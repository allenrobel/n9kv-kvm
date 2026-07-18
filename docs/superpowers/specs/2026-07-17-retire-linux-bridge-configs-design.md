# Retire Linux-Bridge Configs (OVS Transition, Part 2) — Design

Date: 2026-07-17
Status: Approved

## Purpose

The lab runs on Open vSwitch: both VM launchers (`nexus9000v.py`, `8000v.py`)
attach TAPs with `ovs-vsctl`, which requires OVS bridges, and the LXC
containers were moved to OVS in Part 1 (PR #20). But the repo still carries the
Linux-bridge era: a parallel set of Linux bridge-config files and an
authoritative bringup doc (`docs/bridges.md`) that documents creating **Linux**
bridges. That doc contradicts the actual runtime requirement and is the root of
recurring confusion. Part 2 retires the dead Linux artifacts and makes OVS the
single documented path.

This is **Part 2**, deferred from the container OVS migration
(`docs/superpowers/specs/2026-07-17-containers-ovs-migration-design.md`).

## Canonical bridge-creation path (Approach A: layered)

Two OVS mechanisms are complementary layers, not competitors, and both are
kept:

- `config/bridges/netplan/9912-bridges.yaml` (+ `9914`/`9915`) — netplan OVS
  variants (`openvswitch: {}`, MTU 9216, `stp: false`) create the bridges
  declaratively and persist them across reboot.
- `config/bridges/bridges_config_ovs.sh` — creates any missing bridge and sets
  `other-config:forward-bpdu=true` + `mtu_request` (the netplan variant does
  not set `forward-bpdu`, which LACP/vPC needs). Its header documents that it
  is meant to run after netplan to re-assert these. `nexus9000v.py` also
  re-asserts `forward-bpdu` per-port at each VM launch.

## Retire (delete)

- `config/bridges/9912-bridges.yaml`, `config/bridges/9914-bridges.yaml`,
  `config/bridges/9915-bridges.yaml` — the **top-level** Linux netplan variants
  (no `openvswitch:` key; they would create plain Linux bridges the launchers
  cannot attach to). The OVS variants under `config/bridges/netplan/` are the
  keepers.
- `config/bridges/bridges_config_linux.sh` — Linux-bridge create script.
- `config/bridges/bridge.conf` — the qemu bridge-helper allowlist. The
  launchers pre-create OVS TAPs and never invoke the built-in bridge helper, so
  this file is vestigial; nothing programmatic references it (verified — only
  `docs/bridges.md` and `README.md` mention it).

## Doc / reference reconciliation

1. **`docs/bridges.md`** (the authoritative bringup guide, linked from
   `README.md`) — rewrite to the OVS flow:
   - Delete the entire `bridge.conf` / `/etc/qemu` section (lines 3-31).
   - Point the netplan copy step at `config/bridges/netplan/9912-bridges.yaml`
     (the OVS variant) instead of the deleted top-level file.
   - Add a step to run `sudo ./bridges_config_ovs.sh` after `netplan apply`, so
     `forward-bpdu` is set on every bridge before any VM launches.
   - Replace the Linux verification (`ip link show type bridge | grep BR_`,
     with Linux-bridge example output) with OVS verification
     (`sudo ovs-vsctl list-br`, `sudo ovs-vsctl show`).
2. **`config/bridges/netplan/9912-bridges.yaml` header comment** — fix its
   self-referential copy command (line 6:
   `sudo cp .../config/bridges/9912-bridges.yaml ...`) to point at the
   `netplan/` path that now holds it. (`9914`/`9915` netplan variants have no
   such self-reference — verified.)
3. **`docs/manual_vpc_bringup_s1.md`** — fix dangling references:
   - Lines 19-20: `bridges_config.sh` (never existed) → `bridges_config_ovs.sh`;
     `config/bridges/9912-bridges.yaml` → `config/bridges/netplan/9912-bridges.yaml`.
   - Line 65 and line 92: references to `add_vlans_BR_S1_LE1_H1_1.sh` (deleted
     in PR #20). Reword to describe the VLANs directly (the container-side
     tagging is what matters now); drop the script reference.
4. **`README.md`** — refresh the `config/bridges` directory tree (lines
   ~324-333). It is already stale: it lists `bridges_config.sh` (does not
   exist), `add_vlans_*`/`vlans_del_*` (deleted in PR #20), `9912-bridges.yaml`
   and `bridge.conf` (deleted here), and omits `bridges_config_linux.sh`
   (deleted here), `bridges_config_ovs.sh`, and the `netplan/` subdirectory.
   Replace it with the real post-retirement file set.

## Out of scope

- Making netplan self-sufficient for `forward-bpdu` — the script owns that by
  design.
- Any behavioral change to `bridges_config_ovs.sh`, `bridges_down.sh`, or
  `bridges_monitor.sh`.
- The `cockpit/` bridge-monitor extension.
- The `docs/superpowers/` specs and plans that mention the retired files — these
  are historical record and are left as-is.

## Validation (no lab host, no test suite)

- A repo-wide grep (excluding `docs/superpowers/` and `.git`) for
  `bridges_config_linux`, `bridge.conf`, `add_vlans`, `vlans_del`, and the
  top-level path `config/bridges/9912-bridges.yaml` returns **zero** matches.
- The five retired files are gone; the kept netplan YAMLs still `yaml.safe_load`
  and `bash -n` is clean on the kept scripts.
- `pymarkdown scan` is clean on `docs/bridges.md`,
  `docs/manual_vpc_bringup_s1.md`, and `README.md`.
- Every file path named in the rewritten `docs/bridges.md` exists in the repo
  (no new dangling references introduced).
