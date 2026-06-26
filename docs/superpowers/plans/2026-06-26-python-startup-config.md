# Python Startup-Config Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate each Nexus9000v switch's NX-OS startup-config and boot ISO in Python from the per-switch YAML the launcher already reads, replacing the Ansible `startup_config_iso.yaml` path (PR1 only — Ansible left intact as a fallback).

**Architecture:** Add day-0 fields (`mgmt_ip`, `mgmt_gw`) to each `config/nexus9000v/S*.yaml` and `nxos_boot_image` to `global_config.yaml`. A new `config/nexus9000v/startup_config.py` loads those YAMLs, renders a single co-located Jinja2 template `nxos_startup_config.j2`, and wraps the output in a per-switch ISO via `genisoimage` — byte-identical to the playbook's invocation. Data-plane interfaces are derived as `Ethernet1/1..N` where `N = len(isl_bridges)`. Admin password comes from `$NXOS_PASSWORD`.

**Tech Stack:** Python 3.13, PyYAML, Jinja2 (both already in `.venv` via Ansible), `genisoimage`/`mkisofs` (host tool).

## Global Constraints

- Line length **169** (`black`/`flake8`/`pylint` configured to it). Do not reformat to 79/88.
- **No test suite.** Validate Python with `mypy` and `flake8`, and by exercising the script + a parity diff vs the current playbook. Never claim "tests pass".
- Branch is `python-startup-config`; PR workflow — do not push to `main`.
- Do **not** modify the Ansible files, `nexus9000v-ovs.py` QEMU/MAC/disk logic, or `config/nd/` in this PR.
- Secrets: admin password is read from `$NXOS_PASSWORD` only; never write it into committed YAML.
- ISO invocation must match the playbook exactly: file `nxos_config.txt`, `genisoimage -o <hostname>.iso -l --iso-level 2 -V "<hostname>_CONFIG" nxos_config.txt`.
- Canonical boot image: `nxos64-cs.10.6.2.F.bin`.

### Per-switch day-0 data (migration source: `config/ansible/dynamic_inventory.py`)

Gateways: sites 1/2 → `192.168.12.1`; sites 3/4 → `192.168.14.1`. All masks `/24`.

| switch | mgmt_ip | mgmt_gw |
|---|---|---|
| S1_BG1 | 192.168.12.131/24 | 192.168.12.1 |
| S2_BG1 | 192.168.12.132/24 | 192.168.12.1 |
| S1_SP1 | 192.168.12.141/24 | 192.168.12.1 |
| S2_SP1 | 192.168.12.142/24 | 192.168.12.1 |
| S1_LE1 | 192.168.12.151/24 | 192.168.12.1 |
| S1_LE2 | 192.168.12.152/24 | 192.168.12.1 |
| S2_LE1 | 192.168.12.153/24 | 192.168.12.1 |
| S1_TOR1 | 192.168.12.161/24 | 192.168.12.1 |
| S3_BG1 | 192.168.14.131/24 | 192.168.14.1 |
| S4_BG1 | 192.168.14.132/24 | 192.168.14.1 |
| S3_SP1 | 192.168.14.141/24 | 192.168.14.1 |
| S4_SP1 | 192.168.14.142/24 | 192.168.14.1 |
| S3_LE1 | 192.168.14.151/24 | 192.168.14.1 |
| S4_LE1 | 192.168.14.152/24 | 192.168.14.1 |
| S4_LE2 | 192.168.14.153/24 | 192.168.14.1 |
| S4_LE3 | 192.168.14.154/24 | 192.168.14.1 |

---

### Task 1: Add `nxos_boot_image` to global config

**Files:**
- Modify: `config/nexus9000v/global_config.yaml`

**Interfaces:**
- Produces: `nxos_boot_image` key, consumed by `startup_config.py` (Task 3).

- [ ] **Step 1: Add the key**

In `config/nexus9000v/global_config.yaml`, add below the `default_image:` line:

