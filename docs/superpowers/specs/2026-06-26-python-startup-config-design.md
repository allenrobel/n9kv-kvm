# Design: Python Startup-Config Generation from Per-Switch YAML

Date: 2026-06-26
Supersedes: `2026-06-26-nxos-image-single-source-design.md` (the Ansible-based
`nxos_image` fix). That narrower change is subsumed here.

## Problem

The lab no longer uses the `cisco.dcnm` Ansible collection to build the testbed
— VXLAN/EVPN fabric configuration now happens through Cisco Nexus Dashboard,
driven from a **separate** repository based on the `cisco.nd` collection
(<https://github.com/CiscoDevNet/ansible-nd>). What remains here is bringing up
the VMs and their day-0 bootstrap. The Ansible machinery in `config/ansible/`
and `config/ansible_local/` is now mostly historical.

Within the VM-bringup path, each switch is currently described **twice**:

| | Launcher side (`config/nexus9000v/S*.yaml`) | Ansible side (`dynamic_inventory.py`) |
|---|---|---|
| fields | `name`, `role`, `sid`, `mgmt_bridge`, `neighbors`, `isl_bridges` | `hostname`, `mgmt_ip`, interface names, boot `.bin`, gateway, password |
| format | per-switch YAML (read by `nexus9000v-ovs.py`) | env-var defaults in a Python inventory |

The launcher (`nexus9000v-ovs.py`) is already a clean Python config system
(`GlobalConfig` + `SwitchConfig`, deterministic MAC generation, disk creation,
QEMU assembly). It even references the boot ISO (`{cdrom_path}/{name}.iso`) — it
just does not create it. The ISO is built by the Ansible `startup_config_iso.yaml`
playbook from the *other* data source. There are even two image strings:
`global_config.yaml` `default_image: nexus9300v64.10.6.2.F.qcow2` (the disk) and
the startup-config's `nxos64-cs.10.6.2.F.bin` (the boot image) — same version,
two places.

So the real duplication is the entire switch roster, and Ansible is only here for
historical reasons.

## Goals

1. Make the per-switch YAML (already read by the launcher) the **single source
   of truth** for a switch's day-0 bootstrap.
2. Generate the startup-config and its boot ISO in **Python**, producing
   byte-equivalent results to today's playbook output (so existing VMs boot
   identically).
3. Fold in the earlier "print the generated config to STDOUT" utility as a mode
   of the new tool (replacing the deleted static `cfg/` reference files).

## Non-goals / boundary

- **This repo = VMs + day-0 bootstrap** (just enough for ND to reach each
  switch: hostname, mgmt IP/gateway, boot image, data-plane interfaces up).
  **The separate `ansible-nd` repo = everything ND drives** (VXLAN/EVPN
  overlay, VRFs, networks). Day-0 bootstrap must stay here because ND cannot
  configure a switch it cannot reach.
- Do **not** remove the Ansible files in this PR. Retiring
  `startup_config_iso.yaml` + templates + the inventory bits that served it is
  **PR2**; archiving the historical `cisco.dcnm` playbooks is a later cleanup.
  This keeps PR1 focused and reversible.
- Do not change `config/nd/` (ND appliance VM launch) — still required.
- Do not change the QEMU/MAC/disk logic in `nexus9000v-ovs.py`.

## Design (PR1)

### 1. YAML schema additions — the single source of truth

`global_config.yaml` gains the boot image (placed next to the qcow2 so the two
versions stay visibly consistent):

```yaml
# NX-OS boot image written into each switch's startup-config (bootflash:/)
nxos_boot_image: nxos64-cs.10.6.2.F.bin
```

Each per-switch YAML (e.g. `S1_BG1.yaml`) gains its two genuinely per-switch
day-0 values:

```yaml
mgmt_ip: 192.168.12.131/24   # mgmt0 address (CIDR)
mgmt_gw: 192.168.12.1        # management default route next-hop
```

