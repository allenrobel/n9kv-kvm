# ND provisioning tool

Provisions one lab testbed (fabrics, MSD, switches, vPC + ToR pairing, ISN links, overlay, campus leaf) into one Nexus Dashboard from a declarative
topology file, and snapshots/diffs ND state to prove two testbeds mirror each other. Replaces the ad-hoc REST steps that
used to live only in the `provision-isn` skill and `docs/nd4_fabrics_bringup.md`.

## Files

- `topology_nd421.yaml` / `topology_nd431.yaml` - the two testbeds (SITE1/SITE2/ISN/MSD + the CAMPUS1 Cat9kv leaf per controller); differ only in hostnames and mgmt IPs
- `provision.py` - phased, idempotent, `--dry-run` (phases: fabrics, msd, switches, vpc, tor, isn, overlay, deploy); `--replication-mode multicast|ingress`
- `snapshot.py` - `dump` (read-only) and `diff` (normalized)
- `golden.py` - `drift` / `restore` / `adopt` / `convert` of the live ND against the topology files (see "Golden baseline" and "Replication modes" below)
- `golden_drift.py` (pure compare), `golden_live.py` (live read), `golden_apply.py` (push),
  `golden_adopt.py` (bootstrap/adoption writer), `golden_convert.py` (mode conversion) - the modules behind `golden.py`
- `replication.py` - replication-mode knowledge shared by `provision.py` and the golden tools (multicast-only keys, per-mode policy names, mode state)
- `golden/nd421/<mode>/`, `golden/nd431/<mode>/` - reference snapshots (`snapshot.py dump`, credential hashes scrubbed), one directory per replication
  mode; the tool does not read them. Only `multicast/` exists today (both testbeds were dumped in multicast mode); no `ingress/` snapshot has been taken
- `nd_client.py`, `topology.py` - library code; `tests/` - pytest for the pure parts; `tests/fixtures/` - the two base topology files the golden tests use

## Usage (on the lab host, prod env sourced)

```bash
source ~/repos/n9kv-kvm/env_prod/env.sh
cd ~/repos/n9kv-kvm
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --replication-mode ingress --phase all --dry-run
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --replication-mode ingress --phase fabrics
# --replication-mode is required because the shipped files declare replication_modes (there is no default)
# ... msd, switches (waits for discovery; also pins the Catalyst mgmt-port intent to iosXeMgmt/cdp:false in campus fabrics), vpc, tor, isn, overlay, deploy
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421 --nd-ip 10.10.20.10
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431 --nd-ip 10.10.20.20
uv run config/nd/provision/snapshot.py diff ~/tmp/snap_nd421 ~/tmp/snap_nd431 \
  --map S1_BG1=S3_BG1 --map S1_SP1=S3_SP1 --map S1_LE1=S3_LE1 --map S1_LE2=S3_LE2 --map S1_LE3=S3_LE3 --map S1_LE4=S3_LE4 \
  --map S1_TOR1=S3_TOR1 --map S2_BG1=S4_BG1 --map S2_SP1=S4_SP1 --map S2_LE1=S4_LE1 --map WAN1=WAN2 --map C1_LE1=C3_LE1 --map C1_SP1=C3_SP1
```

## Golden baseline (drift, restore, adopt)

The two topology files are the golden baseline of a testbed. `golden.py` compares a live ND with them, pushes the live ND back to them, or
writes the live state into them. One invocation targets one controller (`--nd-ip`), so run it once per testbed.

```bash
source ~/repos/n9kv-kvm/env_prod/env.sh
cd ~/repos/n9kv-kvm
uv run config/nd/provision/golden.py drift --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10     # read-only, exit 1 on drift
uv run config/nd/provision/golden.py drift --topology config/nd/provision/topology_nd431.yaml --snapshot ~/tmp/snap_nd431   # offline
uv run config/nd/provision/golden.py restore --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 \
  [--replication-mode multicast|ingress] [--yes] [--extras adopt|delete|skip] [--no-deploy]
uv run config/nd/provision/golden.py adopt --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 \
  [--replication-mode multicast|ingress] [--snapshot DIR] [--classes links,interfaces,defaults]
uv run config/nd/provision/golden.py convert --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 \
  --replication-mode ingress [--yes] [--extras adopt|delete|skip] [--dry-run]
```

`--replication-mode multicast|ingress` is optional on `drift`, `restore` and `adopt`: without it the mode is detected (see "Replication modes").
`convert` requires it.

