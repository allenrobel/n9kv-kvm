# Catalyst 9000v (Cat9kv) campus leaf design

Date: 2026-09-11
Status: Approved

## Purpose

Give each Nexus Dashboard controller one ND-managed Catalyst 9000v so the `cisco.nd` IOS-XE interface modules
(`nd_interface_ethernet_access`, `nd_interface_ethernet_trunk_host`, `nd_interface_ethernet_routed`) can run their
`xe.yaml` integration scenarios against a Catalyst switch. Source of the request: the ansible-nd handoff of
2026-09-11 (`/iso1/cml/cat9kv-17.15.03/HANDOFF.md` on glide).

Neither ND controller manages a Catalyst switch today. The only IOS-XE devices are the C8000V WAN routers
(`WAN1`, `WAN2`) in the `ISN` external fabric, which cannot exercise Catalyst-specific interface policies.

## Decisions

- **One Catalyst leaf per controller in a new `vxlanCampus` fabric named `CAMPUS1`.** A Catalyst switch cannot join
  the NX-OS-only `vxlanIbgp` fabrics. Both controllers get a fabric with the same name and ASN, mirrored the way
  `SITE1`/`SITE2` are.
- **No fabric links.** The interface modules write intent and deploy per-interface config; no spine, underlay or
  overlay adjacency is exercised. `GigabitEthernet1/0/1` (the tests' default interface) must stay free of any ND
  fabric link, so the leaf is not cabled to any other switch. Front-panel NICs exist only because the image will not
  boot with fewer than nine NICs.
- **Mirror convention holds.** The ND 4.2.1 leaf lives on `BR_ND_DATA_12` (192.168.12.x); the ND 4.3.1 leaf lives on
  `BR_ND_DATA_14` (192.168.14.x) with the same last octet. The handoff's "both on `BR_ND_DATA_12`" is stale: ND 4.3.1
  was re-homed to `BR_ND_DATA_14` in September 2026.
- **`config/cat9kv/` is a self-contained mirror of `config/8000v/`.** Same repo convention as the C8000V launcher
  (which mirrors the n9kv launcher): no shared library, no changes to the two working launchers. The C8000V spec
  deferred extraction "until a third platform lands"; this is that platform, but extracting shared plumbing is a
  separate refactor and is not done in this change.
- **`vswitch.xml` is edited only for the serial.** Cisco's CML node definition ships `port_count 24` as static content
  regardless of NIC count (9 to 25). That is the proven combination; `port_count` is not tied to the NIC count.
- **The serial is pinned per instance.** ND keys switches on the serial; the Cat9kv reads it from `vswitch.xml`, so a
  fixed value avoids the Nexus 9000v serial churn on reload. The serial derives from the sid.

## Placement

| Controller | Fabric | Host | sid | mgmt bridge | mgmt IP | serial | RAM |
|---|---|---|---|---|---|---|---|
| ND 4.2.1 (10.10.20.10) | `CAMPUS1` (`vxlanCampus`, ASN 65003) | `C1_LE1` | 1701 | `BR_ND_DATA_12` | 192.168.12.181/24 | `CAT9KV1701` | 18432 MB |
| ND 4.3.1 (10.10.20.20) | `CAMPUS1` (`vxlanCampus`, ASN 65003) | `C3_LE1` | 3701 | `BR_ND_DATA_14` | 192.168.14.181/24 | `CAT9KV3701` | 18432 MB |

- Hostnames: `C<n>_LE<idx>` where `C` marks the campus fabric and `n` follows the odd-site = ND 4.2.1, mirror =
  ND 4.3.1 rule used by `S1`/`S3`.
- sid: the existing `SRII` scheme (`site*1000 + role*100 + index`) with a new role digit `7` = campus leaf. Consoles
  land on telnet `11701` / `13701` and monitors on `21701` / `23701`, clear of every n9kv (`1xxxx`) and WAN (`19101`,
  `19102`) port.
- IPs: `.18x` is a new block for campus leaves (`.13x` BG, `.14x` SP, `.15x` LE, `.16x` TOR, `.17x` containers).
  Both `.181` addresses are unused on the ND data segments and in both topology files.
- Fabric settings (both controllers, identical):

  ```yaml
  management:
    bgpLoopbackIpRange: 10.41.0.0/22
    nveLoopbackIpRange: 10.42.0.0/22
    anycastRendezvousPointIpRange: 10.43.0.0/24
    intraFabricSubnetRange: 10.44.0.0/22
    vrfLiteSubnetRange: 10.45.0.0/16
  ```

  Follows the `SITE1` 10.1x / `SITE2` 10.2x pattern. ND's campus default `vrfLiteSubnetRange` is 10.33.0.0/16;
  setting it explicitly keeps the pools disjoint from every other fabric.
- Memory: 2 x 18 GiB on top of the ~340 GiB used on glide (755 GiB physical, 415 GiB available on 2026-09-11).

## Files

### New: `config/cat9kv/`

| File | Purpose |
|---|---|
| `cat9kv.py` | Launcher: loads global + per-switch YAML, creates TAPs, attaches the wired ones to OVS, builds and starts QEMU. Same CLI flags as `8000v.py`. |
| `startup_config.py` | Renders the day-0 config from the per-switch YAML, substitutes the serial into `vswitch.xml`, and builds the day-0 ISO. `--print`, `--all`. |
| `iosxe_startup_config.j2` | Day-0 Jinja2 template. |
| `vswitch.xml` | Day-0 ASIC selector from the CML node definition (`board_id 20612`, `port_count 24`). The serial is substituted at ISO build time. |
| `global_config.yaml` | Global defaults (below). |
| `C1_LE1.yaml`, `C3_LE1.yaml` | Per-switch configs. |
| `con_c1_le1`, `ssh_c1_le1`, `con_c3_le1`, `ssh_c3_le1` | Console / SSH one-liners. |
| `README.md` | Usage doc for the subsystem. |

### Changed

| File | Change |
|---|---|
| `config/nd/provision/topology_nd421.yaml`, `topology_nd431.yaml` | Add the `CAMPUS1` fabric with its switch (`platform: ios-xe`). |
| `config/nd/provision/provision.py` | `_switch_password` picks the credential by switch platform (`ios-xe` -> `IOSXE_PASSWORD`), not by fabric type. |
| `config/nd/provision/tests/` | Fabric list in the shipped-topology test; password rule tests by platform. |
| `config/nd/provision/README.md` | `CAMPUS1` in the topology description; `--map C1_LE1=C3_LE1` in the snapshot diff example. |
| `config/ansible/dynamic_inventory.py` | `C1_LE1_IP4`, `C3_LE1_IP4`, hostnames, `CAMPUS1_FABRIC`. |
| `env/02-ansible.sh` | `ND_FABRIC_CAMPUS1=CAMPUS1`. (Same line added to `env_prod/` locally; never committed.) |
| `README.md` | Topology section and project-structure table mention `config/cat9kv/` and `CAMPUS1`. |
| `CLAUDE.md` | `config/cat9kv/` row in the layout table; `C` prefix and role digit 7 in the conventions. |

## Configuration schema

`global_config.yaml`:

```yaml
image_path: /iso1/cml/cat9kv-17.15.03
cdrom_path: /iso2/iosxe/config           # per-VM qcow2 + day-0 ISO, next to WAN1/WAN2
default_image: cat9kv_prd.17.15.03.qcow2
base_mac: "52:54:00"
default_ram: 18432                        # MB; the image does not boot with less
default_vcpus: 4
default_interface_type: e1000
min_nics: 9                               # image minimum; unused front-panel NICs are padded
```

Per-switch YAML, same keys as the C8000V schema:

```yaml
name: C1_LE1
role: Campus Leaf
sid: 1701
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.181/24
mgmt_gw: 192.168.12.1
neighbors: []
isl_bridges: []
```

`len(neighbors) == len(isl_bridges)` is enforced as in the other launchers. `serial` is derived as
`CAT9KV{sid}`; the launcher and the ISO builder compute it from the same YAML so they cannot disagree.

## QEMU launch

From the CML node definition (`sim.linux_native`: driver `csr1000v`, `disk_driver: ide`, `nic_driver: e1000`,
4 vCPU, 18432 MB, 2 serial ports, BIOS boot):

- `-machine type=pc,accel=kvm` (i440fx, which carries the legacy IDE controller; q35 does not). No `-bios`: the image
  boots SeaBIOS, unlike the `serial_efi` C8000V.
- Disk: `-drive file=<cdrom_path>/<name>.qcow2,if=ide,format=qcow2,cache=writethrough`. The per-VM qcow2 is a copy of
  the base image (as the C8000V launcher does), never the extracted file itself.
- Day-0: `-drive file=<cdrom_path>/<name>.iso,media=cdrom`.
- NICs, in PCI order: index 0 = `GigabitEthernet0/0` on `mgmt_bridge`; index i (1..N) = `GigabitEthernet1/0/i` on
  `isl_bridges[i-1]`; then pad indices N+1 .. `min_nics`-1 with TAPs that are created and brought up but attached to no
  bridge. All NICs are `e1000` with MACs from the SRII generator (`52:54:00:<sid_hi>:<port>:<sid_lo>`).
- Two serial ports: `-serial telnet:localhost:<10000+sid>,server=on,wait=off` (console) and `-serial null`.
- Monitor on `20000+sid`, `-name <name>`, `-nographic`, `-rtc clock=host,base=localtime`, memory backend + NUMA
  node as in the C8000V launcher.

TAP names are `tap<sid>-<index>` (`tap1701-0` .. `tap1701-8`). Padding TAPs skip `ovs-vsctl add-port`; `--teardown`
removes them like any other.

## Day-0 config

`startup_config.py` renders `iosxe_startup_config.j2`:

```text
hostname {{ hostname }}
!
vrf definition Mgmt-vrf
 address-family ipv4
 exit-address-family
!
username admin privilege 15 secret 0 {{ admin_password }}
!
ip domain name lab.local
ip ssh version 2
!
interface GigabitEthernet0/0
 vrf forwarding Mgmt-vrf
 ip address {{ mgmt_ip_addr }} {{ mgmt_netmask }}
 no shutdown
!
ip route vrf Mgmt-vrf 0.0.0.0 0.0.0.0 {{ mgmt_gw }}
!
line vty 0 15
 login local
 transport input ssh
!
event manager applet GENERATE_RSA_KEYS
 ... (same one-shot RSA keygen as the C8000V template)
!
end
```

`Mgmt-vrf` is the Catalyst's built-in management VRF (`GigabitEthernet0/0` is in it by default); declaring it is
harmless and keeps the file self-describing. Password from `$IOSXE_PASSWORD`, falling back to `$NXOS_PASSWORD`. No
`license boot level` line and no SNMP config until first boot shows either is needed (WAN1 is the precedent: ND
discovery works against the same day-0 shape).

The ISO staging directory holds `iosxe_config.txt` and `conf/vswitch.xml` (the committed file with
`<prod_serial_number>` replaced by the switch serial). Build: `genisoimage -o <name>.iso -V CDROM -r -J <dir>`.
Volume label `CDROM` is what the image looks for.

## Provisioner

- `topology.py` needs no schema change: `Fabric.type` is a free string and `Switch.platform` already exists.
- `fabric_create_payload` is unchanged; `vxlanCampus` requires only `bgpAsn`. The pools above are merged through the
  existing `settings:` path in `phase_fabrics`.
- `_switch_password(fabric)` returns `IOSXE_PASSWORD` when every switch in the fabric is `ios-xe` (the existing
  `_platform` helper already rejects mixed fabrics), `NXOS_PASSWORD` otherwise. The `ISN` fabric keeps working because
  its only switch is `ios-xe`.
- `switch_add_payload` is unchanged: `preserveConfig` is `true` only for `externalConnectivity`, so the campus leaf is
  added with `false` and ND owns its config.
- `phase_switches` recalculates and deploys `CAMPUS1` like every other fabric. With one leaf and no links, the deploy
  writes the leaf's underlay/base intent (OSPF process, loopbacks, nve). If ND rejects a single-leaf deploy, that is a
  finding to record, not something to pre-empt.
- `snapshot.py diff` proves the mirror with one more `--map C1_LE1=C3_LE1`.

## Integration test wiring (outside this repo)

Per-target inventories in `~/ansible_collections/cisco/inventory.nd_interface_ethernet_{access,trunk_host,routed}`:

```ini
nd_test_xe_fabric_name=CAMPUS1
nd_test_xe_switch_ip=192.168.12.181
```

Today those files point `nd_test_xe_*` at `ISN` / `WAN1`. They are switched once acceptance item 2 passes.

## Bringup order (on glide)

1. `sudo -E python3 startup_config.py --all` in `config/cat9kv/`.
2. `sudo python3 cat9kv.py --config C1_LE1.yaml`, same for `C3_LE1.yaml`; watch `./con_c1_le1` for
   `%SSH-5-ENABLED:` (up to 600 s).
3. `provision.py --topology topology_nd421.yaml --nd-ip 10.10.20.10 --phase fabrics`, then `--phase switches`;
   repeat with `topology_nd431.yaml --nd-ip 10.10.20.20`. Both phases are idempotent for the existing fabrics.
4. `snapshot.py dump` on both controllers, `snapshot.py diff` with the extended map.

## Acceptance

1. Each Cat9kv boots to `%SSH-5-ENABLED:` and answers SSH on its mgmt IP from glide.
2. `GET /api/v1/manage/fabrics/CAMPUS1/switches` on each controller lists the leaf with role `leaf`, status
   manageable, `networkOSType` `ios-xe`.
3. `GET .../switches/<serial>/interfaces` lists `GigabitEthernet1/0/1` with `policyType` `iosXeTrunkHost`.
4. The three `xe.yaml` scenarios pass on 4.2.1, then on 4.3.1 (run by the collection owner; not part of this
   repo's change).

## Out of scope

- A campus spine or any underlay adjacency.
- Extracting a shared IOS-XE launcher library from `config/8000v/` and `config/cat9kv/`.
- Copying anything from the CML refplat ISO into the repo (Cisco-internal material; only `vswitch.xml`, a 3 KB
  config file from the public node definition, is committed).
- NetBox population for the new devices (`config/netbox/` does not exist in this checkout).
