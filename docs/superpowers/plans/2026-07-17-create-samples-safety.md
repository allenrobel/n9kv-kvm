# Safe `--create-samples` + Refreshed Samples — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `--create-samples` in both VM launchers write to a `samples/` subdirectory (never the working files), skip existing files unless `--force`, and
emit samples that carry the full current schema — closing the footgun that silently overwrote real switch YAMLs with field-incomplete ones.

**Architecture:** Each launcher gets a small `_write_sample(path, data, force)` helper and a `create_sample_configs(force=False)` that writes into
`Path("samples")`. `main()` gains a `--force` flag passed through. The nexus sample content is refreshed to a self-contained single-site topology
(BG → spine → vPC leaf pair → dual-homed TOR) with `mgmt_ip`/`mgmt_gw` on every switch and `nxos_boot_image` in the global sample. The two launchers stay
independent standalone mirrors (the helper is duplicated, not shared — matching repo convention). Spec:
`docs/superpowers/specs/2026-07-17-create-samples-safety-design.md`.

**Tech Stack:** Python 3.13, PyYAML, argparse.

## Global Constraints

- Line-length limit **169** (black/flake8/pylint). Do not reflow.
- **No test suite exists** (CLAUDE.md). Validate with a scratch-directory behavior test (shown per task), `mypy`, `flake8`, and `pymarkdown`. Never claim
  "tests pass."
- **mypy baseline:** `config/nexus9000v/nexus9000v.py` has **one pre-existing** mypy error at line 652 (`Popen[bytes]` vs `Popen[str]`) unrelated to this
  work — leave it; the change must add **no new** mypy errors. `config/8000v/8000v.py` is mypy-clean and must stay clean. Both launchers are flake8-clean and
  must stay clean.
- The two launchers are deliberately **standalone mirrors** — duplicate the `_write_sample` helper in each; do not extract a shared module.
- Never touch anything under `env_prod/`.
- Work on branch `fix-create-samples-safety`; commit after every task; do not push to `main`.
- Use the repo venv at `.venv/bin/`.

## File-change map

| File | Change | Task |
|------|--------|------|
| `config/nexus9000v/nexus9000v.py` | `_write_sample` helper; `create_sample_configs(force=False)` → `samples/` + skip/force + new topology; `main()` `--force` | 1 |
| `config/nexus9000v/README.md` | Document `samples/` + `--force` | 1 |
| `config/8000v/8000v.py` | `_write_sample` helper; `create_sample_configs(force=False)` → `samples/` + skip/force (WAN1 unchanged); `main()` `--force` | 2 |
| `config/8000v/README.md` | Document `samples/` + `--force` | 2 |

---

### Task 1: nexus9000v.py — safe samples + refreshed topology + README

**Files:**

- Modify: `config/nexus9000v/nexus9000v.py` (the `create_sample_configs` function at lines 682-769, and `main()` argparse + dispatch at lines 781, 787-789)
- Modify: `config/nexus9000v/README.md` (the "Display sample configs" section, lines 18-23)

**Interfaces:**

- Consumes: nothing from other tasks.
- Produces: `create_sample_configs(force: bool = False)` writes `samples/global_config.yaml` and `samples/S*.yaml`; `main()` accepts `--force`. Module-level
  helper `_write_sample(path: Path, data: dict, force: bool) -> None`.

- [ ] **Step 1: Demonstrate the bug (RED) — current code clobbers a real file in cwd**

Run:

```bash
SCRATCH=$(mktemp -d) && cd "$SCRATCH"
printf 'SENTINEL: do-not-touch\n' > S1_BG1.yaml
/Users/arobel/repos/n9kv-kvm/.venv/bin/python /Users/arobel/repos/n9kv-kvm/config/nexus9000v/nexus9000v.py --create-samples >/dev/null 2>&1
grep -q SENTINEL S1_BG1.yaml && echo "sentinel survived" || echo "RED: current code CLOBBERED the real S1_BG1.yaml in cwd"
cd /Users/arobel/repos/n9kv-kvm && rm -rf "$SCRATCH"
```

Expected (RED): `RED: current code CLOBBERED the real S1_BG1.yaml in cwd`.

