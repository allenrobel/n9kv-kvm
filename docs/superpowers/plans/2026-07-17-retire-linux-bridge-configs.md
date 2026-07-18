# Retire Linux-Bridge Configs (OVS Transition, Part 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the dead Linux-bridge config files and make Open vSwitch the single documented bridge-bringup path, so the authoritative doc matches what the
launchers actually require.

**Architecture:** Approach A (layered OVS) from the spec
(`docs/superpowers/specs/2026-07-17-retire-linux-bridge-configs-design.md`): keep `config/bridges/netplan/*-bridges.yaml` (declarative OVS, boot-persistent)
plus `bridges_config_ovs.sh` (asserts `forward-bpdu`/MTU). Delete the top-level Linux netplan YAMLs, `bridges_config_linux.sh`, and `bridge.conf`; rewrite
`docs/bridges.md` to the OVS flow; fix every dangling reference to the deleted files.

**Tech Stack:** Markdown docs, netplan (OVS), bash, Open vSwitch. No application code changes.

## Global Constraints

- **No test suite / no lab host here.** Validate with `pymarkdown scan`, `yaml.safe_load`, `bash -n`, and repo-wide `grep` for dangling references. Never claim
  "tests pass."
- Markdown must pass `.venv/bin/pymarkdown scan <file>` (line-length limit 169).
- Never touch anything under `env_prod/`.
- Leave `docs/superpowers/` specs and plans as-is — they are historical record and legitimately mention the retired files.
- Do not change the behavior of `bridges_config_ovs.sh`, `bridges_down.sh`, or `bridges_monitor.sh`.
- Work on branch `retire-linux-bridge-configs` (already based on current `origin/main`); commit after every task; do not push to `main`.
- Use the repo venv at `.venv/bin/`.

## File-change map

| File | Change | Task |
|------|--------|------|
| `docs/bridges.md` | Rewrite from the Linux-netplan+bridge.conf flow to the OVS flow | 1 |
| `config/bridges/9912-bridges.yaml`, `9914-bridges.yaml`, `9915-bridges.yaml` | Delete (top-level Linux netplan variants) | 2 |
| `config/bridges/bridges_config_linux.sh` | Delete | 2 |
| `config/bridges/bridge.conf` | Delete | 2 |
| `config/bridges/netplan/9912-bridges.yaml` | Fix self-referential copy-path comment (line 6) | 2 |
| `docs/manual_vpc_bringup_s1.md` | Fix dangling refs (lines 19-20, 65, 92) | 2 |
| `README.md` | Refresh the `config/bridges` directory tree | 2 |

Task 1 goes first so that `docs/bridges.md` no longer references `bridge.conf` — that lets Task 2's final repo-wide "no dangling references" grep pass.

---

### Task 1: Rewrite `docs/bridges.md` to the OVS flow

**Files:**

- Modify: `docs/bridges.md` (full rewrite)

**Interfaces:**

- Consumes: nothing.
- Produces: an OVS bringup doc that references only files that exist post-retirement (`config/bridges/netplan/9912-bridges.yaml`, `bridges_config_ovs.sh`).
  No later task depends on its content.

- [ ] **Step 1: Replace the entire contents of `docs/bridges.md` with:**

````markdown
# Setup Bridges

The lab's data-plane bridges are Open vSwitch (OVS) bridges. The VM launchers
(`config/nexus9000v/nexus9000v.py` and `config/8000v/8000v.py`) attach each
VM's TAP interfaces to these bridges with `ovs-vsctl`, so the bridges must be
OVS bridges, not Linux bridges.

Two layers create and configure them:

- **netplan** (`config/bridges/netplan/9912-bridges.yaml`) creates the bridges
  declaratively and persists them across reboot (MTU 9216, `stp: false`).
- **`bridges_config_ovs.sh`** asserts the OVS settings netplan does not set —
  notably `other-config:forward-bpdu=true`, which LACP / vPC peer-links need,
  plus the jumbo `mtu_request` — and creates any bridge that is missing.

## Configure netplan

Inspect and edit the OVS bridge definitions to match your host:

<!-- pyml disable-next-line commands-show-output -->
```text
$HOME/repos/n9kv-kvm/config/bridges/netplan/9912-bridges.yaml
```

In particular, verify that:

- The physical interface exists. Change the interface name (`eno6` in the file)
  to match your host — see the `link` parameter for `Vlan12`. Check your
  interfaces with `ip link show`.
