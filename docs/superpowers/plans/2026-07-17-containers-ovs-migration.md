# Migrate LXC Host Containers to OVS — Implementation Plan (Part 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach the `config/containers/` LXC host-endpoint containers to the existing OVS bridges (libvirt OVS virtualport) and delete the now-dead
host-side VLAN-filtering path, so the containers work on the OVS-transitioned lab host.

**Architecture:** The container already does its own 802.1Q tagging in trunk mode (`eth1.<id>` subinterfaces built by `config_generators.py`), so on OVS the
host bridge just passes frames trunk-all — exactly like the switch taps. The only functional change is adding `<virtualport type='openvswitch'/>` to the
libvirt LXC interface XML; the host-side VLAN-filtering code (`bridge.py`, the orchestrator step, and four manual `bridge vlan` shell scripts) becomes dead
and is removed.

**Tech Stack:** Python 3.13, Jinja2, libvirt-LXC, Open vSwitch. Spec: `docs/superpowers/specs/2026-07-17-containers-ovs-migration-design.md`.

## Global Constraints

- Line length limit is **169** (flake8/black/pylint). Do not reflow to 79/88.
- **No test suite exists** in this repo by design (CLAUDE.md). Validate with `mypy`, `flake8`, a Jinja render check, and (on the lab host) a live bringup.
  Never claim "tests pass."
- The `config/containers/` package has **no `__init__.py`**; its modules import each other by bare name (`from models import ...`). All Python commands for
  it must run with `config/containers` as the working directory (or `PYTHONPATH=.` from inside it). Use the repo venv at `.venv/bin/`.
- `orchestrator.py` carries **12 pre-existing F541** (f-string-without-placeholder) flake8 warnings unrelated to this work. Do **not** fix them; just don't
  add new ones. `factory.py` and `libvirt_manager.py` are flake8-clean today and must stay clean.
- Never touch anything under `env_prod/`.
- Work on branch `migrate-containers-to-ovs`; commit after every task; do not push to `main`.
- This is **Part 1 only**. Do not touch `bridges_config_linux.sh`, the top-level Linux netplan YAMLs, `bridge.conf`, or the bringup docs — those are Part 2.

## File-change map

| File | Change | Task |
|------|--------|------|
| `config/containers/libvirt_manager.py` | Add `<virtualport type='openvswitch'/>` to both interface blocks | 1 |
| `config/containers/orchestrator.py` | Remove `BridgeVLANManager` dep + `_setup_bridge_vlans`; reword usage printout | 2 |
| `config/containers/factory.py` | Remove `BridgeVLANManager` import + wiring | 2 |
| `config/containers/bridge.py` | Delete | 2 |
| `config/bridges/{add_vlans,vlans_del}_BR_S{1,2}_LE1_H1_1.sh` (4 files) | Delete | 2 |
| `config/containers/README.md` | Replace Linux-bridge VLAN guidance with the OVS model | 3 |

---

### Task 1: Add OVS virtualport to the libvirt LXC interface XML

**Files:**

- Modify: `config/containers/libvirt_manager.py` (the two `<interface type='bridge'>` blocks in the `generate_xml` template, currently lines 49-58)

**Interfaces:**

- Consumes: nothing from earlier tasks.
- Produces: the rendered LXC domain XML now attaches both NICs to OVS. The render behavior later tasks rely on: `LibvirtXMLGenerator.generate_xml(spec,
  rootfs_path, output_file)` writes XML containing exactly two `<virtualport type='openvswitch'/>` elements — one per interface.

- [ ] **Step 1: Write the render check and confirm it FAILS on the current code**

Run from the container package dir (the check monkeypatches the emulator lookup so it works on macOS without libvirt):

```bash
cd config/containers && ../../.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
import pathlib, tempfile
import libvirt_manager
from config_loader import ConfigLoader

libvirt_manager.LibvirtXMLGenerator._find_libvirt_emulator = lambda self: "/usr/lib/libvirt/libvirt_lxc"
gen = libvirt_manager.LibvirtXMLGenerator(None)

for cfg, name in [("container_configs_access_mode.yaml", "S1_H1"), ("container_configs_trunk_mode.yaml", "S1_H1")]:
    spec = ConfigLoader(cfg).create_container_spec(name)
    out = pathlib.Path(tempfile.mktemp(suffix=".xml"))
    gen.generate_xml(spec, pathlib.Path("/tmp/rootfs"), out)
    xml = out.read_text()
    n = xml.count("<virtualport type='openvswitch'/>")
    assert n == 2, f"{cfg}: expected 2 virtualport elements, got {n}"
    assert f"<source bridge='{spec.management_interface.bridge}'/>" in xml
    assert f"<source bridge='{spec.test_interface.bridge}'/>" in xml
    print(f"{cfg} {name}: OK - 2 virtualport, mgmt={spec.management_interface.bridge}, test={spec.test_interface.bridge}")
print("RENDER CHECK PASSED")
PY
cd ../..
```