- [ ] **Step 2: Add the `_write_sample` helper and rewrite `create_sample_configs`**

Replace the entire existing `create_sample_configs` function (lines 682-769) with:

```python
def _write_sample(path: Path, data: dict, force: bool) -> None:
    """Write one sample YAML to path, skipping it if it already exists unless force."""
    if path.exists() and not force:
        print(f"Skipping existing {path} (use --force to overwrite)")
        return
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    print(f"Created {path}")


def create_sample_configs(force: bool = False):
    """Create sample configuration files under ./samples/ (never the working dir).

    Existing files are skipped unless force is True. Writing into a samples/
    subdirectory keeps a stray run from clobbering the real per-switch YAMLs.
    """
    out_dir = Path("samples")
    out_dir.mkdir(parents=True, exist_ok=True)

    global_config = {
        "image_path": "/iso1/nxos",
        "cdrom_path": "/iso2/nxos/config",
        "bios_file": "/usr/share/ovmf/OVMF.fd",
        "default_image": "nexus9300v64.10.6.2.F.qcow2",
        "nxos_boot_image": "nxos64-cs.10.6.2.F.bin",
        "base_mac": "52:54:00",  # yaml.dump quotes this so it round-trips as a string
        "default_ram": 16384,
        "default_vcpus": 4,
        "default_disk_size": "32G",
        "default_interface_type": "e1000",
        "default_external_storage_size": "20G",
        "external_storage_enabled": True,
    }
    _write_sample(out_dir / "global_config.yaml", global_config, force)

    # A self-contained single-site topology: Border Gateway -> Spine ->
    # vPC leaf pair (S1_LE1 + S1_LE2, peer-linked) -> dual-homed TOR. Every
    # isl_bridge is a point-to-point link within this set.
    switches = [
        {
            "name": "S1_BG1",
            "role": "Border Gateway",
            "sid": 1301,
            "mgmt_bridge": "BR_ND_DATA_12",
            "mgmt_ip": "192.168.12.131/24",
            "mgmt_gw": "192.168.12.1",
            "neighbors": ["S1_SP1"],
            "isl_bridges": ["BR_S1_BG1_SP1_1"],
        },
        {
            "name": "S1_SP1",
            "role": "Spine Switch",
            "sid": 1401,
            "mgmt_bridge": "BR_ND_DATA_12",
            "mgmt_ip": "192.168.12.141/24",
            "mgmt_gw": "192.168.12.1",
            "neighbors": ["S1_BG1", "S1_LE1", "S1_LE2"],
            "isl_bridges": ["BR_S1_BG1_SP1_1", "BR_S1_SP1_LE1_1", "BR_S1_SP1_LE2_1"],
        },
        {
            "name": "S1_LE1",
            "role": "Leaf Switch",
            "sid": 1501,
            "mgmt_bridge": "BR_ND_DATA_12",
            "mgmt_ip": "192.168.12.151/24",
            "mgmt_gw": "192.168.12.1",
            "neighbors": ["S1_SP1", "S1_LE2", "S1_TOR1"],
            "isl_bridges": ["BR_S1_SP1_LE1_1", "BR_S1_LE1_LE2_1", "BR_S1_LE1_T1_1"],
        },
        {
            "name": "S1_LE2",
            "role": "Leaf Switch",
            "sid": 1502,
            "mgmt_bridge": "BR_ND_DATA_12",
            "mgmt_ip": "192.168.12.152/24",
            "mgmt_gw": "192.168.12.1",
            "neighbors": ["S1_SP1", "S1_LE1", "S1_TOR1"],
            "isl_bridges": ["BR_S1_SP1_LE2_1", "BR_S1_LE1_LE2_1", "BR_S1_LE2_T1_1"],
        },
        {
            "name": "S1_TOR1",
            "role": "Top-of-Rack Switch",
            "sid": 1601,
            "mgmt_bridge": "BR_ND_DATA_12",
            "mgmt_ip": "192.168.12.161/24",
            "mgmt_gw": "192.168.12.1",
            "neighbors": ["S1_LE1", "S1_LE2"],
            "isl_bridges": ["BR_S1_LE1_T1_1", "BR_S1_LE2_T1_1"],
        },
    ]

    for switch in switches:
        _write_sample(out_dir / f"{switch['name']}.yaml", switch, force)
```

