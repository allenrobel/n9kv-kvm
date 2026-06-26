# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is **not** a deployable software project. It is a collection of scripts, configs, playbooks, and docs used to bring up a multi-site VXLAN lab built
from Cisco Nexus Dashboard (ND) + Cisco Nexus9000v VMs running on an Ubuntu 24.04 KVM/libvirt host. The lab topology, intended audience, and full install
procedure live in `README.md` and `docs/`. Treat changes here as lab infrastructure tweaks — most files are run on (or copied to) a specific Ubuntu lab
host, not a generic dev environment.

## Environment Setup

The project assumes you have sourced the environment before running anything. Two parallel environment trees exist:

- `env/` — primary/dev environment (safe to commit)
- `env_prod/` — production lab host environment. **NEVER commit `env_prod/`.** It contains real passwords and other secrets that must not be made public.
  Treat it as untracked-only: do not `git add env_prod/`, do not include it in a `git add -A` / `git add .`, and do not stage individual files inside it. If
  a future change needs to share *structure* from `env_prod/`, copy the relevant file into `env/` with secrets stripped and commit that instead.

Source one of them (they wire up `VIRTUAL_ENV`, Ansible vars, `LIBVIRT_DEFAULT_URI`, and `PYTHONPATH`):

```bash
source env/env.sh        # or: source env_prod/env.sh
```

Key variables these set (do not hardcode — read from env when possible):

- `ND_IP4`, `ND_USERNAME`, `ND_PASSWORD`, `ND_FABRIC_*` — Nexus Dashboard target + fabric names
- `ANSIBLE_COLLECTIONS_PATH` points at `$HOME/repos/ansible/collections` (the Cisco `cisco.nd` collection is expected to be checked out there)
- `LIBVIRT_DEFAULT_URI=qemu:///system` — switch to `qemu:///session` only if virt-manager was started as non-root

The `dynamic_inventory.py` files under `config/ansible/` and `config/ansible_local/` build their entire inventory from these env vars, falling back to
hardcoded defaults. Changing IPs/credentials should be done via the env scripts, not the inventory.

## Tooling

- Python 3.13 (see `.python-version`); deps managed with `uv` (`uv.lock` present, `pyproject.toml` is the source of truth).
- Line length is **169** everywhere — `black`, `flake8`, and `pylint` are all configured to it in `pyproject.toml` / `.flake8`. Don't reformat to PEP 8's 79/88 default.
- No test suite exists. Don't claim "tests pass" — there are none to run. Validate Python changes with `mypy`, `flake8`, and by exercising the script against
  the lab (or `--dry-run` where supported).
- Use `pymarkdown scan <file>` to ensure Markdown files are formatted correctly and `pymarkdown fix <file>` to fix.

```bash
# Lint / type-check a module
mypy config/nexus9000v/nexus9000v.py
flake8 config/containers/
black --check config/
```

## High-Level Layout

The repo is organized by **lab subsystem**, not by language. Each subdir is largely self-contained:

<!-- pyml disable-num-lines 12 line-length -->
| Path | What it does |
|------|--------------|
| `config/nexus9000v/` | YAML per-switch configs (S1_BG1, S1_SP1, S1_LE1, …) + `nexus9000v.py` which reads `global_config.yaml` + a per-switch YAML and invoke `virt-install` / QEMU. `con_*` and `ssh_*` are one-liner helpers that telnet/ssh to each switch's serial console or mgmt IP. |
| `config/nd/` | Shell scripts that run `virt-install` for each ND release/node combination (e.g. `nd-42-1-4-node1.sh`). One script == one ND VM. Versions in filenames are intentional; do not consolidate. |
| `config/ansible/` and `config/ansible_local/` | Each now contains only a `dynamic_inventory.py` (env-var-driven inventory; `ansible/` covers SITE1–SITE4, `ansible_local/` covers SITE1/SITE2 + the edge router). The former `cisco.dcnm` fabric playbooks were removed — fabric/overlay config now happens through Nexus Dashboard from a separate `ansible-nd` repo. The inventories are retained for ad-hoc use and as the canonical source of per-switch IPs/interfaces. |
| `config/containers/` | A Python package (no `__init__.py`, run via `main.py`) implementing SOLID-style orchestration for creating libvirt-LXC "host" containers (e.g. `S1_H1`, `S2_H1`) used as endpoint hosts on the leaves. See `config/containers/README.md` for the module breakdown and usage. Entry point: `sudo python3 main.py --config <yaml> <CONTAINER_NAME>`. |
| `config/bridges/` | Shell + netplan YAML that provisions the Linux bridges (`BR_ND_DATA_12`, `BR_S1_LE1_H1_1`, etc.) connecting all the VMs. `bridges_config.sh` (re)creates them; the `*-bridges.yaml` are netplan variants. MTU 9216 is intentional (VXLAN overhead). |
| `monitor/` | Ad hoc operator scripts (`show_bridges`, `show_nd_interfaces`, …) for inspecting the lab from the host. |
| `cockpit/` | Two optional Cockpit extensions (bridge monitor, n9kv monitor) installed onto the lab host. Each has its own README. |
| `docs/` | The authoritative step-by-step bringup guide; `README.md` is essentially an index into `docs/`. |