Expected now (RED): the first assertion fires —
`AssertionError: container_configs_access_mode.yaml: expected 2 virtualport elements, got 0`.

- [ ] **Step 2: Add the virtualport element to both interfaces**

In `config/containers/libvirt_manager.py`, the template block currently reads:

```python
    <interface type='bridge'>
      <source bridge='{{ spec.management_interface.bridge }}'/>
      <model type='virtio'/>
      <mac address='{{ spec.management_interface.mac_address }}'/>
    </interface>
    <interface type='bridge'>
      <source bridge='{{ spec.test_interface.bridge }}'/>
      <model type='virtio'/>
      <mac address='{{ spec.test_interface.mac_address }}'/>
    </interface>
```

Change it to (add one `<virtualport type='openvswitch'/>` line after each `<source .../>`):

```python
    <interface type='bridge'>
      <source bridge='{{ spec.management_interface.bridge }}'/>
      <virtualport type='openvswitch'/>
      <model type='virtio'/>
      <mac address='{{ spec.management_interface.mac_address }}'/>
    </interface>
    <interface type='bridge'>
      <source bridge='{{ spec.test_interface.bridge }}'/>
      <virtualport type='openvswitch'/>
      <model type='virtio'/>
      <mac address='{{ spec.test_interface.mac_address }}'/>
    </interface>
```

- [ ] **Step 3: Re-run the render check and confirm it PASSES**

Run the exact same command from Step 1.

Expected now (GREEN):

```text
container_configs_access_mode.yaml S1_H1: OK - 2 virtualport, mgmt=BR_ND_DATA_12, test=BR_S1_LE1_H1_1
container_configs_trunk_mode.yaml S1_H1: OK - 2 virtualport, mgmt=BR_ND_DATA_12, test=BR_S1_LE1_H1_1
RENDER CHECK PASSED
```

- [ ] **Step 4: Type-check and lint**

```bash
cd config/containers && PYTHONPATH=. ../../.venv/bin/mypy libvirt_manager.py && ../../.venv/bin/flake8 libvirt_manager.py && cd ../.. && echo OK
```

Expected: `Success: no issues found in 1 source file`, flake8 no output, then `OK`.

- [ ] **Step 5: Commit**

```bash
git add config/containers/libvirt_manager.py
git commit -m "Attach LXC container NICs to OVS via libvirt virtualport"
```

---

### Task 2: Remove the dead host-side VLAN path

**Files:**

- Modify: `config/containers/orchestrator.py`
- Modify: `config/containers/factory.py`
- Delete: `config/containers/bridge.py`
- Delete: `config/bridges/add_vlans_BR_S1_LE1_H1_1.sh`, `config/bridges/add_vlans_BR_S2_LE1_H1_1.sh`,
  `config/bridges/vlans_del_BR_S1_LE1_H1_1.sh`, `config/bridges/vlans_del_BR_S2_LE1_H1_1.sh`

**Interfaces:**

- Consumes: the OVS attachment from Task 1 (so containers now reach their bridges without host-side VLAN config).
- Produces: `ContainerOrchestrator.__init__` no longer takes a `bridge_manager` parameter; `create_container` no longer calls any bridge-VLAN setup. The
  container package still imports cleanly with no reference to a `bridge` module.

- [ ] **Step 1: Remove the `bridge` import and `_setup_bridge_vlans` from `orchestrator.py`**

In `config/containers/orchestrator.py`:

(a) Delete the import line:

```python
from bridge import BridgeVLANManager
```

(b) In `ContainerOrchestrator.__init__`, delete the parameter line `bridge_manager: BridgeVLANManager,` and the assignment line
`self.bridge_manager: BridgeVLANManager = bridge_manager`. The constructor should go from:

```python
    def __init__(
        self,
        executor: CommandExecutor,
        fs_manager: FileSystemManager,
        bridge_manager: BridgeVLANManager,
        rootfs_builder: RootfsBuilder,
        package_installer: PackageInstaller,
        config_generators: List[ConfigurationGenerator],
        xml_generator: LibvirtXMLGenerator,
        domain_manager: LibvirtDomainManager,
    ) -> None:
        self.executor: CommandExecutor = executor
        self.fs_manager: FileSystemManager = fs_manager
        self.bridge_manager: BridgeVLANManager = bridge_manager
        self.rootfs_builder: RootfsBuilder = rootfs_builder
```