The data-plane interfaces to bring up are **derived**, not listed: they are
`Ethernet1/1 .. Ethernet1/N` where `N = len(isl_bridges)`. This is already an
invariant of the model (the launcher creates exactly one NIC per ISL bridge, and
`len(neighbors) == len(isl_bridges)` is enforced), so deriving avoids a third
list to keep in sync. Migration values for `mgmt_ip`/`mgmt_gw` come from the
existing `*_IP4` defaults in `dynamic_inventory.py` (sites 1/2 gateway
`192.168.12.1`, sites 3/4 `192.168.14.1`).

The admin password is **not** stored in YAML — it is read from the `NXOS_PASSWORD`
environment variable at render time (same as today), defaulting to a placeholder
if unset.

### 2. `startup_config.py` — renderer + ISO builder + printer

A new module in `config/nexus9000v/` with a small, testable surface:

- `load_global(path) -> dict` — read `global_config.yaml`.
- `load_switch(path) -> dict` — read one per-switch YAML.
- `render_config(switch: dict, boot_image: str, password: str) -> str` —
  produce the NX-OS startup-config text. Uses a single Jinja2 template
  `nxos_startup_config.j2` (co-located), the superset template (hostname,
  password, boot image, mgmt0 address, management VRF default route via
  `mgmt_gw`, and `no shutdown` for each derived data-plane interface).
- `build_iso(config_text: str, hostname: str, out_dir: Path) -> Path` — write
  the text as `nxos_config.txt` and wrap it in `{hostname}.iso` via
  `genisoimage`/`mkisofs` with `-l --iso-level 2 -V "{hostname}_CONFIG"`
  (byte-for-byte the playbook's invocation, so NX-OS POAP consumes it
  identically).
- CLI (run via `sudo python3 startup_config.py ...` since `/iso2` needs root):
  - `startup_config.py <SWITCH>.yaml` — build that switch's ISO.
  - `startup_config.py --all` — build ISOs for every `S*.yaml` in the dir.
  - `startup_config.py --print <SWITCH>.yaml` — render to STDOUT, build nothing
    (the reference/printer mode; no root needed).

Output dir defaults to `global_config.yaml`'s `cdrom_path` (`/iso2/nxos/config`).

**Known deliberate difference:** the two current templates disagree — the
`config/ansible/` template emits a management-VRF default route (and
`username`/`no password strength-check`), while the simpler `config/ansible_local/`
template omits them. The unified template adopts the **fuller** `config/ansible/`
form for all switches, so SITE1/SITE2 switches previously built via
`ansible_local` will gain a default route and the username line. This is
intended (ND reachability is more robust with the route) and must be confirmed
during the parity check.

### 3. Optional launcher hook (kept minimal)

`nexus9000v-ovs.py` already errors if the ISO is missing. PR1 leaves the build
as a separate step (matching today's "build configs, then launch" workflow). A
follow-up may add a `--make-iso` flag that calls `startup_config.build_iso`; out
of scope for PR1.

## Verification (no test suite; per CLAUDE.md use mypy/flake8 + exercise)

- `mypy` + `flake8` on `startup_config.py` (line length 169).
- **Parity check:** for each switch, compare the Python `--print` output against
  the config the current playbook generates (run the playbook into a temp dir,
  diff `nxos_config.txt`). They should match except for the intentional change
  (boot image now from `nxos_boot_image`). Document any deliberate differences.
- Build one ISO with the Python tool and confirm `isoinfo -l` shows
  `NXOS_CONFIG.TXT;1` and volume id `<HOST>_CONFIG`, matching a playbook ISO.
- Boot one switch (lab host) from a Python-built ISO and confirm it comes up
  with the right hostname, mgmt IP, and reachability from ND.

## Decomposition / rollout

- **PR1 (this spec):** YAML schema additions + `startup_config.py` + single
  template + populate `S*.yaml` with `mgmt_ip`/`mgmt_gw`. Ansible untouched and
  still functional as a fallback.
- **PR2:** retire the Ansible startup-config path (`startup_config_iso.yaml`,
  the two `.j2` copies, inventory entries that only served it). Update docs.
- **PR3 (later):** archive or delete the historical `cisco.dcnm` playbooks under
  `config/ansible*`.

Branch for PR1: `python-startup-config`.