```yaml
# NX-OS boot image written into each switch's startup-config (bootflash:/)
nxos_boot_image: nxos64-cs.10.6.2.F.bin
```

- [ ] **Step 2: Verify it parses**

Run: `python3 -c "import yaml; print(yaml.safe_load(open('config/nexus9000v/global_config.yaml'))['nxos_boot_image'])"`
Expected: `nxos64-cs.10.6.2.F.bin`

- [ ] **Step 3: Commit**

```bash
git add config/nexus9000v/global_config.yaml
git commit -m "Add nxos_boot_image to global_config.yaml"
```

---

### Task 2: Add `mgmt_ip` / `mgmt_gw` to all 16 per-switch YAMLs

**Files:**
- Modify: `config/nexus9000v/S1_BG1.yaml`, `S2_BG1.yaml`, `S1_SP1.yaml`, `S2_SP1.yaml`, `S1_LE1.yaml`, `S1_LE2.yaml`, `S2_LE1.yaml`, `S1_TOR1.yaml`, `S3_BG1.yaml`, `S4_BG1.yaml`, `S3_SP1.yaml`, `S4_SP1.yaml`, `S3_LE1.yaml`, `S4_LE1.yaml`, `S4_LE2.yaml`, `S4_LE3.yaml`

**Interfaces:**
- Produces: `mgmt_ip`, `mgmt_gw` keys in each switch YAML, consumed by `startup_config.py` (Task 3).

- [ ] **Step 1: Add the two keys to each file**

For each switch, add these two lines after the existing `mgmt_bridge:` line, using the values from the table in Global Constraints. Example for `config/nexus9000v/S1_BG1.yaml`:

```yaml
mgmt_ip: 192.168.12.131/24
mgmt_gw: 192.168.12.1
```

Repeat for all 16 files with their respective values. Do not add these to the `*.netplan.yaml` files (those are not switch launch configs).

- [ ] **Step 2: Verify every switch YAML now has both keys with a /24 mgmt_ip**

Run:
```bash
cd config/nexus9000v && for f in S1_BG1 S2_BG1 S1_SP1 S2_SP1 S1_LE1 S1_LE2 S2_LE1 S1_TOR1 S3_BG1 S4_BG1 S3_SP1 S4_SP1 S3_LE1 S4_LE1 S4_LE2 S4_LE3; do python3 -c "import yaml,sys; d=yaml.safe_load(open('$f.yaml')); assert d['mgmt_ip'].endswith('/24') and d['mgmt_gw']; print('$f', d['mgmt_ip'], d['mgmt_gw'])"; done
```
Expected: 16 lines, each printing the switch, its `/24` mgmt_ip, and its gateway; no assertion errors.

- [ ] **Step 3: Commit**

```bash
git add config/nexus9000v/S*.yaml
git commit -m "Add mgmt_ip/mgmt_gw day-0 fields to per-switch YAMLs"
```

---

### Task 3: Create the Jinja2 template

**Files:**
- Create: `config/nexus9000v/nxos_startup_config.j2`

**Interfaces:**
- Consumes (render context): `hostname`, `admin_password`, `boot_image`, `mgmt_gw`, `mgmt_ip`, `interfaces` (list of strings).
- Produces: the NX-OS startup-config text consumed by `render_config` (Task 4).

- [ ] **Step 1: Write the template**

Create `config/nexus9000v/nxos_startup_config.j2` with exactly this content (mirrors the `config/ansible/` template; `mgmt_ip` already carries the `/24`, and interfaces are looped):

```jinja
!Time: Fri Jul 25 10:00:00 2025
!Startup config saved at: Fri Jul 25 10:00:00 2025
configure terminal
hostname {{ hostname }}
no password strength-check
username admin password 0 {{ admin_password }} role network-admin
boot nxos bootflash:/{{ boot_image }}

vrf context management
  ip route 0.0.0.0/0 {{ mgmt_gw }}

interface mgmt0
  no cdp enable
  vrf member management
  ip address {{ mgmt_ip }}
  no shutdown

{% for intf in interfaces %}
interface {{ intf }}
    no shutdown

{% endfor %}
```

