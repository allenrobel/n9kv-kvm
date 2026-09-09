# ND provisioning tool

Provisions one lab testbed (fabrics, MSD, switches, ISN links, overlay) into one Nexus Dashboard from a declarative
topology file, and snapshots/diffs ND state to prove two testbeds mirror each other. Replaces the ad-hoc REST steps that
used to live only in the `provision-isn` skill and `docs/nd4_fabrics_bringup.md`.

## Files

- `topology_nd421.yaml` / `topology_nd431.yaml` - the two testbeds (SITE1/SITE2/ISN/MSD on each controller); they differ only in hostnames and mgmt IPs
- `provision.py` - phased, idempotent, `--dry-run` (phases: fabrics, msd, switches, vpc, isn, overlay, deploy)
- `snapshot.py` - `dump` (read-only) and `diff` (normalized)
- `nd_client.py`, `topology.py` - library code; `tests/` - pytest for the pure parts

## Usage (on the lab host, prod env sourced)

```bash
source ~/repos/n9kv-kvm/env_prod/env.sh
cd ~/repos/n9kv-kvm
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase all --dry-run
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase fabrics
# ... msd, switches (waits for discovery), isn, overlay, deploy
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421 --nd-ip 10.10.20.10
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431 --nd-ip 10.10.20.20
uv run config/nd/provision/snapshot.py diff ~/tmp/snap_nd421 ~/tmp/snap_nd431 \
  --map S1_BG1=S3_BG1 --map S1_SP1=S3_SP1 --map S1_LE1=S3_LE1 --map S1_LE2=S3_LE2 --map S1_LE3=S3_LE3 --map S1_LE4=S3_LE4 \
  --map S1_TOR1=S3_TOR1 --map S2_BG1=S4_BG1 --map S2_SP1=S4_SP1 --map S2_LE1=S4_LE1 --map WAN1=WAN2
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
- The `vpc` phase pairs the leaf pairs listed under `vpc_pairs:` with ND's default template (`PUT /fabrics/{f}/switches/{sn}/vpcPair`,
  `vpcAction: pair`); ND allocates the domain id in pairing order and generates the `port-channel500` peer-link over the discovered leaf link.
  It then recalculates and deploys the fabric. Pairs ND already lists (`GET /fabrics/{f}/vpcPairs`, either order) are skipped.
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
