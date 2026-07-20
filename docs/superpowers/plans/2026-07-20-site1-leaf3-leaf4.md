# SITE1 Second Leaf Pair (S1_LE3 / S1_LE4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan
task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add leaf switches S1_LE3 and S1_LE4 to the SITE1 fabric — three new OVS bridges, two per-switch YAMLs, S1_SP1 uplink expansion, console/ssh helpers, launch
script, and dynamic inventory entries.

**Architecture:** This repo brings up n9kv VMs as raw QEMU processes; each switch is defined by one YAML under `config/nexus9000v/` and its links are OVS bridges
pre-created on the host (netplan is canonical, `bridges_config_ovs.sh` is the idempotent fallback). `isl_bridges` is an ordered list — position N maps to
`Ethernet1/(N+1)` — and `len(neighbors) == len(isl_bridges)` is enforced. No fabric/overlay config lives here (that's the separate `ansible-nd` repo); this plan is day-0
bringup only.

**Tech Stack:** YAML switch configs consumed by `nexus9000v.py` / `startup_config.py`, netplan + Open vSwitch, bash helper scripts, env-var-driven Python dynamic inventory.

## Global Constraints

- New links (from the request, verbatim):
  - `S1_SP1.Eth1/4 --- S1_LE3.Eth1/1`
  - `S1_SP1.Eth1/5 --- S1_LE4.Eth1/1`
  - `S1_LE3.Eth1/2 --- S1_LE4.Eth1/2`
- Bridge names must be ≤ 15 chars (IFNAMSIZ). All three new names comply: `BR_S1_SP1_LE3_1` (15), `BR_S1_SP1_LE4_1` (15), `BR_S1_LE3_LE4_1` (15).
- Bridge naming: intra-site `BR_S<site>_<upper>_<lower>_<n>`, higher tier first (SP > LE); same-tier peers sort numerically (LE3 before LE4).
- sid scheme is `<site><role-digit>0<idx>` with leaf role digit 5: S1_LE1=1501, S1_LE2=1502 ⇒ **S1_LE3=1503, S1_LE4=1504** (verified unused across all `S*.yaml`; console
  ports become 11503/11504, monitor ports 21503/21504, MACs derive from sid so uniqueness matters).
- mgmt IP pool on `BR_ND_DATA_12` (192.168.12.0/24): .131/.132 = BGs, .141/.142 = SPs, .151 = S1_LE1, .152 = S1_LE2, .153 = **S2_LE1** (do not reuse), .161 = S1_TOR1 ⇒
  **S1_LE3 = 192.168.12.154, S1_LE4 = 192.168.12.155**.
- MTU 9216 on all fabric bridges (VXLAN overhead) — copy existing netplan stanzas exactly.
- Do the work on a new branch off `main` (e.g. `add-s1-le3-le4`) and finish with a PR — never push to main directly. Current checkout is on `enable-cdp-c8000v-day0`;
  don't mix this work into that branch.
- No test suite exists. Verification = `bash -n` for shell scripts, `python3 dynamic_inventory.py | python3 -m json.tool` for the inventory, and `startup_config.py
  <yaml> --print` (needs `NXOS_PASSWORD` set; any dummy value is fine for rendering) for the switch YAMLs.
- `env_prod/` must never be committed or staged. Nothing in this plan touches it.
- Out of scope, intentionally: the README mermaid topology (already omits S1_LE2/S1_TOR1 — a separate cleanup), `config/ansible_local/dynamic_inventory.py` (it
  deliberately mirrors only a subset of SITE1 — it omits S1_LE2 today, so the new leaves follow the same rule), `env/env.sh` (it defines no per-switch vars; inventory
  defaults are the source), and `docs/manual_vpc_bringup_s1.md` (describes the LE1/LE2 pair only).

---

### Task 1: Bridge definitions (netplan + create/teardown scripts)

**Files:**

- Modify: `config/bridges/netplan/9912-bridges.yaml` (comment table ~line 21-24; bridge stanzas after `BR_S1_LE2_T1_1`, ~line 147)
- Modify: `config/bridges/bridges_config_ovs.sh:22-37` (`BRIDGES` array)
- Modify: `config/bridges/bridges_down.sh:5-19` (`BRIDGES` array)

**Interfaces:**

- Consumes: nothing.
- Produces: bridge names `BR_S1_SP1_LE3_1`, `BR_S1_SP1_LE4_1`, `BR_S1_LE3_LE4_1` — Tasks 2–4 reference these exact strings in `isl_bridges`.

- [ ] **Step 1: Create the branch**

```bash
cd ~/repos/n9kv-kvm
git checkout main && git pull
git checkout -b add-s1-le3-le4
```

- [ ] **Step 2: Add the three links to the netplan comment table**

In `config/bridges/netplan/9912-bridges.yaml`, after the line
`# S1_LE2_INTERFACE_3      S1_TOR1_INTERFACE_2     BR_S1_LE2_T1_1` insert:

```text
# S1_SP1_INTERFACE_4      S1_LE3_INTERFACE_1      BR_S1_SP1_LE3_1
# S1_SP1_INTERFACE_5      S1_LE4_INTERFACE_1      BR_S1_SP1_LE4_1
# S1_LE3_INTERFACE_2      S1_LE4_INTERFACE_2      BR_S1_LE3_LE4_1   (VPC peer-link)
```

- [ ] **Step 3: Add the three bridge stanzas to netplan**

In the same file, after the `BR_S1_LE2_T1_1:` stanza (keep SITE1 bridges grouped), insert — identical shape to the neighbors:

```yaml
    BR_S1_SP1_LE3_1:
      openvswitch: {}
      dhcp4: false
      dhcp6: false
      mtu: 9216
      accept-ra: false
      parameters:
        stp: false
      interfaces: []

    BR_S1_SP1_LE4_1:
      openvswitch: {}
      dhcp4: false
      dhcp6: false
      mtu: 9216
      accept-ra: false
      parameters:
        stp: false
      interfaces: []

    BR_S1_LE3_LE4_1:
      openvswitch: {}
      dhcp4: false
      dhcp6: false
      mtu: 9216
      accept-ra: false
      parameters:
        stp: false
      interfaces: []
```

- [ ] **Step 4: Add the bridges to `bridges_config_ovs.sh`**

In the `BRIDGES=(...)` array, after `BR_S1_LE2_T1_1`:

```bash
    BR_S1_SP1_LE3_1
    BR_S1_SP1_LE4_1
    BR_S1_LE3_LE4_1
```

- [ ] **Step 5: Add the bridges to `bridges_down.sh`**

Same three lines, same position (after `BR_S1_LE2_T1_1`) in its `BRIDGES=(...)` array.

- [ ] **Step 6: Verify**

```bash
bash -n config/bridges/bridges_config_ovs.sh && bash -n config/bridges/bridges_down.sh
python3 -c "import yaml; yaml.safe_load(open('config/bridges/netplan/9912-bridges.yaml'))"
grep -c "BR_S1_SP1_LE3_1\|BR_S1_SP1_LE4_1\|BR_S1_LE3_LE4_1" config/bridges/netplan/9912-bridges.yaml
```

Expected: no output from `bash -n` / yaml load; grep count `6` (3 comment-table + 3 stanza keys).

- [ ] **Step 7: Commit**

```bash
git add config/bridges/netplan/9912-bridges.yaml config/bridges/bridges_config_ovs.sh config/bridges/bridges_down.sh
git commit -m "Add SITE1 LE3/LE4 bridges to netplan and OVS scripts"
```

---

### Task 2: S1_LE3 switch YAML + console/ssh helpers

**Files:**

- Create: `config/nexus9000v/S1_LE3.yaml`
- Create: `config/nexus9000v/con_s1_le3` (mode 0755)
- Create: `config/nexus9000v/ssh_s1_le3` (mode 0755)

**Interfaces:**

- Consumes: bridge names from Task 1.
- Produces: `S1_LE3` with sid `1503`, mgmt `192.168.12.154/24`. Eth1/1 → `BR_S1_SP1_LE3_1`, Eth1/2 → `BR_S1_LE3_LE4_1` (list order defines interface numbering).

- [ ] **Step 1: Write `config/nexus9000v/S1_LE3.yaml`**

```yaml
---
# SITE1
# S1_LE3.yaml - Leaf Switch 3 in SITE1 (VPC pair member with S1_LE4)
name: S1_LE3
role: Leaf Switch
sid: 1503
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.154/24
mgmt_gw: 192.168.12.1
neighbors:
  - S1_SP1
  - S1_LE4
isl_bridges:
  - BR_S1_SP1_LE3_1
  - BR_S1_LE3_LE4_1
```

(`neighbors` and `isl_bridges` are paired lists — index 0 = Eth1/1 = spine uplink, index 1 = Eth1/2 = peer-link, matching the requested link map.)

- [ ] **Step 2: Write `config/nexus9000v/con_s1_le3`**

Console port = 10000 + sid = 11503:

```bash
telnet localhost 11503
```

- [ ] **Step 3: Write `config/nexus9000v/ssh_s1_le3`**

Same one-liner pattern as `ssh_s1_le2` (`sh` is the operator's ssh wrapper — copy verbatim, only the IP changes):

```bash
sh admin@192.168.12.154
```

- [ ] **Step 4: Make helpers executable and verify the YAML renders**

```bash
chmod 755 config/nexus9000v/con_s1_le3 config/nexus9000v/ssh_s1_le3
cd config/nexus9000v
NXOS_PASSWORD=dummy python3 startup_config.py S1_LE3.yaml --print
cd -
```

Expected: rendered NX-OS startup-config on STDOUT containing `hostname S1_LE3`, `ip address 192.168.12.154/24`, and interfaces `Ethernet1/1` and `Ethernet1/2` (no ISO is
built with `--print`).

- [ ] **Step 5: Commit**

```bash
git add config/nexus9000v/S1_LE3.yaml config/nexus9000v/con_s1_le3 config/nexus9000v/ssh_s1_le3
git commit -m "Add S1_LE3 leaf switch config and console/ssh helpers"
```

---

### Task 3: S1_LE4 switch YAML + console/ssh helpers

**Files:**

- Create: `config/nexus9000v/S1_LE4.yaml`
- Create: `config/nexus9000v/con_s1_le4` (mode 0755)
- Create: `config/nexus9000v/ssh_s1_le4` (mode 0755)

**Interfaces:**

- Consumes: bridge names from Task 1.
- Produces: `S1_LE4` with sid `1504`, mgmt `192.168.12.155/24`. Eth1/1 → `BR_S1_SP1_LE4_1`, Eth1/2 → `BR_S1_LE3_LE4_1`.

- [ ] **Step 1: Write `config/nexus9000v/S1_LE4.yaml`**

```yaml
---
# SITE1
# S1_LE4.yaml - Leaf Switch 4 in SITE1 (VPC pair member with S1_LE3)
name: S1_LE4
role: Leaf Switch
sid: 1504
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.155/24
mgmt_gw: 192.168.12.1
neighbors:
  - S1_SP1
  - S1_LE3
isl_bridges:
  - BR_S1_SP1_LE4_1
  - BR_S1_LE3_LE4_1
```

- [ ] **Step 2: Write `config/nexus9000v/con_s1_le4`**

```bash
telnet localhost 11504
```

- [ ] **Step 3: Write `config/nexus9000v/ssh_s1_le4`**

```bash
sh admin@192.168.12.155
```

- [ ] **Step 4: Make helpers executable and verify the YAML renders**

```bash
chmod 755 config/nexus9000v/con_s1_le4 config/nexus9000v/ssh_s1_le4
cd config/nexus9000v
NXOS_PASSWORD=dummy python3 startup_config.py S1_LE4.yaml --print
cd -
```

Expected: rendered startup-config with `hostname S1_LE4`, `ip address 192.168.12.155/24`, interfaces Ethernet1/1–1/2.

- [ ] **Step 5: Commit**

```bash
git add config/nexus9000v/S1_LE4.yaml config/nexus9000v/con_s1_le4 config/nexus9000v/ssh_s1_le4
git commit -m "Add S1_LE4 leaf switch config and console/ssh helpers"
```

---

### Task 4: S1_SP1 uplinks + site1.sh launch entries

**Files:**

- Modify: `config/nexus9000v/S1_SP1.yaml:10-17` (append to `neighbors` and `isl_bridges`)
- Modify: `config/nexus9000v/site1.sh` (add two launch lines)

**Interfaces:**

- Consumes: bridge names from Task 1; switch names `S1_LE3`/`S1_LE4` from Tasks 2–3.
- Produces: S1_SP1 grows from 3 to 5 data interfaces; Eth1/4 → `BR_S1_SP1_LE3_1`, Eth1/5 → `BR_S1_SP1_LE4_1`. Existing Eth1/1–1/3 assignments must not move (order
  changes renumber interfaces AND change sid/port-derived MACs on a redeploy).

- [ ] **Step 1: Append the new uplinks to `S1_SP1.yaml`**

Append only — existing entries keep their positions. Resulting file:

```yaml
---
# SITE1
# S1_SP1.yaml - Spine Switch 1 in SITE1
name: S1_SP1
role: Spine Switch
sid: 1401
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.141/24
mgmt_gw: 192.168.12.1
neighbors:
  - S1_BG1
  - S1_LE1
  - S1_LE2
  - S1_LE3
  - S1_LE4
isl_bridges:
  - BR_S1_BG1_SP1_1
  - BR_S1_SP1_LE1_1
  - BR_S1_SP1_LE2_1
  - BR_S1_SP1_LE3_1
  - BR_S1_SP1_LE4_1
```

- [ ] **Step 2: Add launch lines to `site1.sh`**

Insert before the `S1_SP1.yaml` line (leaves before spine, matching the existing LE-before-SP ordering):

```bash
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S1_LE3.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S1_LE4.yaml
```

- [ ] **Step 3: Verify the spine renders with 5 interfaces**

```bash
cd config/nexus9000v
NXOS_PASSWORD=dummy python3 startup_config.py S1_SP1.yaml --print
cd -
bash -n config/nexus9000v/site1.sh
```

Expected: S1_SP1 config now lists `Ethernet1/1` through `Ethernet1/5`; `bash -n` silent. (The `len(neighbors) == len(isl_bridges)` constraint is enforced by the tooling
— a mismatch fails here, not at boot.)

- [ ] **Step 4: Commit**

```bash
git add config/nexus9000v/S1_SP1.yaml config/nexus9000v/site1.sh
git commit -m "Uplink S1_LE3/S1_LE4 to S1_SP1 Eth1/4-1/5; launch via site1.sh"
```

---

### Task 5: Dynamic inventory entries

**Files:**

- Modify: `config/ansible/dynamic_inventory.py` (IPs ~line 54; hostnames ~line 101; interfaces ~line 151; `all.vars` dict ~lines 206/222/250; `nxos.children` ~line 314)

**Interfaces:**

- Consumes: IPs/hostnames/interface assignments fixed in Tasks 2–4.
- Produces: env-var-overridable inventory vars `S1_LE3_IP4`, `S1_LE4_IP4`, `S1_LE3_HOSTNAME`, `S1_LE4_HOSTNAME`, `S1_LE3_INTERFACE_1/2`, `S1_LE4_INTERFACE_1/2`,
  `S1_SP1_INTERFACE_4/5` — the canonical per-switch record for the `ansible-nd` repo's fabric config.

- [ ] **Step 1: Add device IPs**

After the `S1_TOR1_IP4` line (line 54):

```python
S1_LE3_IP4 = environ.get("S1_LE3_IP4", "192.168.12.154")
S1_LE4_IP4 = environ.get("S1_LE4_IP4", "192.168.12.155")
```

- [ ] **Step 2: Add hostnames**

After the `S1_TOR1_HOSTNAME` line (line 101):

```python
S1_LE3_HOSTNAME = environ.get("S1_LE3_HOSTNAME", "S1_LE3")
S1_LE4_HOSTNAME = environ.get("S1_LE4_HOSTNAME", "S1_LE4")
```

- [ ] **Step 3: Add interfaces (and extend the link comment block)**

After the `S1_SP1_INTERFACE_3` line (line 151):

```python
S1_SP1_INTERFACE_4 = environ.get("S1_SP1_INTERFACE_4", "Ethernet1/4")
S1_SP1_INTERFACE_5 = environ.get("S1_SP1_INTERFACE_5", "Ethernet1/5")

# S1_LE3/S1_LE4 are a second VPC pair (spine uplink + peer-link).
S1_LE3_INTERFACE_1 = environ.get("S1_LE3_INTERFACE_1", "Ethernet1/1")
S1_LE3_INTERFACE_2 = environ.get("S1_LE3_INTERFACE_2", "Ethernet1/2")
S1_LE4_INTERFACE_1 = environ.get("S1_LE4_INTERFACE_1", "Ethernet1/1")
S1_LE4_INTERFACE_2 = environ.get("S1_LE4_INTERFACE_2", "Ethernet1/2")
```

And extend the `# Links` comment block (lines 113–120) with:

```python
# S1_SP1_INTERFACE_4      S1_LE3_INTERFACE_1      BR_S1_SP1_LE3_1
# S1_SP1_INTERFACE_5      S1_LE4_INTERFACE_1      BR_S1_SP1_LE4_1
# S1_LE3_INTERFACE_2      S1_LE4_INTERFACE_2      BR_S1_LE3_LE4_1
```

- [ ] **Step 4: Publish everything in `all.vars` and `nxos.children`**

In the `all.vars` dict — after `"S1_TOR1_IP4": S1_TOR1_IP4,`:

```python
            "S1_LE3_IP4": S1_LE3_IP4,
            "S1_LE4_IP4": S1_LE4_IP4,
```

after `"S1_TOR1_HOSTNAME": S1_TOR1_HOSTNAME,`:

```python
            "S1_LE3_HOSTNAME": S1_LE3_HOSTNAME,
            "S1_LE4_HOSTNAME": S1_LE4_HOSTNAME,
```

after `"S1_SP1_INTERFACE_3": S1_SP1_INTERFACE_3,`:

```python
            "S1_SP1_INTERFACE_4": S1_SP1_INTERFACE_4,
            "S1_SP1_INTERFACE_5": S1_SP1_INTERFACE_5,
            "S1_LE3_INTERFACE_1": S1_LE3_INTERFACE_1,
            "S1_LE3_INTERFACE_2": S1_LE3_INTERFACE_2,
            "S1_LE4_INTERFACE_1": S1_LE4_INTERFACE_1,
            "S1_LE4_INTERFACE_2": S1_LE4_INTERFACE_2,
```

In `nxos.children`, after `"S1_LE2",`:

```python
            "S1_LE3",
            "S1_LE4",
```

- [ ] **Step 5: Verify**

```bash
python3 config/ansible/dynamic_inventory.py | python3 -m json.tool > /dev/null && echo OK
python3 config/ansible/dynamic_inventory.py | grep -c "S1_LE3\|S1_LE4"
flake8 config/ansible/dynamic_inventory.py
```

Expected: `OK`; grep count `10` (8 all.vars lines + 2 nxos.children lines; the two `S1_SP1_INTERFACE_*` lines don't contain the pattern); flake8 silent (line length 169 is configured in `.flake8`).

- [ ] **Step 6: Commit and open the PR**

```bash
git add config/ansible/dynamic_inventory.py
git commit -m "Add S1_LE3/S1_LE4 to dynamic inventory"
git push -u origin add-s1-le3-le4
gh pr create --title "Add second SITE1 leaf pair (S1_LE3/S1_LE4)" --fill
```

---

## Deployment notes (manual, on the lab host — not part of the repo change)

Merging the PR changes files only. To make the lab match:

1. `sudo cp config/bridges/netplan/9912-bridges.yaml /etc/netplan/9912-bridges.yaml && sudo chmod 600 /etc/netplan/9912-bridges.yaml && sudo netplan apply` (or just run
   `sudo ./config/bridges/bridges_config_ovs.sh` — it creates missing bridges idempotently).
2. Launch the new leaves: the two new `site1.sh` lines (or run them individually). `startup_config.py` builds each boot ISO from the YAML; the VM consumes it on first boot.
3. Restarting the already-running S1_SP1 is required to pick up Eth1/4–1/5 (raw QEMU process — kill via `kill_n9kv.sh`/PID, relaunch; existing Eth1/1–1/3 MACs are
   unchanged because the list was append-only).
4. Fabric onboarding of the new leaves (ND discovery, VPC pairing) happens from the `ansible-nd` repo, not here.