- [ ] **Step 2: Commit**

```bash
git add config/nexus9000v/nxos_startup_config.j2
git commit -m "Add unified NX-OS startup-config Jinja2 template"
```

---

### Task 4: Implement `startup_config.py` (load + render + ISO + CLI)

**Files:**
- Create: `config/nexus9000v/startup_config.py`

**Interfaces:**
- Consumes: `global_config.yaml` (`nxos_boot_image`, `cdrom_path`), per-switch YAML (`name`, `mgmt_ip`, `mgmt_gw`, `isl_bridges`), `nxos_startup_config.j2`, `$NXOS_PASSWORD`.
- Produces: CLI (`<yaml>`, `--all`, `--print <yaml>`); functions `load_global`, `load_switch`, `derive_interfaces`, `render_config`, `build_iso`.

- [ ] **Step 1: Write the module**

Create `config/nexus9000v/startup_config.py` with exactly this content:

```python
#!/usr/bin/env python3
"""Generate NX-OS day-0 startup-config and boot ISO for Nexus9000v switches.

Single source of truth: the per-switch YAML (S*.yaml) that nexus9000v-ovs.py
already reads, plus global_config.yaml. Renders nxos_startup_config.j2 and wraps
the result in a per-switch ISO (genisoimage), byte-compatible with the retired
startup_config_iso.yaml playbook. The admin password is read from $NXOS_PASSWORD.

Usage (ISO build writes to global_config.yaml cdrom_path, usually needs sudo):
    sudo python3 startup_config.py S1_BG1.yaml      # build one ISO
    sudo python3 startup_config.py --all            # build every S*.yaml ISO
    python3 startup_config.py --print S1_BG1.yaml   # render to STDOUT only
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
GLOBAL_CONFIG = HERE / "global_config.yaml"
TEMPLATE = "nxos_startup_config.j2"
DEFAULT_PASSWORD = "SuperSecretPassword"


def load_global(path: Path = GLOBAL_CONFIG) -> dict:
    """Load global_config.yaml."""
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_switch(path: Path) -> dict:
    """Load one per-switch YAML."""
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def derive_interfaces(switch: dict) -> list:
    """Data-plane interfaces to bring up: Ethernet1/1..N for N isl_bridges."""
    count = len(switch.get("isl_bridges") or [])
    return [f"Ethernet1/{i}" for i in range(1, count + 1)]


def render_config(switch: dict, boot_image: str, password: str, env: Environment) -> str:
    """Render the NX-OS startup-config text for one switch."""
    context = {
        "hostname": switch["name"],
        "admin_password": password,
        "boot_image": boot_image,
        "mgmt_ip": switch["mgmt_ip"],
        "mgmt_gw": switch["mgmt_gw"],
        "interfaces": derive_interfaces(switch),
    }
    return env.get_template(TEMPLATE).render(**context)


def _iso_tool() -> str:
    for tool in ("genisoimage", "mkisofs"):
        if subprocess.run(["which", tool], capture_output=True, check=False).returncode == 0:
            return tool
    raise FileNotFoundError("Neither genisoimage nor mkisofs found; install genisoimage")


def build_iso(config_text: str, hostname: str, out_dir: Path) -> Path:
    """Write config_text as nxos_config.txt and wrap it in <hostname>.iso."""
    out_dir.mkdir(parents=True, exist_ok=True)
    iso_path = out_dir / f"{hostname}.iso"
    tool = _iso_tool()
    with tempfile.TemporaryDirectory() as staging:
        cfg = Path(staging) / "nxos_config.txt"
        cfg.write_text(config_text, encoding="utf-8")
        subprocess.run(
            [tool, "-o", str(iso_path), "-l", "--iso-level", "2", "-V", f"{hostname}_CONFIG", str(cfg)],
            check=True,
            capture_output=True,
        )
    return iso_path


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(HERE)), undefined=StrictUndefined, keep_trailing_newline=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate NX-OS startup-config / boot ISO.")
    parser.add_argument("yaml", nargs="?", help="Per-switch YAML (e.g. S1_BG1.yaml)")
    parser.add_argument("--all", action="store_true", help="Build ISOs for every S*.yaml in this dir")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Render to STDOUT; build nothing")
    args = parser.parse_args()

    gcfg = load_global()
    boot_image = gcfg["nxos_boot_image"]
    out_dir = Path(gcfg.get("cdrom_path", "/iso2/nxos/config"))
    password = os.environ.get("NXOS_PASSWORD", DEFAULT_PASSWORD)
    env = _env()

    if args.all:
        targets = sorted(HERE.glob("S*.yaml"))
        targets = [t for t in targets if not t.name.endswith(".netplan.yaml")]
    elif args.yaml:
        targets = [Path(args.yaml) if Path(args.yaml).is_absolute() else HERE / args.yaml]
    else:
        parser.error("provide a switch YAML or --all")

    for path in targets:
        switch = load_switch(path)
        text = render_config(switch, boot_image, password, env)
        if args.print_only:
            print(text)
            continue
        iso = build_iso(text, switch["name"], out_dir)
        print(f"Built {iso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x config/nexus9000v/startup_config.py`