to:

```python
    def __init__(
        self,
        executor: CommandExecutor,
        fs_manager: FileSystemManager,
        rootfs_builder: RootfsBuilder,
        package_installer: PackageInstaller,
        config_generators: List[ConfigurationGenerator],
        xml_generator: LibvirtXMLGenerator,
        domain_manager: LibvirtDomainManager,
    ) -> None:
        self.executor: CommandExecutor = executor
        self.fs_manager: FileSystemManager = fs_manager
        self.rootfs_builder: RootfsBuilder = rootfs_builder
```

(c) In `create_container`, delete these two lines (the comment and the call):

```python
            # Setup bridge VLANs
            self._setup_bridge_vlans(spec)
```

(d) Delete the whole `_setup_bridge_vlans` method:

```python
    def _setup_bridge_vlans(self, spec: ContainerSpec) -> None:
        """Setup bridge VLAN configuration"""
        vlan_ids: List[int] = [vlan.vlan_id for vlan in spec.vlans]
        self.bridge_manager.configure_bridge_vlans(spec.test_interface.bridge, vlan_ids)
```

- [ ] **Step 2: Reword the VLAN printout in `_print_usage_info` (`orchestrator.py`)**

The block currently reads:

```python
        if spec.vlans:
            for vlan in spec.vlans:
                test = spec.test_interface
                print(f"  {test.name}.{vlan.vlan_id}: {vlan.ip_address}/{vlan.netmask} -> {test.bridge} (VLAN {vlan.vlan_id})")

            print(f"\nBridge VLAN Configuration:")
            vlan_ids = [v.vlan_id for v in spec.vlans]
            print(f"  Bridge {spec.test_interface.bridge} configured with VLANs: {vlan_ids}")
        else:
            test = spec.test_interface
            print(f"  {test.name}: {test.ip_address}/{test.netmask} -> {test.bridge} (Direct)")
            print(f"\nBridge Configuration:")
            print(f"  Bridge {test.bridge} configured without VLANs")
```

Replace it with (note: the two new heading lines are **plain** strings, not f-strings, so they add no F541 warnings):

```python
        if spec.vlans:
            for vlan in spec.vlans:
                test = spec.test_interface
                print(f"  {test.name}.{vlan.vlan_id}: {vlan.ip_address}/{vlan.netmask} -> {test.bridge} (VLAN {vlan.vlan_id})")

            vlan_ids = [v.vlan_id for v in spec.vlans]
            print("\nVLAN Handling:")
            print(f"  VLANs {vlan_ids} are tagged inside the container and passed")
            print(f"  trunk-all by OVS bridge {spec.test_interface.bridge} (no host-side config).")
        else:
            test = spec.test_interface
            print(f"  {test.name}: {test.ip_address}/{test.netmask} -> {test.bridge} (Direct)")
```

- [ ] **Step 3: Remove the `BridgeVLANManager` wiring from `factory.py`**

In `config/containers/factory.py`:

(a) Delete the import line:

```python
from bridge import BridgeVLANManager
```

(b) Delete the instantiation line:

```python
        bridge_manager = BridgeVLANManager(executor)
```

(c) In the `return ContainerOrchestrator(...)` call, delete the argument line:

```python
            bridge_manager=bridge_manager,
```

- [ ] **Step 4: Delete `bridge.py` and the four Linux VLAN shell scripts**

```bash
git rm config/containers/bridge.py \
       config/bridges/add_vlans_BR_S1_LE1_H1_1.sh \
       config/bridges/add_vlans_BR_S2_LE1_H1_1.sh \
       config/bridges/vlans_del_BR_S1_LE1_H1_1.sh \
       config/bridges/vlans_del_BR_S2_LE1_H1_1.sh
```

- [ ] **Step 5: Verify the package still imports and no references remain**

```bash
cd config/containers && ../../.venv/bin/python -c "import factory, orchestrator; print('import OK')" && cd ../..
grep -rn "BridgeVLANManager\|from bridge import\|bridge_manager" config/containers/*.py || echo "no references remain"
ls config/bridges/add_vlans_BR_S1_LE1_H1_1.sh 2>&1 | grep -q "No such file" && echo "scripts deleted"
```

Expected: `import OK`; then `no references remain`; then `scripts deleted`. (Importing `factory` pulls in `orchestrator`; if any `from bridge import` survived,
this raises `ModuleNotFoundError: No module named 'bridge'`.)

- [ ] **Step 6: Type-check and lint the two changed files**

```bash
cd config/containers
PYTHONPATH=. ../../.venv/bin/mypy orchestrator.py factory.py libvirt_manager.py
../../.venv/bin/flake8 factory.py
../../.venv/bin/flake8 orchestrator.py | grep -c F541
cd ../..
```

