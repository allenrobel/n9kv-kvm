# Changing a VXLAN fabric from multicast to ingress replication in Nexus Dashboard

Date: 2026-11-13. Controller: ND 4.3.1 (10.10.20.20), fabrics `SITE1` and `SITE2`.

## Status

Both testbeds run ingress replication in `SITE1` and `SITE2` and are on the golden baseline. ND 4.3.1 was converted by hand, following the
procedure below. ND 4.2.1 was converted on 2026-11-13 by `golden.py convert`, which automates that procedure.

ND 4.3.1:

- `golden.py drift` against `topology_nd431.yaml` reports no drift, and no switch has pending config.
- All ten switches report `inSync`. `MSD` holds `ISN`, `SITE1` and `SITE2` again.
- VRF `LAB` and network `LAB_NET1` are attached and deployed as before.
- On the switches, `show nve vni` lists VNI 30001 as `UnicastBGP`, state Up, and the NVE peers are up on both sites.
- The cross-site host ping from `S3_H1` to `S4_H1` (192.0.1.172) works.

ND 4.2.1 (10.10.20.10), after `golden.py convert --replication-mode ingress`:

- The run took about 15 minutes and ended with zero drift and no pending config. `MSD` holds `ISN`, `SITE1` and `SITE2`.
- `show nve vni` lists VNI 30001 as `UnicastBGP`, state Up, on `S1_LE1`, `S2_LE1` and `S1_BG1`; the NVE peers are up and there are no PIM neighbours.
- The host ping from `S1_H1` to `S2_H1` (192.0.1.172) works.
- `convert` was then validated in both directions and across interrupted runs on 2026-11-18 and 2026-11-19 (see
  "Validation of both directions and of resume" below). ND 4.2.1 was left in ingress mode.

## What the interface tests should expect

The restore reset test residue on ND 4.3.1 to the golden baseline. Anything the test setup created earlier has to be created again.
The baseline (the same in `topology_nd421.yaml`) is:

| Switch | Object | Baseline |
|--------|--------|----------|
| `S3_BG1`, `S4_BG1` | free ports, including `Ethernet1/10`-`1/14`, `1/31`-`1/34`, `1/41`-`1/50` | `trunkHost`, `allowedVlans: none`, MTU `jumbo` |
| `S3_BG1` | `Ethernet1/63` | `routedHost`, MTU 9216 |
| `S3_BG1` | `port-channel10` (`l3Po`, "Routed subinterface parent for integration tests") | present, MTU 9216 |
| `S3_TOR1` | `Ethernet1/63` | `routedHost`, MTU 9216 |
| `S3_TOR1` | `port-channel10` (`l3Po`, "Routed subinterface parent for integration tests") | present, MTU 9216 |
| `S3_TOR1` | `Ethernet1/3` (`S3_H1` host port) | `accessHost` |
| `C3_LE1` | `GigabitEthernet1/0/1` | `iosXeTrunkHost` |

The ND 4.2.1 mirror pins the same objects on `S1_BG1` and `S1_TOR1`. The `Ethernet1/63` and `port-channel10` entries are the subinterface parents the
integration tests use; nothing else on the border gateways is routed by default.

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

Per fabric, in this order. This is what was run by hand on ND 4.3.1; `golden.py convert` runs these steps (see below) and was used on ND 4.2.1.

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

`golden.py convert` does the whole procedure, steps 1 to 6, against the topology file's `replication_modes` for the target mode, and a rerun
continues a conversion that stopped part way:

```bash
uv run config/nd/provision/golden.py convert --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 --replication-mode ingress --dry-run
uv run config/nd/provision/golden.py convert --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 --replication-mode ingress
```

`--dry-run` prints the plan and the first step's calls and sends nothing. See "Replication modes" in `config/nd/provision/README.md` for the steps, the
refusals and the exit codes.

## Findings from the ND 4.2.1 lab runs

The first `golden.py convert` run against ND 4.2.1 (2026-11-13) stopped in "remove overlay" on these two behaviours; the tool now handles both.

- vPC peers must be attached and detached together. `POST /fabrics/SITE1/vrfAttachments` with
  `{"attachments": [{"vrfName": "LAB", "switchId": "<LE2>", "attach": false}]}` (one peer alone) answered that item with status `failed`:
  `Attach Response : Failed : VPC details not found for Peer Serial no: <LE1>`. ND had in fact detached both peers. Attaching one peer alone
  fails the same way (`VPC details not found for Peer Serial no: <LE2>`). One request carrying both peers,
  `{"attachments": [{"vrfName": "LAB", "switchId": "<LE1>", "attach": true}, {"vrfName": "LAB", "switchId": "<LE2>", "attach": true}]}`,
  answered `success` for both items.