- `drift` prints one line per difference (MISSING, DIFFERENT, EXTRA) and changes nothing.
- `restore` prints the drift, writes any adoptions to the topology file first, asks for confirmation (`--yes` skips it), creates or overwrites what is
  missing or different, applies the chosen deletes, then Recalculate & Deploys the touched fabrics and then the groups (`--no-deploy` skips that), re-reads,
  and prints the remaining drift and pending-config counts.
- `adopt` is the bootstrap: it writes `links`, `generated_links`, `interfaces`, `defaults` and so on from the live ND (or a `--snapshot`) into the
  topology file. It prints `CONFLICT:` lines and exits 1 when a live generated link collides with a link the tool owns.
- Exit codes: 0 ok / no drift, 1 drift (`drift`) or conflicts (`adopt`), 2 refused or cancelled, 3 live read failed (HTTP error or
  unreachable controller), 4 apply failed (a failed op, a dropped connection, or a failed Recalculate & Deploy); `restore` exits 0 even with leftovers, so
  read its remaining-drift line.
- Extras are objects that exist live but not in golden. `--extras adopt` writes them into the yaml, `delete` removes them from ND, `skip` leaves them;
  without the flag `restore` asks per object. With `--yes` and extras present but no `--extras`, `restore` exits 2 and asks for `--extras adopt|delete|skip`.
  `restore` also Recalculate & Deploys any fabric whose switches still carry pending config from an earlier aborted run.

Rules:

- Covered classes: tool-owned fabric and ISN links, ND-generated links listed under `generated_links`, physical interface policies, logical interfaces,
  network/VRF attachments, VRFs and networks, vPC and ToR pairs, switch membership and role, fabric-group membership, fabric and group settings (golden settings are a subset;
  extra keys in ND are not drift).
- ND-generated links (`multisiteUnderlay`, `multisiteOverlay`, campus links, peer-link and ToR port-channels) are repaired by the owner's Recalculate &
  Deploy and are never deleted or `PUT`. Propagated MSD copies of VRFs and networks are never extras.
