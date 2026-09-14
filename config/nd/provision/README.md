# ND provisioning tool

Provisions one lab testbed (fabrics, MSD, switches, vPC + ToR pairing, ISN links, overlay, campus leaf) into one Nexus Dashboard from a declarative
topology file, and snapshots/diffs ND state to prove two testbeds mirror each other. Replaces the ad-hoc REST steps that
used to live only in the `provision-isn` skill and `docs/nd4_fabrics_bringup.md`.

## Files

- `topology_nd421.yaml` / `topology_nd431.yaml` - the two testbeds (SITE1/SITE2/ISN/MSD + the CAMPUS1 Cat9kv leaf per controller); differ only in hostnames and mgmt IPs
- `provision.py` - phased, idempotent, `--dry-run` (phases: fabrics, msd, switches, vpc, tor, isn, overlay, deploy)
- `snapshot.py` - `dump` (read-only) and `diff` (normalized)
- `nd_client.py`, `topology.py` - library code; `tests/` - pytest for the pure parts

## Usage (on the lab host, prod env sourced)

```bash
source ~/repos/n9kv-kvm/env_prod/env.sh
cd ~/repos/n9kv-kvm
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase all --dry-run
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase fabrics
# ... msd, switches (waits for discovery), vpc, tor, isn, overlay, deploy
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421 --nd-ip 10.10.20.10
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431 --nd-ip 10.10.20.20
uv run config/nd/provision/snapshot.py diff ~/tmp/snap_nd421 ~/tmp/snap_nd431 \
  --map S1_BG1=S3_BG1 --map S1_SP1=S3_SP1 --map S1_LE1=S3_LE1 --map S1_LE2=S3_LE2 --map S1_LE3=S3_LE3 --map S1_LE4=S3_LE4 \
  --map S1_TOR1=S3_TOR1 --map S2_BG1=S4_BG1 --map S2_SP1=S4_SP1 --map S2_LE1=S4_LE1 --map WAN1=WAN2 --map C1_LE1=C3_LE1
```

## Gotchas carried over from ND 4.2.1

- `POST /fabrics/{f}/switches` rejects entries without `serialNumber` and `model` (HTTP 400 schema validation). The `switches` phase therefore runs
  `POST /fabrics/{f}/actions/shallowDiscovery` first (seed IPs, `maxHop: 0`) and adds only the switches ND reports `manageable`; unreachable ones are logged and skipped.
- The add sends `preserveConfig: true` for external fabrics (ND rejects `false` there: "preserveConfig option should be true for External Fabric Type")
  and `false` for VXLAN fabrics, matching the GUI's *Preserve Config* checkbox.
- "Recalculate and Deploy" is two calls: `POST /fabrics/{f}/actions/configSave` then `POST /fabrics/{f}/actions/deploy`. The older
  `actions/configDeploy` is deprecated on 4.3.1 and never generated the underlay intent there. Both calls are synchronous (minutes on a 7-switch fabric).
- For switches added through the API (seen on 4.3.1; also seen on 4.2.1 with POAP/discovery adds, never with GUI-added switches) the first deploy after a
  Recalculate can run against a stale expected config (the import-time defaults), emit `no vlan 1`, fail with "Deletion of VLAN 1 is not allowed!!" and
  abort that switch; the next deploy uses the fresh intent. `config_deploy()` checks pendingConfig after the deploy, prints the failed commands from
  `deploymentHistory`, and deploys once more if anything is left.
- The `overlay` phase creates the objects under `overlay:` in the fabrics they list (`MSD` for both shipped files, so the two sites share one L2/L3
  VNI; ND propagates them to SITE1/SITE2), attaches them per switch, and deploys with `vrfActions/deploy` / `networkActions/deploy` (both need the
  VRF/network names in the body). An access-mode attachment interface (`{mode: access, interfaceRange: Ethernet1/2}`) makes the tool first put that
  port into access mode (`accessHost` policy): every unused leaf port defaults to `trunkHost` and ND refuses an access attachment on a trunk port.
  The shipped overlay is VRF `LAB` (L3VNI 50001) + network `LAB_NET1` (VLAN 2, L2VNI 30001, anycast gateway 192.0.1.1/24) on the S1 vPC pair and
  S2_LE1 (Ethernet1/2 = the S2_H1 host port). S1_H1 hangs off S1_TOR1 and is not reachable through this yet: the attachment API has no ToR-port
  concept. The `tor` phase now pairs the ToR with its leaf vPC; attaching `LAB_NET1` to the ToR host port is the remaining step.
- The `vpc` phase pairs the leaf pairs listed under `vpc_pairs:` with ND's default template (`PUT /fabrics/{f}/switches/{sn}/vpcPair`,
  `vpcAction: pair`); ND allocates the domain id in pairing order and generates the `port-channel500` peer-link over the discovered leaf link.
  It then recalculates and deploys the fabric. Pairs ND already lists (`GET /fabrics/{f}/vpcPairs`, either order) are skipped.