- [ ] **Step 3: Type-check and lint**

Run: `mypy config/nexus9000v/startup_config.py && flake8 config/nexus9000v/startup_config.py`
Expected: no errors. (Untyped `dict`/`list` returns are acceptable for this repo; fix only real errors.)

- [ ] **Step 4: Render one switch to STDOUT (no root needed)**

Run: `cd config/nexus9000v && ./startup_config.py --print S1_BG1.yaml`
Expected output contains:
```
hostname S1_BG1
boot nxos bootflash:/nxos64-cs.10.6.2.F.bin
  ip route 0.0.0.0/0 192.168.12.1
  ip address 192.168.12.131/24
interface Ethernet1/1
interface Ethernet1/2
```

- [ ] **Step 5: Verify interface derivation on a multi-ISL switch**

Run: `cd config/nexus9000v && ./startup_config.py --print S4_SP1.yaml | grep -c "no shutdown"`
Expected: `5` (mgmt0 + Ethernet1/1..4).

- [ ] **Step 6: Commit**

```bash
git add config/nexus9000v/startup_config.py
git commit -m "Add startup_config.py: render NX-OS day-0 config + build ISO from YAML"
```

---

### Task 5: Parity check against the current playbook

**Files:**
- None modified (verification only). Optionally create a throwaway script under the scratchpad; do not commit it.

**Interfaces:**
- Consumes: `startup_config.py --print` output and the playbook's rendered config.

- [ ] **Step 1: Render the playbook's config for comparison**

On a host with Ansible + the env sourced, generate the playbook's `.cfg` files into a temp dir by running the playbook with `output_dir` overridden, OR copy an existing generated `/iso2/nxos/config/S1_BG1.cfg`. Capture the playbook's `boot`, `ip route`, `ip address`, and `interface`/`no shutdown` lines for `S1_BG1`.

- [ ] **Step 2: Diff against the Python output**

Run: `cd config/nexus9000v && ./startup_config.py --print S1_BG1.yaml`
Compare to the playbook output. Expected: identical except `boot nxos bootflash:/...` now reflects `nxos_boot_image`.

- [ ] **Step 3: Confirm the documented deliberate differences on the right switches**

- `S1_LE1`, `S1_SP1`, `S4_SP1`: Python output has more `interface Ethernet1/N` / `no shutdown` stanzas than the playbook (all ISL links up). Confirm counts match `len(isl_bridges)` (3, 3, 4 respectively).
- Any switch previously built via `config/ansible_local/`: Python output now includes the `vrf context management` default route and the `username` line.