- A network detach that lists interfaces removes only the interfaces. `POST /fabrics/SITE2/networkAttachments` with

  ```json
  {"attachments": [{"networkName": "LAB_NET1", "switchId": "<S2_LE1>", "vlanId": 2,
                    "interfaces": [{"interfaceRange": "Ethernet1/2", "mode": "access"}], "attach": false}]}
  ```

  followed by the network deploy, left the switch `attach: true`, `status: deployed`, `interfaces: []`: ND removed the port and kept the
  switch attached. A second detach with `"interfaces": []` then detached the switch (`attach: false`).

## Validation of both directions and of resume

Run against ND 4.2.1 on 2026-11-18 and 2026-11-19 (UTC). Every run below ended with zero drift and no pending config.

- Ingress to multicast: exit 0 in about 16 minutes, first attempt.
- Multicast to ingress, client lost during the rebuild: the laptop running `convert` slept during the last fabric deploy, giving exit 4 on a read
  timeout. A rerun found both fabrics in ingress, deployed what was pending and ended exit 0.
- Ingress to multicast, Ctrl-C after the first `removeMembers`: exit 130. The rerun printed "resuming a partly converted testbed", planned no
  overlay removal and one group member to remove, and ended exit 0 in about 15 minutes.
- Multicast to ingress, Ctrl-C after `PUT /fabrics/SITE1`: exit 130. `golden.py drift` then refused with exit 2
  (`fabrics disagree on the replication mode (SITE1=ingress, SITE2=multicast); run golden.py convert`). The rerun planned only the mode change
  and the rebuild and ended exit 0 in about 14 minutes.

After the conversion to multicast, on `S1_LE1`, `S2_LE1` and `S1_BG1`: VNI 30001 is Up with multicast group `239.1.1.0`, the PIM neighbours are
up, the RP is `10.13.0.1` in `SITE1` and `10.23.0.1` in `SITE2`, and the NVE peers are up. After the final conversion to ingress, VNI 30001 is
`UnicastBGP` and Up on the same three switches, with no PIM neighbours. The host ping was not repeated in either state.

Answers to the questions the design left open:

- ND accepted the multicast settings `PUT` with only `replicationMode` and `anycastRendezvousPointIpRange` in the multicast delta. No further key
  is needed.
- ND allocated the same values when multicast returned. `fabric_SITE1.json` and `fabric_SITE2.json` of a fresh dump are identical to the reference
  taken before the first conversion, and loopback 254, the RP addresses and the `rp-address ... group-list 239.1.1.0/25` lines match.
- The vPC pairs (domain ids 1 and 2) and the ToR pairing came back unchanged in both directions.
- Whether leaving the fabric group is required was not tested; `convert` always does it.

Other observations:

- `golden/nd421/multicast/` was re-taken from the first run. The earlier dump predated the border-gateway `trunkHost` default and recorded the
  `WAN1`-`S1_BG1` link as `multisiteUnderlay`, where the golden topology and the live controller have `ebgpVrfLite`. The unit tests were written
  against the earlier dumps, which now live in `config/nd/provision/tests/fixtures/snapshots/`. `golden/nd431/multicast/` is still the earlier
  dump, because ND 4.3.1 has not been back in multicast mode.
- During these runs Ctrl-C ended `convert` with a Python traceback and exit 130. It now prints one line and exits 130. Nothing is rolled back
  and a rerun continues.
- A long deploy is one HTTP request held open for minutes. If the client machine sleeps, the request dies while ND carries on; rerun `convert`
  (or `golden.py restore`) from a machine that stays awake.

## Tooling notes for this repo

- Both topology files declare `replication_modes` (`multicast` and `ingress`) for `SITE1` and `SITE2`, and `--replication-mode` picks one. Without
  the flag, `golden.py drift`, `restore` and `adopt` use the mode they detect on the controller. `test_shipped_topologies_load_and_mirror`
  passes in both modes: the two files differ only in hostnames and management IPs.
- `provision.py --phase fabrics` refuses (exit 2) to change the mode of a fabric that already has switches. Use `golden.py convert` for that.
- `golden.py` covers fabric-group membership (a missing member is re-added) and the `enableIr` flag of a golden network's member copies in
  ingress mode. The repair of the flag is two ops: a `PUT` of the member copy, then `networkActions/deploy`. An existing network that differs in any
  other field is still reported as `DIFFERENT` with no repair.

Also seen on the successful run:

- ND refused the first `DELETE /fabrics/MSD/networks/LAB_NET1` while the detach was still being deployed; the retry 10 seconds later succeeded.
- `POST /fabrics/MSD/actions/removeMembers` takes the same body as `addMembers`, `{"members": [{"name": "SITE1"}]}`. Recalculate and Deploy of
  each fabric after it left the group was enough; `MSD` itself needed no deploy at that point.
- On an ingress fabric the `ingress_rep_simulated` policy is present on the switches (checked on ND 4.3.1), which is what the tool uses to
  recognise an unfinished ingress-to-multicast change.
