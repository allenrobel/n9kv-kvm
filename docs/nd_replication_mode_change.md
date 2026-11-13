# Changing a VXLAN fabric from multicast to ingress replication in Nexus Dashboard

Date: 2026-11-13. Controller: ND 4.3.1 (10.10.20.20), fabrics `SITE1` and `SITE2`.

## Status

The ND 4.3.1 testbed now runs ingress replication in `SITE1` and `SITE2` and is back on the golden baseline.

- `golden.py drift` against `topology_nd431.yaml` reports no drift, and no switch has pending config.
- All ten switches report `inSync`. `MSD` holds `ISN`, `SITE1` and `SITE2` again.
- VRF `LAB` and network `LAB_NET1` are attached and deployed as before.
- On the switches, `show nve vni` lists VNI 30001 as `UnicastBGP`, state Up, and the NVE peers are up on both sites.
- The cross-site host ping from `S3_H1` to `S4_H1` (192.0.1.172) works.
- The ND 4.2.1 testbed (10.10.20.10) is untouched and still runs multicast.

## What the interface tests should expect

The restore reset test residue on ND 4.3.1 to the golden role defaults. Anything the test setup created earlier has to be created again.

| Switch | Object | Before | Now |
|--------|--------|--------|-----|
| `S3_BG1` | `Ethernet1/10`-`1/14`, `1/31`-`1/34`, `1/41`-`1/50` | `trunkHost` (some with VLANs 400-500, "Fan-out test trunk ports") | `routedHost`, MTU 9216 |
| `S3_TOR1` | `port-channel10` (`l3Po`, "Routed subinterface parent for integration tests") | present | deleted |
| `S3_TOR1` | `Ethernet1/63` | `routedHost` | `trunkHost` |
| `S3_TOR1` | `Ethernet1/3` (`S3_H1` host port) | `trunkHost` | `accessHost` |
| `C3_LE1` | `GigabitEthernet1/0/1` | `iosXeRoutedHost` | `iosXeTrunkHost` |

Fabric settings that differ from the multicast baseline, in `SITE1` and `SITE2`:

- `replicationMode` is `ingress`.
- ND no longer returns `anycastRendezvousPointIpRange`, `multicastGroupSubnet`, `rendezvousPointLoopbackId`, `underlayMulticastGroupAddressLimit`,
  `autoGenerateMulticastGroupAddress` or `tenantRoutedMulticastIpv6`.
- The member-fabric copies of `LAB_NET1` carry `l2Data.fabricData.enableIr: true`. The `MSD` object always reads `false`.

The switches keep `feature pim` (ND leaves it in place on purpose) but have no `ip pim` lines, no RP and no `mcast-group`.

## The error

Recalculate (`POST /fabrics/SITE1/actions/configSave`) answered HTTP 500 after the fabric setting was saved as `ingress`:

```text
Switch [S3_BG1/99JQH3UGNC0]: Cannot change Fabric Replication Mode from Multicast to Ingress with existing overlay definitions.
... (one line each for S3_LE1, S3_LE2, S3_LE3, S3_LE4, S3_SP1)
Inconsistency between Fabric setting and existing device configuration. All errors should be resolved prior to Recalculate Config.
```

At that point every overlay object was already gone: no VRFs, networks, attachments or VNI/VLAN allocations in `SITE1`, `SITE2` or `MSD`, no
`MSD` members, and nothing on the switches (`show nve vni` empty, only the default and management VRFs).

## Root cause

ND counts an inter-fabric VRF-Lite link as an "overlay definition". `SITE1` still had one: the `ebgpVrfLite` link `S3_BG1 Ethernet1/3` to
`WAN2 GigabitEthernet2` (`LINK-UUID-7110`), the ISN link.

The check lives in ND's `fabric_utility_11_1` template, which is readable through
`GET /appcenter/cisco/ndfc/api/v1/configtemplate/rest/config/templates/fabric_utility_11_1`:

```python
overlayConfigPresent = Util.exe(Helper.isOverlayExist(FABRIC_NAME))
...
if REPLICATION_MODE == "Ingress":
    ptiList = Util.exe(PTIWrapper.get(deviceSn, "SWITCH", "SWITCH", "UNDERLAY", "base_multicast_11_1"))
    ptiList += Util.exe(PTIWrapper.get(deviceSn, "SWITCH", "SWITCH", "UNDERLAY", "base_pim_asm_v6"))
    if ptiList:
        if overlayConfigPresent and ENABLE_EVPN == "true":
            respObj.addErrorReport(..., "Cannot change Fabric Replication Mode from Multicast to Ingress with existing overlay definitions.", deviceSn)
```

- The error is raised once per switch that still has the multicast underlay policy `base_multicast_11_1`. `S3_TOR1` has none, so it was not listed.
- `Helper.isOverlayExist` is one fabric-wide flag. It is Java, so its body is not readable, but the `Easy_Fabric` template uses the same helper to
  guard a BGP ASN change with the message "existing overlays, VRF lite IFCs, Multi-Site IFCs, or BGP policies with different ASN".
- Confirmation: after deleting `LINK-UUID-7110` and changing nothing else, the same Recalculate answered HTTP 200. `SITE2` behaved the same way
  with its link `LINK-UUID-15510`.
- Once the multicast policies are gone the check no longer fires. Recalculate passed again after the VRF-Lite links were recreated.

The same template has the mirror check for Ingress to Multicast, keyed on the `ingress_rep_simulated` policy.

## Procedure

Per fabric, in this order. This is what was run on ND 4.3.1 and is the plan for ND 4.2.1.

1. Detach and delete every network and VRF, and remove the fabric from its fabric group.
2. Save `replicationMode: ingress` on the fabric. Through the API, remove the multicast-only keys listed above from the `PUT /fabrics/{f}` body.
   With `anycastRendezvousPointIpRange` still in the body ND answers HTTP 400 `invalid fields [anycastRendezvousPointIpRange=...]`.
3. Delete the fabric's `ebgpVrfLite` links (`DELETE /links/{linkId}`).
4. Recalculate and deploy the fabric. The first deploy left pending lines on the leaves and spine; a second deploy cleared them.
5. Recreate the links, re-add the fabrics to the group, then Recalculate and deploy the fabrics and the group.
6. Recreate the overlay.

Order matters in steps 5 and 6:

- ND refuses a network attachment on a border gateway until the group deploy has generated the multisite links
  (`At least one multi-site overlay link should be available to extend overlays`).
- A network created in `MSD` before the ingress fabrics have joined gets `enableIr: false` on its member copies. ND then generates a bare
  `member vni 30001` with no replication line, the L2 VNI stays Down (`show nve vni` shows `Unconfigured`), and ND reports nothing pending.
  Created after they have joined, the member copies get `enableIr: true` without it being sent. A `PUT` of `enableIr` on the `MSD` object is
  accepted (204) and ignored; a `PUT` on each member copy followed by `networkActions/deploy` repairs it.

With this repo's tooling, steps 5 and 6 are `provision.py --phase msd`, `--phase deploy`, then `golden.py restore`.

## Tooling notes for this repo

- `topology_nd431.yaml` now pins `replicationMode: ingress` for `SITE1` and `SITE2` in place of `anycastRendezvousPointIpRange`.
  The change is on the local branch `nd431-ingress-replication`, not committed.
- `topology_nd421.yaml` is unchanged, so `test_shipped_topologies_differ_only_in_hostnames_and_mgmt_ips` fails until ND 4.2.1 is converted.
- `golden.py` does not cover fabric-group membership and has no operation to update an existing network; it reports such a network as
  `DIFFERENT` and applies nothing.