Expected: mypy `Success: no issues found in 3 source files`; `flake8 factory.py` prints nothing (clean); the F541 count on `orchestrator.py` is now **10**
(down from the pre-existing 12 — Step 2 removed two no-placeholder f-strings). There must be **no** flake8 findings other than F541, and none on the lines you
edited. Do not fix the remaining pre-existing F541 warnings — out of scope.

- [ ] **Step 7: Commit**

```bash
git add config/containers/orchestrator.py config/containers/factory.py
git commit -m "Remove dead host-side VLAN path from container orchestration

bridge.py / BridgeVLANManager and the four manual bridge-vlan scripts drove
Linux-bridge VLAN filtering, which cannot run against the OVS bridges the
containers now attach to. VLANs are tagged inside the container and passed
trunk-all by OVS, so no host-side VLAN config is needed."
```

(The `git rm` from Step 4 is already staged, so this commit includes the deletions.)

---

### Task 3: Update the container README for the OVS model

**Files:**

- Modify: `config/containers/README.md`

**Interfaces:**

- Consumes: the OVS attachment (Task 1) and the removed VLAN path (Task 2).
- Produces: documentation only.

- [ ] **Step 1: Fix the module-structure list and Features section**

In `config/containers/README.md`, delete the `bridge.py` line from the module tree:

```text
├── bridge.py              # Bridge VLAN management
```

Then update the two "Network Configuration" feature bullets that describe host-side bridge filtering. Change:

```text
- **VLAN support**: Optional 802.1Q tagging with bridge filtering
- **Automatic bridge configuration**: VLAN filtering enabled/disabled based on container configuration
```

to:

```text
- **VLAN support**: Optional 802.1Q tagging done inside the container (eth1.<id> subinterfaces)
- **OVS attachment**: Container NICs attach to OVS bridges via libvirt virtualport; tagged frames pass trunk-all with no host-side VLAN config
```

- [ ] **Step 2: Replace the "Bridge Not Found" and "VLAN Filtering Issues" troubleshooting blocks**

The current troubleshooting text uses Linux-bridge commands. Replace this block
(a `#### 2. Bridge Not Found` section with an `ip link add ... type bridge`
snippet, followed by a `#### 3. VLAN Filtering Issues` section with a
`bridge vlan show` / `ip link set ... type bridge vlan_filtering 1` snippet)
with the following two OVS-based sections:

````text
#### 2. Bridge Not Found

The container bridges are OVS bridges, created by `config/bridges/bridges_config_ovs.sh`.
Verify they exist and (re)create them there — do not create them as Linux bridges:

```bash
# List OVS bridges
sudo ovs-vsctl list-br

# (Re)create the SITE1/SITE2 set if any are missing
sudo config/bridges/bridges_config_ovs.sh
```

#### 3. Container Port Not on the Bridge

VLANs are tagged inside the container and passed trunk-all by OVS, so there is no
host-side VLAN configuration to check. Confirm libvirt attached the container's
vnet to the OVS bridge:

```bash
# The container's vnet should appear under its bridge
sudo ovs-vsctl show
sudo ovs-vsctl list-ports BR_S1_LE1_H1_1
```
````

- [ ] **Step 3: Lint the README**

```bash
.venv/bin/pymarkdown scan config/containers/README.md
```

Expected: exit 0, no output. If MD0xx findings appear (line-length limit 169), fix them minimally while preserving meaning.

- [ ] **Step 4: Commit**

```bash
git add config/containers/README.md
git commit -m "Document container OVS attachment; drop Linux-bridge VLAN guidance"
```

---

## Post-merge lab-host validation (cannot run on the dev machine)

The render check and mypy/flake8 gates run anywhere, but the decisive proof —
that libvirt-LXC honors `<virtualport type='openvswitch'/>` — requires the
Ubuntu OVS host. After merge, on the lab host:

```bash
# Define + start a container, then confirm its vnet landed on the OVS bridge
cd config/containers
sudo python3 main.py --config container_configs_trunk_mode.yaml S1_H1
sudo virsh -c lxc:/// start S1_H1
sudo ovs-vsctl list-ports BR_S1_LE1_H1_1     # expect the container's vnet here
sudo ovs-vsctl list-ports BR_ND_DATA_12      # expect the mgmt vnet here
```

Then verify reachability from inside the container (`network-test mgmt-ping`,
`network-test vlan2-ping`). If the vnet does **not** appear on the bridge, the
host's libvirt lacks LXC OVS-virtualport support — fall back to the post-define
`ovs-vsctl add-port` approach noted in the spec's Assumptions and risks.