- Vlan 12 is not already associated with your interface (the `id` parameter for
  `Vlan12`).
- The bridge names (e.g. `BR_ND_DATA_12`, `BR_S1_BG1_SP1_1`) don't conflict with
  existing bridges on your host.
- The IP address (`192.168.12.2/24` on `BR_ND_DATA_12`) doesn't conflict with
  other addresses on your host or network.

## Copy the bridges configuration into /etc/netplan

```bash
cd $HOME/repos/n9kv-kvm/config/bridges/netplan
sudo cp ./9912-bridges.yaml /etc/netplan
sudo chmod 600 /etc/netplan/9912-bridges.yaml
```

## Apply the bridges configuration

```bash
sudo netplan try
sudo netplan apply
```

`netplan try` may warn that reverting custom parameters for bridges is not
supported; proceed with `netplan apply` directly. If netplan warns that
`/etc/netplan/*` permissions are too open, tighten them and re-apply:

```bash
sudo chown root /etc/netplan/*
sudo chmod 600 /etc/netplan/*
```

## Assert the OVS settings

Run the OVS config script to set `forward-bpdu`, the jumbo MTU, and create any
bridge netplan did not. It is idempotent, so it is safe to re-run.

```bash
cd $HOME/repos/n9kv-kvm/config/bridges
sudo ./bridges_config_ovs.sh
```

## Verify

```bash
# List the OVS bridges
sudo ovs-vsctl list-br | grep BR_

# Full OVS state (bridges, ports, MTU)
sudo ovs-vsctl show
```

The bridges have no ports until you bring up the VMs; each launcher creates the
VM's TAP interfaces and attaches them to their bridges at launch.
````

- [ ] **Step 2: Lint**

```bash
.venv/bin/pymarkdown scan docs/bridges.md
```

Expected: exit 0, no output. Fix any MD0xx findings (line-length 169). If MD031/MD040 fire on the nested ` ```text ` block, ensure it stays a single fenced
block surrounded by blank lines with a language tag.

- [ ] **Step 3: Confirm the doc references only files that exist**

```bash
grep -oE "config/bridges/[A-Za-z0-9_./-]+" docs/bridges.md | sort -u | while read p; do
  test -e "$p" && echo "OK  $p" || echo "MISSING  $p"
done
```

Expected: every line starts with `OK` (paths `config/bridges/netplan/9912-bridges.yaml` and `config/bridges/bridges_config_ovs.sh` both exist). No `MISSING`.

- [ ] **Step 4: Commit**

```bash
git add docs/bridges.md
git commit -m "Rewrite bridges setup doc for the OVS flow

Drop the Linux-bridge / qemu bridge.conf path; document creating OVS bridges
via the netplan OVS variant plus bridges_config_ovs.sh, and verify with
ovs-vsctl."
```

---

### Task 2: Delete the Linux artifacts and fix every dangling reference

**Files:**

- Delete: `config/bridges/9912-bridges.yaml`, `config/bridges/9914-bridges.yaml`, `config/bridges/9915-bridges.yaml`,
  `config/bridges/bridges_config_linux.sh`, `config/bridges/bridge.conf`
- Modify: `config/bridges/netplan/9912-bridges.yaml` (header comment, line 6)
- Modify: `docs/manual_vpc_bringup_s1.md` (lines 19-20, 65, 92)
- Modify: `README.md` (the `config/bridges` directory tree)

**Interfaces:**

- Consumes: Task 1 (so `docs/bridges.md` no longer references `bridge.conf`, letting the final grep pass).
- Produces: a repo with no references to the deleted files outside `docs/superpowers/`.

- [ ] **Step 1: Delete the five Linux artifacts**

```bash
git rm config/bridges/9912-bridges.yaml \
       config/bridges/9914-bridges.yaml \
       config/bridges/9915-bridges.yaml \
       config/bridges/bridges_config_linux.sh \
       config/bridges/bridge.conf
```

- [ ] **Step 2: Fix the self-referential copy path in `config/bridges/netplan/9912-bridges.yaml`**

Line 6 currently reads:

```text
# sudo cp $HOME/repos/n9kv-kvm/config/bridges/9912-bridges.yaml /etc/netplan/9912-bridges.yaml
```

Change it to point at this file's own `netplan/` location:

```text
# sudo cp $HOME/repos/n9kv-kvm/config/bridges/netplan/9912-bridges.yaml /etc/netplan/9912-bridges.yaml
```

- [ ] **Step 3: Fix the dangling references in `docs/manual_vpc_bringup_s1.md`**

(a) Lines 19-20 currently read:

```text
  (created by `config/bridges/bridges_config.sh` and applied via
  `config/bridges/9912-bridges.yaml`):
