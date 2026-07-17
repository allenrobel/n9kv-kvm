# C8000V (IOS-XE) Launcher Design

Date: 2026-07-17
Status: Approved

## Purpose

Bring up a Cisco Catalyst 8000V (IOS-XE 17.15.05) VM in the lab as a new WAN/ISN
router, using the image `c8000v-universalk9_16G_serial_efi.17.15.05.qcow2`
(Serial console + EFI boot variant). The bringup mirrors the existing
`config/nexus9000v/` pattern: a YAML-driven QEMU launcher plus a day-0
startup-config generator that builds a bootstrap ISO.

## Decisions

- **New device, not the existing `ER`.** The router is cross-site WAN/ISN
  infrastructure connecting to the border gateways over `BR_ISN_*`-style
  bridges. Sample device name: `WAN1` (cross-site infra carries no site
  prefix, consistent with `ER`).
- **Approach A: standalone mirror.** `config/8000v/` is self-contained,
  structurally mirroring `config/nexus9000v/` with no changes to the working
  n9kv launcher and no shared library. Revisit extraction of shared plumbing
  only if a third platform lands.
- **Full day-0 flow.** A `startup_config.py` renders `iosxe_config.txt` from
  the per-router YAML and wraps it in a CD-ROM ISO (the C8000V day-0
  bootstrap mechanism, analogous to the n9kv POAP ISO).
- **Paths.** Base image in `/iso1/iosxe`; per-VM artifacts (cloned qcow2,
  day-0 ISO) in `/iso2/iosxe/config`. Parallel tree to the nxos layout.

## Files (all new, under `config/8000v/`)

| File | Purpose |
|------|---------|
| `8000v.py` | Launcher: loads global + per-router YAML, creates TAPs, attaches them to OVS, builds and starts QEMU. Same CLI flags as the n9kv launcher. |
| `startup_config.py` | Renders the IOS-XE day-0 config from the per-router YAML; builds the boot ISO via `genisoimage` (`iosxe_config.txt` inside). |
| `iosxe_startup_config.j2` | Day-0 Jinja2 template. |
| `global_config.yaml` | Global defaults (see below). |
| `WAN1.yaml` | Sample per-router config. |
| `con_wan1`, `ssh_wan1` | One-liner console/SSH helpers, same style as `con_s1_bg1` etc. |
| `README.md` | Usage doc for the subsystem. |

## Configuration schema

`global_config.yaml`:

```yaml
image_path: /iso1/iosxe
cdrom_path: /iso2/iosxe/config
bios_file: /usr/share/ovmf/OVMF.fd
default_image: c8000v-universalk9_16G_serial_efi.17.15.05.qcow2
base_mac: "52:54:00"
default_ram: 8192          # MB; C8000V minimum is 4096
default_vcpus: 4
default_interface_type: virtio-net-pci
```

Per-router YAML — identical keys to the n9kv schema for uniformity:

```yaml
name: WAN1
role: WAN Router
sid: 9101                  # 9xxx range, clear of site-prefixed 1xxx-4xxx switch sids
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.112/24
mgmt_gw: 192.168.12.1
neighbors:                 # paired with isl_bridges, len must match
  - S1_BG1
  - S2_BG1
isl_bridges:               # key name kept for schema parity with n9kv
  - BR_ISN_WAN_S1_1
  - BR_ISN_WAN_S2_1
# optional overrides: ram, vcpus, disk_size, interface_type, image_name
```

Constraints and derivations (same semantics as the n9kv launcher):

- `sid` is 4-digit (1000-9999); telnet console = `10000 + sid`, QEMU monitor
  = `20000 + sid`.
- MACs derived from `sid` + `base_mac` via the same `StandardMACGenerator`
  scheme (mgmt = port 0, data = port 1..N).
- `len(neighbors) == len(isl_bridges)` enforced.
- Bridges are referenced, not created; they must already exist (created via
  `config/bridges/`). Bridge names respect IFNAMSIZ (15 chars).
- No external-storage disk (n9kv-only concept; dropped here).

## Interface mapping

IOS-XE numbers NICs flatly in PCI order:

- Index 0 → `GigabitEthernet1` = management, on `mgmt_bridge`.
- Index 1..N → `GigabitEthernet2..N+1`, one per `isl_bridges` entry.

TAP naming: `tap<sid>-<index>` (e.g. `tap9101-0`), same as n9kv, ≤15 chars.

## QEMU command (`C8000vQEMUBuilder`)

- `-machine type=q35,accel=kvm,kernel-irqchip=on`, `-cpu host`,
  `-enable-kvm`, `-smp`/`-m`/`-numa` same shape as the n9kv builder.
- `-bios /usr/share/ovmf/OVMF.fd` — required; the image is the EFI variant.
- `-smbios` product string `C8000V` (cosmetic parity).
- Disk: per-VM copy of the base qcow2 to `/iso2/iosxe/config/<name>.qcow2`
  (`cp`; no resize by default — optional `disk_size` triggers
  `qemu-img resize`). Attached via AHCI (`ide-hd`, `bootindex=1`).
- Day-0 ISO attached as cdrom (`-drive file=<name>.iso,media=cdrom`).
- NICs: `virtio-net-pci` default (`interface_type` overridable, e.g.
  `e1000`). TAPs pre-created by `OVSPortManager` — MTU 9216,
  `other-config:forward-bpdu=true`, `script=no,downscript=no`.
- Console: serial image variant → `-nographic`,
  `-serial telnet:localhost:<10000+sid>,server=on,wait=off`,
  `-monitor telnet:localhost:<20000+sid>,server,nowait`, `-rtc
  clock=host,base=localtime`, `-name <name>`.

## Day-0 template (`iosxe_startup_config.j2`)

Renders:

- `hostname <name>`.
- Management isolated from the global routing table: `vrf definition MGMT`
  (address-family ipv4), `GigabitEthernet1` in vrf MGMT with `mgmt_ip`
  and `no shutdown`, plus `ip route vrf MGMT 0.0.0.0 0.0.0.0 <mgmt_gw>`.
  The global table stays clean for later WAN/ISN routing config.
- `username admin privilege 15 secret <password>` — password from
  `$IOSXE_PASSWORD`, falling back to `$NXOS_PASSWORD` so existing env
  scripts work unchanged. `startup_config.py` errors out if neither is set.
- SSH: `ip domain name lab.local` (hardcoded in the template), `ip ssh
  version 2`, `line vty 0 4` with
  `login local` and `transport input ssh`.
- RSA keypair: a one-shot EEM applet that runs at boot, executes
  `crypto key generate rsa modulus 2048` in enable mode, removes itself
  from the config, and saves. (Key generation is an exec command and cannot
  appear directly in a config file.)
- Data interfaces `GigabitEthernet2..N`: `no shutdown` only. WAN/ISN
  addressing and routing are post-bringup work, consistent with the repo's
  bringup-vs-fabric-config boundary.

## Error handling

Same pattern as the n9kv launcher:

- OVS bridge existence checked via `ovs-vsctl br-exists`; missing bridge →
  clear error pointing at `config/bridges/`.
- BIOS file and base image existence validated before launch.
- `--dry-run` prints the full QEMU command, interface/MAC/TAP table, and
  ports without touching the host.
- `--teardown` removes the router's TAP interfaces after the VM is stopped.
- Idempotent TAP setup: stale taps/ports of the same name are cleared first.

## Validation

No test suite exists in this repo. Validate with `mypy` and `flake8`
(line length 169), `--dry-run` output inspection, and live bringup on the
lab host.