## Architectural Notes That Aren't Obvious From Browsing

- **Switch identity is encoded in YAML `sid` + `base_mac`.** `nexus9000v.py` derives per-interface MAC addresses deterministically from `sid` (1–255) and the
  `52:54:00` OUI; bridges named in `mgmt_bridge` / `isl_bridges` must already exist on the host (see `config/bridges/`). The constraint
  `len(neighbors) == len(isl_bridges)` is enforced — these are paired lists, not independent.
- **The startup-config flow is Python, sourced from the per-switch YAML.** `config/nexus9000v/startup_config.py` reads `global_config.yaml`
  (`nxos_boot_image`) + a per-switch `S*.yaml` (`mgmt_ip`, `mgmt_gw`, `isl_bridges`), renders `config/nexus9000v/nxos_startup_config.j2`, and wraps the
  output in a per-switch ISO via `genisoimage`. The n9kv VM mounts that ISO as a cdrom on first boot and NX-OS POAP/auto-config consumes it. Data-plane
  interfaces are derived as `Ethernet1/1..N` for `N = len(isl_bridges)`; the admin password comes from `$NXOS_PASSWORD`. So changing bootstrap behavior
  means editing the per-switch YAML or that Jinja template, not the launch script.
- **`config/ansible/` vs `config/ansible_local/`** are not "remote vs local" — both are localhost env-var-driven inventories that target different fabrics
  (`ansible/` covers SITE1–SITE4; `ansible_local/` covers SITE1/SITE2 + the edge router). Don't merge them.
- **ND has multiple coexisting versions** (`nd_321e.sh`, `nd_411g.sh`, `nd-42-1-*-node*.sh`, …). Each is a distinct VM definition; the lab can run several
  ND clusters simultaneously on different bridges. The numeric suffixes (`.105`, `.119`, `.4`) are the management IP last octet, not version numbers.
- **`n9kv-kvm/` subdirectory at the repo root** is a stray Python venv (note `pyvenv.cfg`, `bin/`, `lib/`), not source. The real venv is `.venv/`. Ignore
  `n9kv-kvm/` for code reading.

## Conventions

- Lab IPs, fabric names, and credentials are read from environment variables with hardcoded fallbacks in `dynamic_inventory.py`. When adding a new
  switch/device, update both the dynamic inventory and the env scripts.
- Switch/host hostnames encode site explicitly: `S<site>_<role><idx>` (e.g. `S1_BG1`, `S2_SP1`, `S1_LE1`, `S1_H1`, `S1_TOR1`). Roles: `BG` (border gateway),
  `SP` (spine), `LE` (leaf), `TOR` (top-of-rack), `H` (host container). Indices renumber per-site starting at 1. Bridge names are subject to the Linux
  IFNAMSIZ limit (15 chars), so they use shorter codes than hostnames: intra-site bridges follow `BR_S<site>_<upper>_<lower>_<n>` with the higher-tier
  endpoint first (BG > SP > LE > T) — note `TOR` is shortened to `T` in bridge names only (e.g. hostname `S1_TOR1` ↔ bridge `BR_S1_LE1_T1_1`). The
  link-index suffix `_<n>` is always present. Same-tier peer bridges sort endpoints alphabetically/numerically. Cross-site (ISN) bridges use
  `BR_ISN_S<a>_S<b>_<n>` (the per-side BG identifier is omitted; each site is assumed to have one BG today). Shared management bridges (`BR_ND_DATA_12`,
  `BR_ND_DATA_14`, `BR_ND_MGMT`) are not site-prefixed.
- Shell scripts assume `sudo` where needed; don't `sudo` inside the script unless it's already the pattern there (`bridges_config.sh` expects to be invoked
  with sudo; the `config/nd/*.sh` scripts invoke `sudo virt-install` internally).