```

Change to (the script never existed under that name; the applied file is the OVS netplan variant):

```text
  (created by netplan from `config/bridges/netplan/9912-bridges.yaml` and
  configured by `config/bridges/bridges_config_ovs.sh`):
```

(b) Line 65 currently reads:

```text
  Matches `config/bridges/add_vlans_BR_S1_LE1_H1_1.sh`. Easy to widen.
```

Change to (that script was deleted in PR #20; the container now tags these VLANs itself):

```text
  These VLANs carry the host container's test traffic. Easy to widen.
```

(c) Line 92 currently reads:

```text
! VLANs for test traffic (matches add_vlans_BR_S1_LE1_H1_1.sh)
```

Change to:

```text
! VLANs for test traffic (tagged by the host container)
```

- [ ] **Step 4: Refresh the `config/bridges` directory tree in `README.md`**

The tree block currently reads (stale — lists a `bridges_config.sh` that never existed, the PR #20-deleted `add_vlans_*`/`vlans_del_*` scripts, and the
files deleted in this task):

```text
│   ├── bridges
│   │   ├── 9912-bridges.yaml
│   │   ├── add_vlans_BR_S1_LE1_H1_1.sh
│   │   ├── add_vlans_BR_S2_LE1_H1_1.sh
│   │   ├── bridge.conf
│   │   ├── bridges_config.sh
│   │   ├── bridges_down.sh
│   │   ├── bridges_monitor.sh
│   │   ├── vlans_del_BR_S1_LE1_H1_1.sh
│   │   └── vlans_del_BR_S2_LE1_H1_1.sh
```

Replace it with the real post-retirement file set (keep the box-drawing indentation style of the surrounding tree exactly):

```text
│   ├── bridges
│   │   ├── bridges_config_ovs.sh
│   │   ├── bridges_down.sh
│   │   ├── bridges_monitor.sh
│   │   └── netplan
│   │       ├── 50-cloud-init.yaml
│   │       ├── 9912-bridges.yaml
│   │       ├── 9914-bridges.yaml
│   │       └── 9915-bridges.yaml
```

- [ ] **Step 5: Verify no dangling references remain and kept files are intact**

```bash
echo "--- dangling references (expect NO output) ---"
grep -rn -e bridges_config_linux -e "bridge\.conf" -e add_vlans -e vlans_del -e "config/bridges/9912-bridges\.yaml" . 2>/dev/null \
  | grep -v "\.git/" | grep -v "docs/superpowers/"
echo "--- deleted files gone (expect all 'gone') ---"
for f in config/bridges/9912-bridges.yaml config/bridges/9914-bridges.yaml config/bridges/9915-bridges.yaml \
         config/bridges/bridges_config_linux.sh config/bridges/bridge.conf; do
  test -e "$f" && echo "STILL PRESENT: $f" || echo "gone: $f"
done
echo "--- kept netplan YAMLs still parse ---"
.venv/bin/python -c "import yaml, glob; [yaml.safe_load(open(f)) for f in glob.glob('config/bridges/netplan/99*-bridges.yaml')]; print('YAML OK')"
echo "--- kept scripts pass bash -n ---"
bash -n config/bridges/bridges_config_ovs.sh && bash -n config/bridges/bridges_down.sh && bash -n config/bridges/bridges_monitor.sh && echo "bash OK"
```

Expected: the dangling-reference grep prints **nothing**; all five files report `gone:`; `YAML OK`; `bash OK`.

- [ ] **Step 6: Lint the changed markdown**

```bash
.venv/bin/pymarkdown scan docs/manual_vpc_bringup_s1.md README.md
```

Expected: exit 0, no output. Fix any MD0xx findings introduced by the edits (line-length 169).

- [ ] **Step 7: Commit**

```bash
git add config/bridges/netplan/9912-bridges.yaml docs/manual_vpc_bringup_s1.md README.md
git commit -m "Retire Linux-bridge config files and fix dangling references

Delete the top-level Linux netplan YAMLs, bridges_config_linux.sh, and
bridge.conf; repoint the netplan OVS variant's copy comment, the SITE1 vPC
bringup doc, and the README config/bridges tree at the surviving OVS files."
```

(The `git rm` deletions from Step 1 are already staged, so this commit includes them alongside the reference fixes.)