- [ ] **Step 3: Add `--force` to `main()` and pass it through**

In `main()`, after the `--create-samples` argument line (currently line 781):

```python
    parser.add_argument("--create-samples", action="store_true", help="Create sample config files")
```

add:

```python
    parser.add_argument("--force", action="store_true", help="Overwrite existing sample files (used with --create-samples)")
```

Then change the dispatch (currently lines 787-789):

```python
    if args.create_samples:
        create_sample_configs()
        return
```

to:

```python
    if args.create_samples:
        create_sample_configs(force=args.force)
        return
```

- [ ] **Step 4: Verify behavior (GREEN) — isolation, keys, skip, force**

Run:

```bash
SCRATCH=$(mktemp -d) && cd "$SCRATCH"
printf 'SENTINEL: do-not-touch\n' > S1_BG1.yaml
cp S1_BG1.yaml S1_BG1.yaml.orig
NX=/Users/arobel/repos/n9kv-kvm/config/nexus9000v/nexus9000v.py
PY=/Users/arobel/repos/n9kv-kvm/.venv/bin/python
$PY "$NX" --create-samples
echo "--- samples written ---"; ls samples/
echo "--- top-level sentinel untouched? ---"; diff S1_BG1.yaml S1_BG1.yaml.orig && echo "SENTINEL UNTOUCHED"
echo "--- required keys present? ---"
$PY - <<'PYEOF'
import glob, yaml
g = yaml.safe_load(open("samples/global_config.yaml"))
assert "nxos_boot_image" in g, "global sample missing nxos_boot_image"
files = sorted(glob.glob("samples/S*.yaml"))
assert len(files) == 5, f"expected 5 switch samples, got {len(files)}"
for f in files:
    s = yaml.safe_load(open(f))
    assert "mgmt_ip" in s and "mgmt_gw" in s, f"{f} missing mgmt_ip/mgmt_gw"
print("KEYS OK (5 switches, all have mgmt_ip/mgmt_gw; global has nxos_boot_image)")
PYEOF
echo "--- second run skips existing ---"
$PY "$NX" --create-samples | grep -q "Skipping existing" && echo "SKIP OK"
echo "--- --force overwrites ---"
$PY "$NX" --create-samples --force | grep -q "Created samples/global_config.yaml" && echo "FORCE OK"
cd /Users/arobel/repos/n9kv-kvm && rm -rf "$SCRATCH"
```

Expected: `samples written` lists `global_config.yaml S1_BG1.yaml S1_LE1.yaml S1_LE2.yaml S1_SP1.yaml S1_TOR1.yaml`; then `SENTINEL UNTOUCHED`,
`KEYS OK (...)`, `SKIP OK`, `FORCE OK`.

- [ ] **Step 5: Round-trip a generated sample through the day-0 generator**

This proves the refreshed sample actually renders (the original bug was `KeyError` here). Run:

```bash
SCRATCH=$(mktemp -d) && cd "$SCRATCH"
DIR=/Users/arobel/repos/n9kv-kvm/config/nexus9000v
PY=/Users/arobel/repos/n9kv-kvm/.venv/bin/python
$PY "$DIR/nexus9000v.py" --create-samples >/dev/null
NXOS_PASSWORD=TestPassword $PY "$DIR/startup_config.py" --print "$SCRATCH/samples/S1_LE1.yaml" \
  | grep -E "hostname S1_LE1|interface Ethernet1/3"
cd /Users/arobel/repos/n9kv-kvm && rm -rf "$SCRATCH"
```

Expected: prints `hostname S1_LE1` and `interface Ethernet1/3` (3 ISL bridges → Ethernet1/1..1/3), i.e. no `KeyError` on `mgmt_ip`. (The generator reads
`nxos_boot_image` from the committed `config/nexus9000v/global_config.yaml`, which has it — the sample-global check in Step 4 covers the sample side.)

- [ ] **Step 6: Type-check and lint**

```bash
.venv/bin/mypy config/nexus9000v/nexus9000v.py 2>&1 | tail -2
.venv/bin/flake8 config/nexus9000v/nexus9000v.py && echo "flake8 clean"
```