- The `tor` phase runs after `vpc` and models ND's ToR pairing (GUI: *Leaf-ToR pairing*) for the entries under `tor_pairs:`; each names a ToR
  and the leaf vPC pair it uplinks to (both leafs must be a `vpc_pairs` entry, validated at load). Per ToR it reads
  `GET /fabrics/{f}/accessAssociations?aggregationOrLeafSwitchId=<LE1>&aggregationOrLeafPeerSwitchId=<LE2>` (400 without the leaf serial) and skips the
  ToR when its record carries a non-empty `resources` block, the mark of a real association: without `includeCandidates` ND still lists an unpaired ToR
  as a recommendation with `isRecommended: true` and empty `resources`. Otherwise it re-reads with `includeCandidates=true` and posts a one-item list
  to `accessAssociationActions/associate` whose `resources` are the port-channel / vPC ids ND recommends for that ToR if it recommends any, else the
  `tor_po` / `leaf_po` / `vpc_id` pinned on the `tor_pairs` entry. ND 4.2.1 recommends none: every form of the GET (with/without `includeCandidates`,
  with/without the peer serial) answers `resources: {}` (lab, 2026-09-14), so the shipped files pin port-channel1 / vpc1 on both sides, the GUI's
  first free id, clear of the `port-channel500` peer-link and of vpc200/201/210 + Ethernet1/8-1/10 that the `cisco.nd` `nd_interface_vpc_*`
  integration targets own on this leaf pair. The answer is HTTP 207 with per-item `status`; a `failed` item aborts the phase before any deploy. No
  ids from either source (the ToR is not a candidate, or `remarks` says its uplinks are not connected, and the entry pins none) also aborts rather
  than guessing; under `--dry-run` the POST is logged with the pinned ids or `<nd-recommended>` placeholders. It then recalculates and deploys the fabric: the association
  creates the ToR uplink port-channel on the ToR and a ToR-owned vPC (plus port-channels) on both leafs. Until it runs, every Recalculate on 4.2.1
  raises the `No leaf-tor pairing is found for the tor` anomaly (`Fabric_Template~configSave:handleTorLeafPairing`); 4.3.1 hides the same condition.
- Pairing a ToR adds a vPC ND owns to the leaf pair. Before running the `cisco.nd` vPC integration targets against a paired fabric, check that vPC's
  `policyType` against the modules' managed policy set (`trunkVpcHost` for `nd_interface_vpc_trunk_host`, `accessVpcHost` for `nd_interface_vpc_access`;
  their `overridden` scenario queries the fabric's vPC interfaces and deletes every one of its managed type that it did not declare). Also run those
  targets with `nd_test_manage_vpc_pairs=false`: their default setup unpairs and re-pairs LE1/LE2 with a virtual peer-link, which would drop the
  ToR association with the pair. Pair one controller first and run `nd_interface_vpc_trunk_host` there before pairing the other.
- The `deploy` phase recalculates and deploys the fabric group (MSD) after its child fabrics; that group deploy is what creates the multisite
  underlay/overlay links between the border gateways and their `ext_base_border_multisite` / `evpn_multisite_interface` policies.
- `snapshot.py diff` maps hostnames with alphanumeric lookarounds (hostnames contain `_`), so per-switch files such as
  `interfaces_SITE1_S1_BG1.json` pair with their mirror.
- `GET /fabrics/{f}/policies?switchId=X` returns the whole fabric on 4.3.1 (the filter is ignored); the tool filters client-side.
- Log lines redact `password`/`userPasswd` values; the real requests still carry them.
- External fabrics created via API come up with `management.monitoredMode: true`; the `isn` phase flips it, otherwise every deploy is silently a no-op.
- IOS-XE runs one BGP process: any stray `router bgp` on the WAN router other than the ISN ASN aborts the deploy mid-script.
- `GET /links` needs `fabricName`; policy lists page at 10 - the client always walks pages.
- ebgpVrfLite links put no IPs on parent interfaces; they appear on subinterfaces once a VRF is extended.
- `CAMPUS1` is a `vxlanCampus` fabric (Campus VXLAN EVPN) holding one Catalyst 9000v leaf with no links; it exists so the `cisco.nd` IOS-XE interface
  tests have an ND-managed Catalyst. `_switch_password` picks `IOSXE_PASSWORD` by switch platform (`ios-xe`), so both `ISN` and `CAMPUS1` use it.
  The leaf is added with `preserveConfig: false` (ND owns its config, like the NX-OS fabrics).
- Cat9kv MTU: the image takes `system mtu` / per-port `mtu` only in 1500-8978 and refuses a per-port value above `system mtu`, so ND's campus
  defaults (`systemMtu` 1500, `l2HostInterfaceMtu` 9216 -> 9198) fail every host-port deploy with "Command mtu 9198 is invalid". The shipped
  `CAMPUS1` settings pin `systemMtu: 8978` and `l2HostInterfaceMtu: 1500` (no `mtu` line in the generated `iosXeTrunkHost` policy).