- Removing a switch is never automatic: an extra switch is reported only.
- A "delete" of an unlisted physical port is a reset to the role default (`defaults:` per fabric, policy type from ND's role table), because ND refuses to
  delete the port. A logical interface (port-channel, vPC, SVI, subinterface) that ND did not generate is a real DELETE.
- Link /30s are pinned in the yaml. Pin them the way ND already allocated them (`adopt` does): ND refuses a `PUT` that swaps the two ends'
  addresses on an existing numbered link (`IP/Subnet allocation failed: ... is allocated to ...`), so the only way to re-address a link
  is to re-provision it. The two topology files therefore differ in one SITE2 /30 besides hostnames and IPs.
- Policy inputs in the yaml are the lowercase strings the comparison uses (`adminState: 'true'`, `mtu: '9216'`); the PUT bodies carry
  ND's own types (boolean, integer for `mtu`/`accessVlan`/`nativeVlan` when numeric). Both OpenAPI specs type them that way; ND 4.3.1
  validates request bodies against the schema and rejects the strings, ND 4.2.1 does not validate.
- Fabric-group membership drift: a golden member missing from the live group is `MISSING` and `restore` re-adds it (`addMembers`, one member per call);
  a live member the yaml does not list is `EXTRA` and only reported (never removed, never adopted). After a member add, `restore` first deploys the
  mode fabrics that joined and then the group, because ND refuses a network attachment on a border gateway until the group deploy has generated the
  multisite links.
- Ingress `enableIr` drift (ingress mode only): a golden network whose copy in a mode fabric does not have `l2Data.fabricData.enableIr: true` is
  `DIFFERENT`. ND then generates a bare `member vni`, the L2 VNI stays Down and nothing shows as pending. The group's own object always reads `false`
  and a `PUT` on it is ignored, so the repair is two ops per member copy: `put_network_ir` (PUT the live copy with `enableIr: true`), then
  `deploy_network_ir` (`networkActions/deploy` for that network on the switches it is attached to). The deploy is its own action so it always runs
  after the PUT and after any attach.
- The baseline for a free border-gateway port is `trunkHost` (`allowedVlans: none`, `mtu: jumbo`), like a leaf port. `Ethernet1/63` (`routedHost`,
  MTU 9216) and `port-channel10` (`l3Po`, MTU 9216, "Routed subinterface parent for integration tests") are pinned on the SITE1 ToR and border gateway as
  subinterface parents for the `cisco.nd` integration tests.
- `golden/{nd421,nd431}/<mode>/` are reference snapshots only; the topology yaml is the golden.
- Run it only when no tests are running: `restore` is disruptive by design (resets ports, deletes interfaces, deploys fabrics).

The 2026-10-30 bootstrap found test residue (`trunkHost` on BGW and spine ports, an `l3Po` port-channel on the ToRs, a campus `Gi1/0/1`) and one ISN
link converted to `multisiteUnderlay`; `restore --extras delete` handled all of it.

## Replication modes

SITE1 and SITE2 can run either multicast or ingress underlay replication. Each of those fabrics in `topology_nd421.yaml` / `topology_nd431.yaml`
declares both, next to its common `settings`:

```yaml
    replication_modes:
      multicast:
        management: {replicationMode: multicast, anycastRendezvousPointIpRange: 10.13.0.0/24}
      ingress:
        management: {replicationMode: ingress}
```

Both modes must be declared, each must set `management.replicationMode` to its own name, and a key may not appear in both `settings` and
`replication_modes`. The chosen mode's block is merged over `settings` at load time; the fabrics that declare it are the "mode fabrics". A file
that declares modes does not load without a mode (there is no default), and `--replication-mode` on a file that declares none is an error.

Choosing the mode:

- `provision.py` takes `--replication-mode multicast|ingress`, required for the shipped files. An ingress fabric's PUT body drops the multicast-only
  keys (`anycastRendezvousPointIpRange`, `multicastGroupSubnet`, `rendezvousPointLoopbackId`, `underlayMulticastGroupAddressLimit`,
  `autoGenerateMulticastGroupAddress`, `tenantRoutedMulticastIpv6`), because ND answers HTTP 400 `invalid fields` when they are present.
- `golden.py drift`, `restore` and `adopt` take the flag too, but detect the mode when it is omitted: they read `management.replicationMode` of every
  mode fabric (from ND, or from `fabric_<name>.json` of a `--snapshot` dump), print `replication mode: <mode> (detected)`, and exit 2 if a fabric
  reports no valid mode or the fabrics disagree.
- `golden.py convert` requires `--replication-mode`; it is the only command that loads the topology without detecting or checking the live state.

Refusals (exit 2, nothing written):

- `drift`, `restore` and `adopt` on a live read refuse a testbed that is mid-conversion and point at `golden.py convert --replication-mode <mode>`.
  A fabric is "mid" when its setting disagrees with its switches: a switch holds an underlay policy of the other mode (`base_multicast_11_1` or
  `base_pim_asm_v6` for multicast, `ingress_rep_simulated` for ingress), or a switch still has pending config. A snapshot read has no policies, so
  the saved setting alone decides.
- `restore` also refuses when the live setting is not the requested mode, because it cannot change the mode on a populated fabric.
- `provision.py --phase fabrics` refuses (exit 2, before any write) to change the mode of a fabric that already has switches, and exits 3 if it cannot
  read the fabric's switches to tell. A fabric with no switches is changed in place.

### convert

ND refuses to change a fabric's mode while the fabric holds any overlay definition. That includes VRFs, networks, fabric-group membership and the
`ebgpVrfLite` ISN links (see `docs/nd_replication_mode_change.md`). `golden.py convert` therefore tears those down, changes the mode and rebuilds
with the normal restore against the target mode's golden:

1. Remove overlay: detach, deploy and delete every VRF and network of the fabric group and of the mode fabrics (networks first), golden or not.
2. Leave the fabric group: `removeMembers` for each mode fabric, then Recalculate and Deploy each fabric that left.
3. Delete the `ebgpVrfLite` links of the mode fabrics.
4. Change the mode: for each fabric not yet in the target mode, a fresh `GET` of the fabric (taken after the teardown, since leaving the group can change
   inherited settings), then a `PUT` of the target settings merged over it, then Recalculate and Deploy. A re-read verifies the result.
5. Rebuild: `golden.py restore` against the target golden (members, links, deploy, overlay), then a check for zero drift and nothing pending.

Every step is decided from the live state, so a run that stopped part way is continued by running the same command again. A fabric needs converting
while its setting is not the target or a switch still holds an other-mode underlay policy; pending config lines alone do not count and go straight to the
rebuild. After the mode deploy, `convert` deploys once more if a converted fabric still has pending lines. If a fabric is still not in the target mode
after that, it prints the rerun command and exits 4. A testbed whose fabrics already are in the target mode skips steps 1 to 4. A testbed that is intact in
the source mode with pending config is refused (exit 2): deploy it first with `golden.py restore`.

Options: `--nd-ip`, `--yes` (skip the prompt; needs `--extras adopt|delete|skip` for the rebuild's restore, else exit 2 before anything is sent) and
`--dry-run`. Exit codes: 0 converted with zero drift and nothing pending, 2 refused or cancelled, 3 a live read failed, 4 a step failed or drift remains.

`--dry-run` reads the live ND and prints the plan: the target mode, each fabric's state (`multicast`, `ingress` or `mid`), then for each step the
objects it will act on (each VRF and network, each group member, each link with its ND link id, the fabrics whose mode changes). It then prints the exact
calls of the first step that has work (for the mode change, the PUT bodies built from today's fabric values), and sends nothing.

Status: the code is covered by the unit tests. ND 4.3.1 was converted to ingress by hand following the procedure in `docs/nd_replication_mode_change.md`;
`convert` itself has not been run against a lab yet, and ND 4.2.1 is still in multicast.

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
  S2_LE1 (Ethernet1/2 = the S2_H1 host port) and, once the `tor` phase has paired the ToR, S1_TOR1 (Ethernet1/3 = the S1_H1 host port). ND 4.x has
  no ToR-port field on a leaf's attachment row; the ToR is an attachment target of its own (the attachment query lists it with `switchRole: tor`),
  so the ToR host port is one more `network_attachments` entry in access mode, ordered after the leaf rows. The VRF and the network are also
  attached to `S1_BG1` and `S2_BG1` with no interfaces: an MSD stretches an overlay across sites only through the border gateways, and it is the
  BGW attachment that generates the VNI membership (with multisite ingress replication) there. Found the hard way on 2026-09-14: with the BGWs
  unattached, `show nve vni` on both was empty, S1_H1 could ping its anycast gateway but not S2_H1, and ND reported no anomaly at all.
  Two things to know when checking the result: the BGW NVE peers take about a minute to come up after the `overlay` deploy (a host ping
  right after the phase returns still fails; the leaves then show the remote host MAC via BGP with the `RS` flag and `show nve vni` on the BGWs
  shows `MS-IR`), and a ping sourced from a leaf is not a valid cross-site test, because it is sourced from the anycast gateway address that
  the far-side leaf also owns. Test from the host containers (`sudo virsh -c lxc:/// console S1_H1`, then `ping 192.0.1.172`).
  Also note the overlay attach of an interface change (the ToR host port flip to `accessHost`) leaves the port's own lines pending until the
  `deploy` phase recalculates the fabric; `networkActions/deploy` pushes only the VLAN/attachment.
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
  than guessing; under `--dry-run` the POST is logged with the pinned ids or `<nd-recommended>` placeholders. It then recalculates and deploys the fabric.
  Verified on ND 4.2.1 and ND 4.3.1 (2026-09-14, identical results): the answer was `Associated successfully`; the deploy left nothing pending; the ToR got `port-channel1`
  (`uplinkPo`, `tor-connected-to-vPC-leaf:S1_LE1~S1_LE2-vPC1`) with Ethernet1/1-1/2 as `uplinkPoMember`; each leaf got `vPC1` (`vpcUplink`,
  member Ethernet1/3) and `port-channel1` (`vpcUplinkPo`); everything is `allowedVlans: none` until a network is attached. The association GET then
  reports the ToR with `remarks: Already paired` and the ids in `resources`, which is what the skip keys on, and the
  `No leaf-tor pairing is found for the tor` anomaly (`Fabric_Template~configSave:handleTorLeafPairing`, raised by every Recalculate on 4.2.1;
  4.3.1 hides the same condition) cleared with that deploy. Only quirk between versions: 4.2.1 flips the paired record's `isRecommended` to
  false, 4.3.1 leaves it true; the skip keys on `resources`, not on that flag.
- Pairing a ToR adds a vPC ND owns to the leaf pair. Before running the `cisco.nd` vPC integration targets against a paired fabric, check that vPC's
  `policyType` against the modules' managed policy set (`trunkVpcHost` for `nd_interface_vpc_trunk_host`, `accessVpcHost` for `nd_interface_vpc_access`;
  their `overridden` scenario queries the fabric's vPC interfaces and deletes every one of its managed type that it did not declare). ND 4.2.1 gives
  the ToR-pairing vPC `policyType: vpcUplink`, outside both sets, so `overridden` leaves it alone. Also run those
  targets with `nd_test_manage_vpc_pairs=false`: their default setup unpairs and re-pairs LE1/LE2 with a virtual peer-link, which would drop the
  ToR association with the pair. Verified 2026-09-14 on both controllers: every state scenario of `nd_interface_vpc_trunk_host` and
  `nd_interface_vpc_access` passes with the ToR vPC present and leaves `vPC1` / `port-channel1` / `port-channel500` and the association
  byte-for-byte unchanged (the orchestrator drops vPC records whose `policyType` is outside its managed set before validation). Only the
  `multi_pair` precondition fails, which is the develop-side `nd_manage_vpc_pair` gathered bug (cisco.nd issue #565), unrelated and
  expected as the last line of both targets. How they are run, from the collection root on the Mac (the nd-dev container cannot reach
  the lab; `ansible-test network-integration` takes no `-e`, so the flag lives in the committed inventories):

  ```bash
  export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
  cd ~/ansible_collections/cisco/nd
  for t in nd_interface_vpc_trunk_host nd_interface_vpc_access; do
    .venv-Darwin-arm64/bin/ansible-test network-integration "$t" --inventory "$HOME/ansible_collections/cisco/inventory.$t"
  done
  ```

  For ND 4.3.1 copy each inventory, change `ansible_host` to 10.10.20.20 and every `192.168.12.` to `192.168.14.`, and pass the copy.
  The ethernet targets run on the border gateway (`Ethernet1/31`-`1/34`, `1/41`-`1/50`), so nothing in the collection touches the
  ToR-pairing ports (`Ethernet1/3` on LE1/LE2, `Ethernet1/1`-`1/2` on the ToR) or ids (`port-channel1` / `vpc1`).
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
- `CAMPUS1` is a `vxlanCampus` fabric (Campus VXLAN EVPN) holding a Catalyst 9000v leaf and spine with one leaf-spine link (leaf
  `GigabitEthernet1/0/8` to spine `GigabitEthernet1/0/1`), an `iosXeNumbered` link policy observed on both 4.2.1 and 4.3.1; the fabric pins
  `fabricMtu: 8978`. Both switches' `GigabitEthernet0/0` management ports also share an ND data bridge, so IOS-XE's default CDP turns that
  adjacency into a second intra-fabric link and Recalculate & Deploy un-configures the port; the fix is two halves: the Cat9kv day-0 config
  disables CDP on `GigabitEthernet0/0`, and the `switches` phase pins ND's own `iosXeMgmt` intent for that port to `cdp: false`
  (`_ensure_mgmt_cdp_off`) so a Recalculate cannot push `cdp enable` back onto it. `CAMPUS1` exists so the `cisco.nd` IOS-XE interface tests
  have an ND-managed Catalyst and the fabric-link guard has a corruptible endpoint. `_switch_password` picks `IOSXE_PASSWORD` by switch
  platform (`ios-xe`); both switches are added with `preserveConfig: false` (ND owns their config). ND refuses an intent-only policy-type
  change on the link endpoint on both controllers: `PUT .../interfaces/GigabitEthernet1/0/8` with `iosXeAccess` answers HTTP 400
  `Policy type change from iosXeNumbered to iosXeAccess is not allowed`; on 4.3.1 even re-putting the unchanged record is refused (`not
  eligible for edit as it has read only parameters`), while 4.2.1 accepts it and adds `linkStateRoutingTag: UNDERLAY`. Recalculate & Deploy
  (`--phase deploy`), not a record `PUT`, is the reliable way to restore any intent drift on that link. On 4.3.1 the per-interface path also
  needs URL-encoded slashes (`.../interfaces/GigabitEthernet1%2F0%2F8`; the raw name 404s), while 4.2.1 accepts either form; the interface
  list endpoint behaves the same on both.
- Campus link endpoints: deleting the leaf-spine link reclassifies both endpoints. The management port `Gi0/0` - which ND lists as
  `interfaceType management` with policy `iosXeMgmt` (`mode managed`, vrf/ip carried in `extraConfig`) - comes back as an ordinary
  ethernet port with the role default (`iosXeTrunkHost` on the leaf, `iosXeRoutedHost` on the spine, `mtu 9198`); restoring `iosXeMgmt`
  by `PUT` (with `cdp: false`) fixed it. Separately, the campus underlay does not come up on the beta Cat9kv image: link interfaces are
  up/up with correct addressing, CDP crosses the wire, and the host TAP counters move both ways, but the leaf never answers the spine's
  ARP, so OSPF has no neighbor and the BGP EVPN session stays Idle; ND intent, deploy and pending config are unaffected.
- Cat9kv MTU: the image takes `system mtu` / per-port `mtu` only in 1500-8978 and refuses a per-port value above `system mtu`, so ND's campus
  defaults (`systemMtu` 1500, `l2HostInterfaceMtu` 9216 -> 9198) fail every host-port deploy with "Command mtu 9198 is invalid". The shipped
  `CAMPUS1` settings pin `systemMtu: 8978`, `fabricMtu: 8978` (intra-fabric link interfaces) and `l2HostInterfaceMtu: 1500` (no `mtu` line in
  the generated `iosXeTrunkHost` policy).