Expected: mypy reports exactly the **one pre-existing** error at line 652 (`Popen[bytes]`/`Popen[str]`) and no others (the line number may shift by the number
of lines your edit added/removed — it is the same single Popen error, not a new one); flake8 prints nothing then `flake8 clean`.

- [ ] **Step 7: Update `config/nexus9000v/README.md`**

Replace the "Display sample configs" section (currently lines 18-23):

````text
### Display sample configs

```bash
python3 nexus9000v.py --create-samples
```
````

with:

````text
### Create sample configs

Writes a sample `global_config.yaml` and a small example topology (a
single-site Border Gateway → Spine → vPC leaf pair → TOR) into a `samples/`
subdirectory — never the working directory. Existing files are skipped unless
`--force` is given.

```bash
python3 nexus9000v.py --create-samples          # write to ./samples/, skip existing
python3 nexus9000v.py --create-samples --force  # overwrite existing samples
```
````

Then lint:

```bash
.venv/bin/pymarkdown scan config/nexus9000v/README.md
```

Expected: exit 0, no output. Fix any MD0xx findings (line-length 169).

- [ ] **Step 8: Commit**

```bash
git add config/nexus9000v/nexus9000v.py config/nexus9000v/README.md
git commit -m "Make nexus9000v --create-samples safe and refresh sample topology

Write samples into ./samples/ (never the working dir), skip existing files
unless --force, and emit a self-contained single-site topology whose switch
samples carry mgmt_ip/mgmt_gw and whose global sample carries nxos_boot_image
so the day-0 startup_config flow no longer KeyErrors on generated samples."
```

---

### Task 2: 8000v.py — safe samples + README

**Files:**

- Modify: `config/8000v/8000v.py` (the `create_sample_configs` function and `main()` argparse + dispatch)
- Modify: `config/8000v/README.md` (the `--create-samples` line in "Other operations", line 45)

**Interfaces:**

- Consumes: nothing from Task 1 (independent standalone mirror; its own duplicated `_write_sample`).
- Produces: `create_sample_configs(force: bool = False)` writes `samples/global_config.yaml` and `samples/WAN1.yaml`; `main()` accepts `--force`.

- [ ] **Step 1: Demonstrate the bug (RED)**

```bash
SCRATCH=$(mktemp -d) && cd "$SCRATCH"
printf 'SENTINEL: do-not-touch\n' > WAN1.yaml
/Users/arobel/repos/n9kv-kvm/.venv/bin/python /Users/arobel/repos/n9kv-kvm/config/8000v/8000v.py --create-samples >/dev/null 2>&1
grep -q SENTINEL WAN1.yaml && echo "sentinel survived" || echo "RED: current code CLOBBERED the real WAN1.yaml in cwd"
cd /Users/arobel/repos/n9kv-kvm && rm -rf "$SCRATCH"
```

Expected (RED): `RED: current code CLOBBERED the real WAN1.yaml in cwd`.

- [ ] **Step 2: Add `_write_sample` and rewrite `create_sample_configs`**

Replace the entire existing `create_sample_configs` function with (WAN1 content unchanged — it already has `mgmt_ip`/`mgmt_gw`; only the write path and
skip/force behavior change):

```python
def _write_sample(path: Path, data: dict, force: bool) -> None:
    """Write one sample YAML to path, skipping it if it already exists unless force."""
    if path.exists() and not force:
        print(f"Skipping existing {path} (use --force to overwrite)")
        return
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    print(f"Created {path}")


def create_sample_configs(force: bool = False):
    """Create sample configuration files under ./samples/ (never the working dir).

    Existing files are skipped unless force is True. Writing into a samples/
    subdirectory keeps a stray run from clobbering the real per-router YAMLs.
    """
    out_dir = Path("samples")
    out_dir.mkdir(parents=True, exist_ok=True)

    global_config = {
        "image_path": "/iso1/iosxe",
        "cdrom_path": "/iso2/iosxe/config",
        "bios_file": "/usr/share/ovmf/OVMF.fd",
        "default_image": "c8000v-universalk9_16G_serial_efi.17.15.05.qcow2",
        "base_mac": "52:54:00",  # yaml.dump quotes this so it round-trips as a string
        "default_ram": 8192,
        "default_vcpus": 4,
        "default_interface_type": "virtio-net-pci",
    }
    _write_sample(out_dir / "global_config.yaml", global_config, force)

    routers = [
        {
            "name": "WAN1",
            "role": "WAN Router",
            "sid": 9101,
            "mgmt_bridge": "BR_ND_DATA_12",
            "mgmt_ip": "192.168.12.112/24",
            "mgmt_gw": "192.168.12.1",
            "neighbors": ["S1_BG1", "S2_BG1"],
            "isl_bridges": ["BR_ISN_WAN_S1_1", "BR_ISN_WAN_S2_1"],
        },
    ]

    for router in routers:
        _write_sample(out_dir / f"{router['name']}.yaml", router, force)
```