Record the confirmed differences in the PR description. No commit (verification only).

---

### Task 6: Build and validate a real ISO

**Files:**
- None committed (produces an ISO in `cdrom_path`).

- [ ] **Step 1: Build one ISO**

Run: `cd config/nexus9000v && sudo NXOS_PASSWORD="$NXOS_PASSWORD" ./startup_config.py S1_BG1.yaml`
Expected: `Built /iso2/nxos/config/S1_BG1.iso`

- [ ] **Step 2: Inspect ISO contents and volume label**

Run: `isoinfo -d -i /iso2/nxos/config/S1_BG1.iso | grep -i "Volume id"; isoinfo -l -i /iso2/nxos/config/S1_BG1.iso | grep -i nxos`
Expected: `Volume id: S1_BG1_CONFIG` and a listing containing `NXOS_CONFIG.TXT;1`.

- [ ] **Step 3 (optional, lab): boot a switch from the Python-built ISO**

Launch S1_BG1 with `nexus9000v-ovs.py` and confirm it comes up with hostname `S1_BG1`, mgmt IP `192.168.12.131`, and is reachable from ND. (Manual lab validation; not scripted.)

---

### Task 7: Document and open the PR

**Files:**
- Modify: `docs/n9kv_bringup.md`

**Interfaces:**
- Consumes: all prior tasks.

- [ ] **Step 1: Update the bringup doc**

In `docs/n9kv_bringup.md`, replace the section that instructs running the Ansible `startup_config_iso.yaml` playbook with the Python flow: edit `mgmt_ip`/`mgmt_gw` in the per-switch YAML and `nxos_boot_image` in `global_config.yaml`, then `sudo python3 startup_config.py --all` (or per-switch). Mention `--print <switch>.yaml` to view a config. Note the Ansible playbook still exists as a fallback (to be retired in a follow-up PR).

- [ ] **Step 2: Lint the markdown**

Run: `pymarkdown scan docs/n9kv_bringup.md`
Expected: no errors (run `pymarkdown fix docs/n9kv_bringup.md` then re-scan if needed).

- [ ] **Step 3: Commit**

```bash
git add docs/n9kv_bringup.md
git commit -m "Document Python startup-config workflow"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin python-startup-config
gh pr create --title "Generate NX-OS startup-config + ISO in Python from per-switch YAML" --body "<summary + parity-check results from Task 5>"
```

---

## Self-Review

**Spec coverage:**
- YAML schema additions (`nxos_boot_image`, `mgmt_ip`, `mgmt_gw`): Tasks 1–2. ✓
- `startup_config.py` (load/render/ISO/printer/CLI): Task 4. ✓
- Single Jinja2 template, fuller form: Task 3. ✓
- Interfaces derived from `isl_bridges`: `derive_interfaces` (Task 4), verified Task 4 Step 5. ✓
- Password from `$NXOS_PASSWORD`: Task 4. ✓
- Byte-compatible ISO invocation: `build_iso` (Task 4), validated Task 6. ✓
- Parity check + documented deliberate differences: Task 5. ✓
- Ansible untouched (PR1 scope): no task modifies it. ✓
- Docs: Task 7. ✓

**Placeholder scan:** Only `<summary + parity-check results>` in Task 7 Step 4 (PR body, filled from Task 5 at PR time) and the manual lab step (Task 6 Step 3, inherently manual). All code/template steps contain complete content.

**Type consistency:** `load_global`, `load_switch`, `derive_interfaces`, `render_config`, `build_iso`, `_iso_tool`, `_env`, `main` defined once in Task 4. Template context keys (`hostname`, `admin_password`, `boot_image`, `mgmt_ip`, `mgmt_gw`, `interfaces`) match Task 3's template variables exactly. YAML keys (`name`, `mgmt_ip`, `mgmt_gw`, `isl_bridges`, `nxos_boot_image`, `cdrom_path`) are consistent across Tasks 1, 2, 4.
