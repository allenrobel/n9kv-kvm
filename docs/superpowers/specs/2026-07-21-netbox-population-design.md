# NetBox Population from n9kv-kvm YAML — Design

Date: 2026-07-21
Status: approved

## Purpose

Populate the NetBox instance on glide (<http://glide.arobel.com:8000>, rootless Podman, NetBox 4.6.5)
with the lab topology, parsed from this repo's authoritative YAML — no hand-maintained inventory.
Re-runnable after topology changes.

## Script

`config/netbox/populate_netbox.py`, run from macOS:

```bash
source ~/.config/netbox/netbox.env   # NETBOX_URL + NETBOX_TOKEN (not committed)
uv run config/netbox/populate_netbox.py
```

`pynetbox` is a project dependency (uv). Idempotent upsert: get-or-create/update, never delete.
Prints created/updated/unchanged summary; a second run must report zero changes.

## Data sources

| Source | Yields |
|---|---|
| `config/nexus9000v/S*.yaml` (not `*.netplan.yaml`) | 18 n9kv switches: name, role, mgmt_ip, `neighbors[i]` + `isl_bridges[i]` → `Ethernet1/{i+1}` (launcher-verified) |
| `config/8000v/WAN1.yaml` | WAN1 (IOS-XE): `GigabitEthernet1` = mgmt, `GigabitEthernet{i+1}` = `isl_bridges[i-1]` (launcher-verified) |
| `config/containers/container_configs_access_mode.yaml` | S1_H1 / S2_H1: eth0 (mgmt) + eth1 (test) with IPs, bridges |
| Static entries in script | ND node (mgmt on `outside` @ 192.168.7.7, data on `BR_ND_DATA_12`), glide (hypervisor) |

## NetBox modeling

- **Sites**: SITE1–SITE4 (site group `n9kv-lab`; site = first token of device name), `Lab-Shared`
  for cross-site gear (WAN1, ND node, glide). S5/S6 excluded until per-VM YAMLs exist; a re-run
  then picks them up automatically.
- **Roles** (YAML `role` → NetBox slug): Border Gateway→`border-gateway`, Spine Switch→`spine`,
  Leaf Switch→`leaf`, Top-of-Rack Switch→`tor` (new), WAN Router→`wan-router` (new);
  containers→`host`, ND→`nd-node`, glide→`hypervisor`.
- **Device types**: switches→`Nexus9300v` (no YAML overrides the 9300v default image);
  WAN1→`Catalyst 8000V` (new); containers→`LXC container` (new, mfr Canonical);
  glide→`Ubuntu KVM host` (new, mfr Canonical). All virtual types u_height 0. **No serial numbers**
  (9000v serials change on reload).
- **Interfaces**: mgmt (`mgmt0`/`GigabitEthernet1`/`eth0`) marked mgmt-only; data interfaces type
  `1000base-t` (e1000 emulation). Interface description = attached bridge name.
- **Cables**: an ISL bridge shared by exactly two endpoints = one cable (label = bridge name).
  Shared segments (`BR_ND_DATA_*`, `outside`) get no cables — IPs only.
- **IPAM**: prefixes `192.168.12.0/24` (S1/S2 mgmt), `192.168.14.0/24` (S3/S4 mgmt),
  `192.0.1.0/24` (container test net). All parsed IPs bound to interfaces; device primary IP = mgmt IP.
- **Known conflict surfaced, not resolved**: S1_TOR1 and S1_H1 both claim `192.168.12.161` in the
  repo today. NetBox enforces uniqueness; the script reports the collision and continues.
  *Resolved 2026-07-21*: host containers renumbered out of the TOR block — S1_H1 → `.171`,
  S2_H1 → `.172` (mgmt, test IPs, and MACs all mirror the new octets).

## Verification

1. Run script; counts match sources (23 devices, 3 prefixes, ~60 interfaces, ~20 cables).
2. Spot-check in UI: SITE1 device list, a cable trace (S1_SP1 Eth1/2 ↔ S1_LE1 Eth1/1), IPAM prefix utilization.
3. Re-run → zero created/updated.