- [ ] **Step 3: Add `--force` to `main()` and pass it through**

After the `--create-samples` argument line:

```python
    parser.add_argument("--create-samples", action="store_true", help="Create sample config files")
```

add:

```python
    parser.add_argument("--force", action="store_true", help="Overwrite existing sample files (used with --create-samples)")
```

Then change the dispatch:

```python
    if args.create_samples:
        create_sample_configs()
        return
```

to:

```python
    if args.create_samples:
        create_sample_configs(force=args.force)
        return
```

- [ ] **Step 4: Verify behavior (GREEN)**

```bash
SCRATCH=$(mktemp -d) && cd "$SCRATCH"
printf 'SENTINEL: do-not-touch\n' > WAN1.yaml
cp WAN1.yaml WAN1.yaml.orig
V8=/Users/arobel/repos/n9kv-kvm/config/8000v/8000v.py
PY=/Users/arobel/repos/n9kv-kvm/.venv/bin/python
$PY "$V8" --create-samples
echo "--- samples written ---"; ls samples/
echo "--- top-level sentinel untouched? ---"; diff WAN1.yaml WAN1.yaml.orig && echo "SENTINEL UNTOUCHED"
echo "--- required keys present? ---"
$PY - <<'PYEOF'
import yaml
w = yaml.safe_load(open("samples/WAN1.yaml"))
assert "mgmt_ip" in w and "mgmt_gw" in w, "WAN1 sample missing mgmt fields"
print("KEYS OK (WAN1 has mgmt_ip/mgmt_gw)")
PYEOF
echo "--- second run skips ---"; $PY "$V8" --create-samples | grep -q "Skipping existing" && echo "SKIP OK"
echo "--- --force overwrites ---"; $PY "$V8" --create-samples --force | grep -q "Created samples/WAN1.yaml" && echo "FORCE OK"
cd /Users/arobel/repos/n9kv-kvm && rm -rf "$SCRATCH"
```

Expected: `samples written` lists `WAN1.yaml global_config.yaml`; then `SENTINEL UNTOUCHED`, `KEYS OK (...)`, `SKIP OK`, `FORCE OK`.

- [ ] **Step 5: Type-check and lint**

```bash
.venv/bin/mypy config/8000v/8000v.py
.venv/bin/flake8 config/8000v/8000v.py && echo "flake8 clean"
```

Expected: mypy `Success: no issues found in 1 source file`; flake8 prints nothing then `flake8 clean`.

- [ ] **Step 6: Update `config/8000v/README.md`**

Change the `--create-samples` line in the "Other operations" block (line 45):

```text
python3 8000v.py --create-samples               # write sample global_config.yaml + WAN1.yaml
```

to:

```text
python3 8000v.py --create-samples               # write samples to ./samples/ (skip existing)
python3 8000v.py --create-samples --force        # overwrite existing samples
```

Then lint:

```bash
.venv/bin/pymarkdown scan config/8000v/README.md
```

Expected: exit 0, no output. Fix any MD0xx findings (line-length 169).

- [ ] **Step 7: Commit**

```bash
git add config/8000v/8000v.py config/8000v/README.md
git commit -m "Make c8000v --create-samples safe

Write samples into ./samples/ (never the working dir) and skip existing files
unless --force, mirroring the nexus9000v launcher fix. WAN1 sample content is
unchanged (it already carries mgmt_ip/mgmt_gw)."
```
