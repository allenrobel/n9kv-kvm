# Campus Spine + Leaf-Spine Fabric Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one Catalyst 9000v spine per controller (`C1_SP1` on ND 4.2.1, `C3_SP1` on ND 4.3.1) to the existing `CAMPUS1` fabric, wired to the
existing campus leaf by one intra-fabric link, so the `cisco.nd` IOS-XE delete-side fabric-link ownership guard (PR #558) can be exercised against a
rebuildable link that nothing else depends on.

**Architecture:** The wire lands on the leaf's `GigabitEthernet1/0/8` (the highest front-panel port the 9-NIC launch provides) and the spine's
`GigabitEthernet1/0/1`. The leaf's NIC 8 already exists as an unattached padding TAP, so the leaf is re-cabled live with one `ovs-vsctl add-port`
and never reloads. To express a link on a non-contiguous port, the Cat9kv per-switch YAML gains an optional `isl_ports` list (parallel to
`neighbors` / `isl_bridges`) and the launcher gains an `--attach` action that attaches a running VM's existing TAPs to their bridges without
recreating them. The ND provisioner needs no code change: the spine is one more switch entry in each topology file, and ND stamps the link policy
on the CDP-discovered adjacency during the `switches` phase's Recalculate & Deploy. Lab execution, API evidence collection and the intent-only
corruption probe are recorded in a handoff-back document for the ansible-nd session.

**Tech Stack:** Python 3.13, PyYAML, pytest (`uv run pytest`), QEMU/KVM, Open vSwitch, netplan, genisoimage, Nexus Dashboard REST via
`config/nd/provision/nd_client.py` and `snapshot.py`.

**Spec:** The request is `/Users/arobel/docs/superpowers/cat9kv/handoff-n9kv-kvm-2026-09-14-delete-side-guard.md` (Option A). Design decisions
that the request left open are fixed in the "Design decisions" section below; there is no separate spec file.

## Global Constraints

- Line length is 169 everywhere (`black`, `flake8`, `pylint`, `pymarkdown`). Validate Python with `uv run black --check`, `uv run flake8`,
  `uv run mypy`; Markdown with `uv run pymarkdown scan <file>`.
- Never commit `env_prod/`.
- Work on branch `campus-spine-link`; the user merges through a PR. Commit messages end with the attribution lines the session was given.
- Lab host `glide-wired.laukapu.com`, repo checkout at `~/repos/n9kv-kvm`. `sudo` there needs a password in a real terminal: run privileged
  steps as `! ssh -t glide-wired.laukapu.com '...'` from the user's prompt, or ask the user to run them. Unprivileged reads (`ssh glide ... nproc`,
  `virsh list`, `telnet localhost <port>`) work non-interactively.
- Hosts (mirrors of each other; only hostname, sid and the third mgmt octet differ):

  | Controller | Spine | sid | serial | mgmt | bridge | leaf endpoint | bridge for the wire |
  |---|---|---|---|---|---|---|---|
  | ND 4.2.1 (10.10.20.10) | `C1_SP1` | 1702 | `CAT9KV1702` | 192.168.12.182/24, gw 192.168.12.1 | `BR_ND_DATA_12` | `C1_LE1 GigabitEthernet1/0/8` | `BR_C1_SP1_LE1_1` |
  | ND 4.3.1 (10.10.20.20) | `C3_SP1` | 3702 | `CAT9KV3702` | 192.168.14.182/24, gw 192.168.14.1 | `BR_ND_DATA_14` | `C3_LE1 GigabitEthernet1/0/8` | `BR_C3_SP1_LE1_1` |

- Spine port on the wire: `GigabitEthernet1/0/1` on both spines. Console `telnet localhost 11702` / `13702` on glide.
- Cat9kv launch parameters are unchanged: 4 vCPU, 18432 MB, `e1000`, 9 NICs minimum, IDE disk, BIOS boot, day-0 ISO label `CDROM`.
- The corruption probe is **intent only**: no `deploy` call, no `config_actions.deploy`, and the fabric must end with zero pending lines.

## Design decisions

1. **Wire on `GigabitEthernet1/0/8`, not `1/0/24`.** The launcher gives 9 NICs (`min_nics: 9`), so `1/0/8` is the highest port that exists as a
   NIC. NIC 8 is already a padding TAP (`tap1701-8` / `tap3701-8`) on the running leaves, so attaching it to a bridge re-cables the leaf without a
   reload, a NIC-count change, or ND re-discovery. `1/0/1..1/0/7` stay free for the `xe.yaml` test interface. The handoff explicitly allows this;
   the ansible-nd side sets `nd_test_xe_fabric_link_interface_name=GigabitEthernet1/0/8`.
2. **`isl_ports` (optional, parallel list) rather than a new `links:` schema.** It keeps the paired-list convention every launcher in this repo
   uses, defaults to `1..N` so existing YAMLs are untouched, and the NIC count grows to cover the highest listed port automatically.
3. **`cat9kv.py --attach`** attaches a running switch's existing TAPs to the bridges the YAML names (idempotent `ovs-vsctl --may-exist add-port`).
   It never creates or deletes a TAP, so it is safe on a live VM. A full launch still uses `setup_port` (which recreates TAPs).
4. **Bridge names** `BR_C1_SP1_LE1_1` / `BR_C3_SP1_LE1_1` follow `BR_<site>_<upper>_<lower>_<n>` with the campus `C<n>` prefix; both are exactly
   15 characters (the IFNAMSIZ ceiling). They are defined in netplan (survive reboot) and created now by the idempotent
   `bridges_config_ovs.sh` (no `netplan apply` needed today).
5. **ND link creation is left to ND.** Catalyst IOS-XE runs CDP by default on every port; after the spine is added, ND's Recalculate turns the CDP
   adjacency into an intra-fabric link. The only campus intra-fabric link template in the 4.2.1/4.3.1 links schema is `iosXeNumbered`, so that is
   the expected `policyType`. If ND does not create the link on its own, Task 6 has the explicit `POST /links` fallback; only if that fallback is
   needed does the provisioner gain a campus `links:` section.
6. **Option B (pre-provision) is answered from the schema, not built.** `POST /fabrics/{f}/switchActions/preProvision` exists on both builds and
   the links schema carries an intra-fabric `preprovision` policy type, but the request body is NX-OS shaped (`softwareImage nxos...`, N9K model
   example) and campus support is untested. Option A is cheaper to trust than to probe; Task 8 records this answer.
7. **Host headroom (measured 2026-09-14 on glide):** 72 threads; 24 QEMU guests at 4 vCPU each plus two ND VMs; 15-minute load average about 37;
   424 GiB available of 755 GiB. Two more 4-vCPU / 18 GiB guests fit.

## File structure

| File | Change |
|---|---|
| `config/cat9kv/cat9kv.py` | `SwitchConfig.isl_ports`, sparse `_generate_interfaces`, `OVSPortManager.attach_port`, `SwitchVMManager.attach_switch`, `--attach` |
| `config/cat9kv/tests/test_cat9kv.py` | tests for the above; update the shipped-YAML identity test |
| `config/cat9kv/C1_LE1.yaml`, `C3_LE1.yaml` | add the spine neighbor, bridge and `isl_ports: [8]` |
| `config/cat9kv/C1_SP1.yaml`, `C3_SP1.yaml` | new spine YAMLs |
| `config/cat9kv/con_c1_sp1`, `ssh_c1_sp1`, `con_c3_sp1`, `ssh_c3_sp1` | console / ssh one-liners |
| `config/cat9kv/README.md` | `isl_ports`, `--attach`, ND placement with the spine |
| `config/bridges/netplan/9912-bridges.yaml`, `9914-bridges.yaml`, `config/bridges/bridges_config_ovs.sh` | the two campus bridges |
| `config/nd/provision/topology_nd421.yaml`, `topology_nd431.yaml` | the spine switch entry |
| `config/nd/provision/README.md` | campus link notes, `--map C1_SP1=C3_SP1` |
| `config/ansible/dynamic_inventory.py` | spine IPs, hostnames, link interface variables, `iosxe` group |
| `README.md`, `CLAUDE.md` | fabric lists, mermaid, tree, campus description |
| `/Users/arobel/docs/superpowers/cat9kv/handoff-back-ansible-nd-2026-09-14-delete-side-guard.md` | deliverables for the ansible-nd session (outside the repo) |

---

### Task 1: Launcher support for a link on a non-contiguous port (`isl_ports`) and live re-cabling (`--attach`)

**Files:**

- Modify: `config/cat9kv/cat9kv.py` (`SwitchConfig`, `OVSPortManager`, `SwitchVMManager._generate_interfaces`, `_start_vm` link printout, `main`)
- Modify: `config/cat9kv/tests/test_cat9kv.py`

**Interfaces:**

- Produces: `SwitchConfig.isl_ports: List[int]` (defaults to `[1..len(isl_bridges)]`; validated same length as `isl_bridges`, unique, `>= 1`);
  `SwitchVMManager._generate_interfaces(config) -> List[NetworkInterface]` now yields `max(min_nics, max(isl_ports) + 1)` interfaces with
  `FP_<port>` entries at the listed ports and `PAD_<i>` elsewhere; `OVSPortManager.attach_port(iface) -> None`;
  `SwitchVMManager.attach_switch(config) -> None`; CLI `--attach --config <yaml>`.
- Task 2's YAMLs rely on `isl_ports` and Task 5 relies on `--attach`.

- [ ] **Step 1: Write the failing tests**

Replace the `isl_bridges == [] and neighbors == []` assertion in `test_shipped_yamls_load_with_the_expected_identity` (the leaf YAMLs change in
Task 2; keep this test green by asserting only the fields that stay), and append these tests to `config/cat9kv/tests/test_cat9kv.py`:

```python
def test_shipped_yamls_load_with_the_expected_identity():
    c1, c3 = _c1_le1(), ConfigLoader.load_switch_config(HERE / "C3_LE1.yaml")
    assert (c1.sid, c1.mgmt_bridge, c1.mgmt_ip, c1.mgmt_gw) == (1701, "BR_ND_DATA_12", "192.168.12.181/24", "192.168.12.1")
    assert (c3.sid, c3.mgmt_bridge, c3.mgmt_ip, c3.mgmt_gw) == (3701, "BR_ND_DATA_14", "192.168.14.181/24", "192.168.14.1")


def test_isl_ports_default_to_the_first_front_panel_slots():
    cfg = SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A", "B"], isl_bridges=["BR_A", "BR_B"])
    assert cfg.isl_ports == [1, 2]


def test_isl_ports_place_the_link_on_the_named_port_and_pad_the_rest():
    cfg = SwitchConfig(name="X", role="r", sid=1701, mgmt_bridge="BR_ND_DATA_12", neighbors=["C1_SP1"], isl_bridges=["BR_C1_SP1_LE1_1"], isl_ports=[8])
    interfaces = SwitchVMManager(_globals())._generate_interfaces(cfg)  # pylint: disable=protected-access
    assert len(interfaces) == 9
    assert [iface.bridge for iface in interfaces] == ["BR_ND_DATA_12"] + [None] * 7 + ["BR_C1_SP1_LE1_1"]
    assert interfaces[8].name == "FP_8" and interfaces[8].tap == "tap1701-8" and interfaces[8].mac == "52:54:00:11:08:01"
    assert interfaces[1].name == "PAD_1"


def test_isl_ports_beyond_min_nics_grow_the_nic_count():
    cfg = SwitchConfig(name="X", role="r", sid=1701, mgmt_bridge="B", neighbors=["N"], isl_bridges=["BR_X"], isl_ports=[24])
    interfaces = SwitchVMManager(_globals())._generate_interfaces(cfg)  # pylint: disable=protected-access
    assert len(interfaces) == 25 and interfaces[24].bridge == "BR_X" and interfaces[9].bridge is None


def test_isl_ports_must_pair_with_isl_bridges_and_be_unique_front_panel_ports():
    with pytest.raises(ValueError, match="isl_ports"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A"], isl_bridges=["BR_A"], isl_ports=[1, 2])
    with pytest.raises(ValueError, match="isl_ports"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A", "B"], isl_bridges=["BR_A", "BR_B"], isl_ports=[3, 3])
    with pytest.raises(ValueError, match="isl_ports"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A"], isl_bridges=["BR_A"], isl_ports=[0])


def test_attach_port_adds_an_existing_tap_to_its_bridge_without_recreating_it(monkeypatch):
    calls = []

    def fake_run(cmd, check=True):  # pylint: disable=unused-argument
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(OVSPortManager, "_run", staticmethod(fake_run))
    OVSPortManager.attach_port(NetworkInterface(name="FP_8", bridge="BR_C1_SP1_LE1_1", mac="m", tap="tap1701-8"))
    assert ["ovs-vsctl", "--may-exist", "add-port", "BR_C1_SP1_LE1_1", "tap1701-8"] in calls
    assert ["ovs-vsctl", "set", "int", "tap1701-8", "mtu_request=9216"] in calls
    assert ["ovs-vsctl", "set", "bridge", "BR_C1_SP1_LE1_1", "other-config:forward-bpdu=true"] in calls
    assert not any("tuntap" in cmd or "del" in cmd for cmd in calls)


def test_attach_port_skips_padding_and_rejects_a_missing_tap(monkeypatch):
    calls = []

    def fake_run(cmd, check=True):  # pylint: disable=unused-argument
        calls.append(cmd)
        rc = 1 if cmd[:3] == ["ip", "link", "show"] else 0
        return subprocess.CompletedProcess(cmd, rc)

    monkeypatch.setattr(OVSPortManager, "_run", staticmethod(fake_run))
    OVSPortManager.attach_port(NetworkInterface(name="PAD_3", bridge=None, mac="m", tap="tap1701-3"))
    assert calls == []
    with pytest.raises(RuntimeError, match="tap1701-8"):
        OVSPortManager.attach_port(NetworkInterface(name="FP_8", bridge="BR_C1_SP1_LE1_1", mac="m", tap="tap1701-8"))
```

Add `import subprocess` and extend the import line to `from cat9kv import Cat9kvQEMUBuilder, ConfigLoader, GlobalConfig, NetworkInterface,
OVSPortManager, SwitchConfig, SwitchVMManager, guest_interface`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest config/cat9kv/tests/test_cat9kv.py -v`
Expected: the new tests FAIL (`TypeError: unexpected keyword argument 'isl_ports'`, `AttributeError: ... has no attribute 'attach_port'`).

- [ ] **Step 3: Implement `isl_ports`**

In `SwitchConfig`:

```python
    neighbors: List[str] = field(default_factory=list)
    isl_bridges: List[str] = field(default_factory=list)
    # Front-panel port number for each isl_bridges entry (GigabitEthernet1/0/<port>). Defaults to 1..N. Lets a link sit on a
    # non-contiguous port (the campus leaf keeps 1/0/1..1/0/7 free for the cisco.nd tests and carries its spine link on 1/0/8).
    isl_ports: List[int] = field(default_factory=list)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.sid < 1000 or self.sid > 9999:
            raise ValueError(f"SID must be a 4-digit value between 1000-9999, got {self.sid}")
        if len(self.neighbors) != len(self.isl_bridges):
            raise ValueError("Number of neighbors must match number of ISL bridges")
        if not self.isl_ports:
            self.isl_ports = list(range(1, len(self.isl_bridges) + 1))
        if len(self.isl_ports) != len(self.isl_bridges):
            raise ValueError("Number of isl_ports must match number of ISL bridges")
        if len(set(self.isl_ports)) != len(self.isl_ports) or any(port < 1 for port in self.isl_ports):
            raise ValueError(f"isl_ports must be unique front-panel port numbers >= 1, got {self.isl_ports}")
```

Replace the two front-panel loops in `_generate_interfaces` with:

```python
        by_port = dict(zip(config.isl_ports, config.isl_bridges))
        nics = max(self.global_config.min_nics, max(by_port, default=0) + 1)
        for i in range(1, nics):
            bridge = by_port.get(i)
            interfaces.append(
                NetworkInterface(
                    name=f"FP_{i}" if bridge else f"PAD_{i}",
                    bridge=bridge,
                    mac=self.mac_generator.generate_ethernet_mac(config.sid, i, base_mac),
                    interface_type=interface_type,
                    tap=self._tap_name(config.sid, i),
                )
            )
        return interfaces
```

Update the docstring of `_generate_interfaces` ("Front-panel slots not named in isl_ports are padded up to `max(min_nics, highest port + 1)`
with TAPs attached to no bridge") and the launch printout in `_start_vm`:

```python
            for port, neighbor, bridge in zip(config.isl_ports, config.neighbors, config.isl_bridges):
                print(f"{config.name} {guest_interface(port)} -> {neighbor}: {bridge}")
```

Update the module docstring line `index i -> GigabitEthernet1/0/i = front-panel port i (isl_bridges[i-1], or padding)` to
`index i -> GigabitEthernet1/0/i = front-panel port i (the isl_bridges entry whose isl_ports value is i, or padding)`.

- [ ] **Step 4: Implement `attach_port`, `attach_switch`, `--attach`**

In `OVSPortManager`, after `setup_port`:

```python
    @classmethod
    def attach_port(cls, iface: NetworkInterface) -> None:
        """Attach an already-existing TAP (a running VM's NIC) to iface.bridge without recreating it.

        Re-cables a live switch: a padding NIC that gains a bridge in the YAML is plugged in with no reload. Idempotent.
        No-op for padding NICs (bridge None); error if the TAP or the bridge does not exist.
        """
        if iface.bridge is None:
            return
        if not iface.tap or cls._run(["ip", "link", "show", "dev", iface.tap], check=False).returncode != 0:
            raise RuntimeError(f"TAP '{iface.tap}' does not exist; the VM is not running (launch it instead of attaching)")
        if not cls.bridge_exists(iface.bridge):
            raise RuntimeError(f"OVS bridge '{iface.bridge}' not found. Create it first via netplan / bridges_config_ovs.sh.")
        cls._run(["ovs-vsctl", "--may-exist", "add-port", iface.bridge, iface.tap])
        cls._run(["ovs-vsctl", "set", "int", iface.tap, f"mtu_request={cls.MTU}"])
        cls.ensure_forward_bpdu(iface.bridge)
        cls._run(["ip", "link", "set", "dev", iface.tap, "up"])
```

In `SwitchVMManager`, after `teardown_switch`:

```python
    def attach_switch(self, config: SwitchConfig) -> None:
        """Attach a running switch's existing TAPs to the bridges the YAML names (re-cable without a reload)."""
        for iface in self._generate_interfaces(config):
            OVSPortManager.attach_port(iface)
            if iface.bridge is not None:
                print(f"{config.name} {iface.tap} -> {iface.bridge}")
```

In `main()`, add the argument and the branch (next to `--teardown`):

```python
    parser.add_argument("--attach", action="store_true", help="Attach the running switch's existing TAPs to their bridges (re-cable live) and exit")
```

```python
    if args.attach:
        if not args.config:
            print("Error: --attach requires --config")
            sys.exit(1)
        global_config = ConfigLoader.load_global_config(args.global_config)
        switch_config = ConfigLoader.load_switch_config(args.config)
        SwitchVMManager(global_config).attach_switch(switch_config)
        return
```

- [ ] **Step 5: Run the tests and linters**

Run: `uv run pytest config/cat9kv/tests -v && uv run black --check config/cat9kv && uv run flake8 config/cat9kv && uv run mypy config/cat9kv/cat9kv.py`
Expected: all PASS, no lint output.

- [ ] **Step 6: Commit**

```bash
git add config/cat9kv/cat9kv.py config/cat9kv/tests/test_cat9kv.py
git commit -m "cat9kv: isl_ports for links on non-contiguous ports; --attach re-cables a running switch"
```

---

### Task 2: Spine and leaf YAMLs, console helpers, bridge definitions

**Files:**

- Create: `config/cat9kv/C1_SP1.yaml`, `config/cat9kv/C3_SP1.yaml`
- Create: `config/cat9kv/con_c1_sp1`, `config/cat9kv/ssh_c1_sp1`, `config/cat9kv/con_c3_sp1`, `config/cat9kv/ssh_c3_sp1` (copy the `_le1` ones, executable)
- Modify: `config/cat9kv/C1_LE1.yaml`, `config/cat9kv/C3_LE1.yaml`
- Modify: `config/bridges/netplan/9912-bridges.yaml`, `config/bridges/netplan/9914-bridges.yaml`, `config/bridges/bridges_config_ovs.sh`
- Modify: `config/cat9kv/tests/test_cat9kv.py` (shipped-YAML test)

**Interfaces:**

- Consumes: `isl_ports` from Task 1.
- Produces: bridge names `BR_C1_SP1_LE1_1` / `BR_C3_SP1_LE1_1` and switch identities that Tasks 3-6 use verbatim.

- [ ] **Step 1: Extend the shipped-YAML test (fails until the YAMLs exist)**

Append to `test_shipped_yamls_load_with_the_expected_identity`:

```python
    assert (c1.neighbors, c1.isl_bridges, c1.isl_ports) == (["C1_SP1"], ["BR_C1_SP1_LE1_1"], [8])
    assert (c3.neighbors, c3.isl_bridges, c3.isl_ports) == (["C3_SP1"], ["BR_C3_SP1_LE1_1"], [8])
    s1, s3 = ConfigLoader.load_switch_config(HERE / "C1_SP1.yaml"), ConfigLoader.load_switch_config(HERE / "C3_SP1.yaml")
    assert (s1.sid, s1.serial, s1.mgmt_bridge, s1.mgmt_ip, s1.mgmt_gw) == (1702, "CAT9KV1702", "BR_ND_DATA_12", "192.168.12.182/24", "192.168.12.1")
    assert (s3.sid, s3.serial, s3.mgmt_bridge, s3.mgmt_ip, s3.mgmt_gw) == (3702, "CAT9KV3702", "BR_ND_DATA_14", "192.168.14.182/24", "192.168.14.1")
    assert (s1.neighbors, s1.isl_bridges, s1.isl_ports) == (["C1_LE1"], ["BR_C1_SP1_LE1_1"], [1])
    assert (s3.neighbors, s3.isl_bridges, s3.isl_ports) == (["C3_LE1"], ["BR_C3_SP1_LE1_1"], [1])
    assert all(len(b) <= 15 for b in s1.isl_bridges + s3.isl_bridges)  # IFNAMSIZ
```

Run: `uv run pytest config/cat9kv/tests/test_cat9kv.py::test_shipped_yamls_load_with_the_expected_identity -v` -- Expected: FAIL (file not found / `[]`).

- [ ] **Step 2: Write the YAMLs**

`config/cat9kv/C1_LE1.yaml`:

```yaml
---
# C1_LE1.yaml - Catalyst 9000v campus leaf managed by ND 4.2.1 (fabric CAMPUS1).
# C<n> marks the campus fabric; n follows the odd-site = ND 4.2.1 rule (S1/S2 are ND 4.2.1, S3/S4 the ND 4.3.1 mirror).
# One fabric link to the campus spine on the highest port the 9-NIC launch provides (GigabitEthernet1/0/8), so
# 1/0/1..1/0/7 stay free for the cisco.nd IOS-XE interface tests. The link was cabled live (`cat9kv.py --attach`).
name: C1_LE1
role: Campus Leaf
sid: 1701
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.181/24
mgmt_gw: 192.168.12.1
neighbors: [C1_SP1]
isl_bridges: [BR_C1_SP1_LE1_1]
isl_ports: [8]
```

`config/cat9kv/C3_LE1.yaml`: same with `C3_LE1`, "managed by ND 4.3.1 (fabric CAMPUS1); mirror of C1_LE1", sid 3701, `BR_ND_DATA_14`,
`192.168.14.181/24`, gw `192.168.14.1`, `neighbors: [C3_SP1]`, `isl_bridges: [BR_C3_SP1_LE1_1]`, `isl_ports: [8]`.

`config/cat9kv/C1_SP1.yaml`:

```yaml
---
# C1_SP1.yaml - Catalyst 9000v campus spine managed by ND 4.2.1 (fabric CAMPUS1). Exists so CAMPUS1 has one
# intra-fabric link (to C1_LE1 GigabitEthernet1/0/8) that the cisco.nd fabric-link ownership guard can be tested against.
name: C1_SP1
role: Campus Spine
sid: 1702
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.182/24
mgmt_gw: 192.168.12.1
neighbors: [C1_LE1]
isl_bridges: [BR_C1_SP1_LE1_1]
```

`config/cat9kv/C3_SP1.yaml`: same with `C3_SP1`, "managed by ND 4.3.1 (fabric CAMPUS1); mirror of C1_SP1", sid 3702, `BR_ND_DATA_14`,
`192.168.14.182/24`, gw `192.168.14.1`, `neighbors: [C3_LE1]`, `isl_bridges: [BR_C3_SP1_LE1_1]`.

Helpers (`chmod +x`), one per file, mirroring the existing `_le1` ones:

```bash
sed 's/11701/11702/' config/cat9kv/con_c1_le1 > config/cat9kv/con_c1_sp1
sed 's/13701/13702/' config/cat9kv/con_c3_le1 > config/cat9kv/con_c3_sp1
sed 's/192.168.12.181/192.168.12.182/' config/cat9kv/ssh_c1_le1 > config/cat9kv/ssh_c1_sp1
sed 's/192.168.14.181/192.168.14.182/' config/cat9kv/ssh_c3_le1 > config/cat9kv/ssh_c3_sp1
chmod +x config/cat9kv/con_c?_sp1 config/cat9kv/ssh_c?_sp1
cat config/cat9kv/con_c1_sp1 config/cat9kv/ssh_c1_sp1   # eyeball: port 11702, host .182
```

- [ ] **Step 3: Add the bridges**

`config/bridges/netplan/9912-bridges.yaml`: add to the link comment table `# C1_SP1_INTERFACE_1       C1_LE1_INTERFACE_8      BR_C1_SP1_LE1_1   (CAMPUS1 Cat9kv spine-leaf)`
and a bridge stanza identical in shape to `BR_S1_LE1_T1_1`:

```yaml
    BR_C1_SP1_LE1_1:
      openvswitch: {}
      dhcp4: false
      dhcp6: false
      mtu: 9216
      accept-ra: false
      parameters:
        stp: false
      interfaces: []
```

`config/bridges/netplan/9914-bridges.yaml`: same for `BR_C3_SP1_LE1_1` with the comment
`# C3_SP1_INTERFACE_1       C3_LE1_INTERFACE_8      BR_C3_SP1_LE1_1   BR_C1_SP1_LE1_1  (CAMPUS1 Cat9kv spine-leaf)`.

`config/bridges/bridges_config_ovs.sh`: append `BR_C1_SP1_LE1_1` after `BR_ISN_WAN_S2_1` and `BR_C3_SP1_LE1_1` after `BR_ISN_WAN_S4_1`, each with a
`# CAMPUS1 Cat9kv spine-leaf` comment.

- [ ] **Step 4: Verify**

```bash
uv run pytest config/cat9kv/tests -v
cd config/cat9kv && python3 cat9kv.py --dry-run --config C1_SP1.yaml | grep -E 'GigabitEthernet1/0/1 |netdev' | head -3 ; cd -
cd config/cat9kv && python3 cat9kv.py --dry-run --config C1_LE1.yaml | grep 'GigabitEthernet1/0/8' ; cd -
bash -n config/bridges/bridges_config_ovs.sh && python3 -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" config/bridges/netplan/9912-bridges.yaml config/bridges/netplan/9914-bridges.yaml
```

Expected: tests pass; the spine dry run shows `GigabitEthernet1/0/1 (FP_1): BR_C1_SP1_LE1_1`; the leaf dry run shows
`GigabitEthernet1/0/8 (FP_8): BR_C1_SP1_LE1_1 -> 52:54:00:11:08:01 (tap: tap1701-8)`; both files parse. (The dry run warns about missing
`/iso1` files on the Mac; that is expected.)

- [ ] **Step 5: Commit**

```bash
git add config/cat9kv config/bridges
git commit -m "cat9kv/bridges: C1_SP1 and C3_SP1 campus spines, one leaf-spine link per controller on leaf Gi1/0/8"
```

---

### Task 3: Provisioner topology, inventory and docs

**Files:**

- Modify: `config/nd/provision/topology_nd421.yaml:70-72`, `config/nd/provision/topology_nd431.yaml:70-72`
- Modify: `config/nd/provision/README.md` (usage `--map`, campus bullet)
- Modify: `config/ansible/dynamic_inventory.py` (IPs, hostnames, interfaces, `iosxe` children, link comment table)
- Modify: `config/cat9kv/README.md`, `README.md`, `CLAUDE.md`

**Interfaces:**

- Consumes: identities from Task 2.
- Produces: `Switch(hostname="C1_SP1", ip="192.168.12.182", role="spine", platform="ios-xe")` in the 4.2.1 topology (and the `C3_SP1` twin), which
  Task 6 provisions with the unchanged `provision.py --phase switches`.

- [ ] **Step 1: Topology files**

Replace the `switches:` block of `CAMPUS1` in `topology_nd421.yaml` with:

```yaml
    switches:
      # Catalyst 9000v leaf + spine, one intra-fabric link (C1_SP1 Gi1/0/1 -- C1_LE1 Gi1/0/8; ND stamps iosXeNumbered on the CDP
      # adjacency at Recalculate). Gi1/0/1..1/0/7 on the leaf must stay free for the cisco.nd IOS-XE interface tests; the link
      # exists so the fabric-link ownership guard (PR #558) has a corruptible, rebuildable endpoint.
      - {hostname: C1_LE1, ip: 192.168.12.181, role: leaf, platform: ios-xe}
      - {hostname: C1_SP1, ip: 192.168.12.182, role: spine, platform: ios-xe}
```

`topology_nd431.yaml`: same with `C3_LE1` / `C3_SP1` and `192.168.14.181` / `192.168.14.182`.

Run: `uv run pytest config/nd/provision/tests -q` and
`uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 --phase switches --dry-run 2>&1 | grep -i campus`
Expected: tests pass; the dry run logs a `shallowDiscovery` for `CAMPUS1` naming only the spine when it can reach ND (or the whole fabric when
it cannot; both are fine on the Mac).

- [ ] **Step 2: Inventory**

In `config/ansible/dynamic_inventory.py` add, next to the existing campus entries (`C1_LE1_IP4` block, hostname block, interface block, the
`all.vars` dict, and the `iosxe` group):

```python
C1_SP1_IP4 = environ.get("C1_SP1_IP4", "192.168.12.182")
C3_SP1_IP4 = environ.get("C3_SP1_IP4", "192.168.14.182")
```

```python
C1_SP1_HOSTNAME = environ.get("C1_SP1_HOSTNAME", "C1_SP1")
C3_SP1_HOSTNAME = environ.get("C3_SP1_HOSTNAME", "C3_SP1")
```

```python
# CAMPUS1 link (Cat9kv spine-leaf): C1_SP1_INTERFACE_1  C1_LE1_INTERFACE_8  BR_C1_SP1_LE1_1  (C3_* mirror on BR_C3_SP1_LE1_1)
C1_SP1_INTERFACE_1 = environ.get("C1_SP1_INTERFACE_1", "GigabitEthernet1/0/1")
C1_LE1_INTERFACE_8 = environ.get("C1_LE1_INTERFACE_8", "GigabitEthernet1/0/8")
C3_SP1_INTERFACE_1 = environ.get("C3_SP1_INTERFACE_1", "GigabitEthernet1/0/1")
C3_LE1_INTERFACE_8 = environ.get("C3_LE1_INTERFACE_8", "GigabitEthernet1/0/8")
```

Add all eight names to `all.vars` beside `C1_LE1_IP4` / `C1_LE1_HOSTNAME`, and change the `iosxe` group to
`"children": ["C1_LE1", "C1_SP1", "C3_LE1", "C3_SP1"]`. Add `C1_SP1` and `C3_SP1` host entries wherever `C1_LE1` / `C3_LE1` have per-host
entries (grep the file for `"C1_LE1"` and mirror each occurrence).

Run: `python3 config/ansible/dynamic_inventory.py | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['iosxe']['children'], d['all']['vars']['C1_SP1_IP4'], d['all']['vars']['C1_LE1_INTERFACE_8'])"`
Expected: `['C1_LE1', 'C1_SP1', 'C3_LE1', 'C3_SP1'] 192.168.12.182 GigabitEthernet1/0/8`.

- [ ] **Step 3: Docs**

- `config/cat9kv/README.md`: in "Files" add the spine YAMLs and helpers; in "Interface mapping" replace the last paragraph with: the leaves
  carry one fabric link on `GigabitEthernet1/0/8` (`isl_ports: [8]`) so `1/0/1..1/0/7` stay free for the interface tests; document `isl_ports`
  (parallel to `isl_bridges`, default `1..N`, the NIC count grows to cover the highest port); in "Other operations" add
  `sudo python3 cat9kv.py --config C1_LE1.yaml --attach   # attach a running switch's existing TAPs to their bridges (re-cable live, no reload)`;
  in "ND placement" say each `CAMPUS1` holds a leaf and a spine joined by one `iosXeNumbered` link and why.
- `config/nd/provision/README.md`: add `--map C1_SP1=C3_SP1` to the snapshot diff example; extend the `CAMPUS1` bullet with the spine and the
  link (policy type and endpoint fields filled in after Task 6).
- `README.md`: fabric lists (`Catalyst 9000v leaf (C1_LE1) + spine (C1_SP1), one leaf-spine link; exists for the cisco.nd IOS-XE interface
  tests and the fabric-link ownership guard`), mermaid (`C1_SP1[Campus Spine - C1_SP1]`, `C1_SP1 --- C1_LE1`, the `spine` class line; same for
  `C3_*`), and the tree under `cat9kv` (`C1_SP1.yaml`, `C3_SP1.yaml`, `con_c1_sp1`, `con_c3_sp1`, `ssh_c1_sp1`, `ssh_c3_sp1`).
- `CLAUDE.md`: the two sentences that say each controller's `CAMPUS1` has "one Catalyst 9000v leaf" become "a Catalyst 9000v leaf and spine
  (`C1_LE1`/`C1_SP1`, `C3_LE1`/`C3_SP1`, `.181`/`.182`) joined by one link on the leaf's `Gi1/0/8`"; add `isl_ports` to the "Switch identity"
  note (front-panel port per `isl_bridges` entry, cat9kv only).

Run: `uv run pymarkdown scan README.md CLAUDE.md config/cat9kv/README.md config/nd/provision/README.md docs/superpowers/plans/2026-09-14-campus-spine-link.md`
Expected: no findings.

- [ ] **Step 4: Commit**

```bash
git add config/nd/provision/topology_nd421.yaml config/nd/provision/topology_nd431.yaml config/nd/provision/README.md \
        config/ansible/dynamic_inventory.py config/cat9kv/README.md README.md CLAUDE.md
git commit -m "provision/inventory/docs: C1_SP1 and C3_SP1 campus spines with one leaf-spine link per controller"
```

---

### Task 4: Lab host prep on glide (bridges, day-0 ISOs, headroom re-check)

**Files:** none in the repo. Runs on `glide-wired.laukapu.com` from `~/repos/n9kv-kvm` on the `campus-spine-link` branch.

- [ ] **Step 1: Sync the branch and re-check headroom**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && git fetch && git checkout campus-spine-link && git pull --ff-only && nproc && free -g | head -2 && cat /proc/loadavg'
```

Expected: branch checked out; 72 threads, at least 40 GiB available, 1-minute load under about 60. Stop and report if not.

- [ ] **Step 2: Create the two bridges (privileged; user runs in a real terminal)**

```bash
! ssh -t glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm/config/bridges \
    && sudo cp netplan/9912-bridges.yaml netplan/9914-bridges.yaml /etc/netplan/ && sudo chmod 600 /etc/netplan/99*-bridges.yaml \
    && sudo ./bridges_config_ovs.sh | grep -E "C1_SP1|C3_SP1"'
```

Expected: `OVS bridge BR_C1_SP1_LE1_1 does not exist. Creating...` then `Configuring bridge BR_C1_SP1_LE1_1...` (same for `C3`). No
`netplan apply` today; the netplan copy only makes the bridges survive a reboot.

- [ ] **Step 3: Build the spine day-0 ISOs**

```bash
! ssh -t glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh && cd config/cat9kv \
    && sudo -E python3 startup_config.py C1_SP1.yaml && sudo -E python3 startup_config.py C3_SP1.yaml'
```

Expected: `Built /iso2/iosxe/config/C1_SP1.iso (serial CAT9KV1702)` and `... C3_SP1.iso (serial CAT9KV3702)`.

---

### Task 5: Cable the leaves live and launch the spines

- [ ] **Step 1: Attach the leaves' NIC 8 to the campus bridges (no reload)**

```bash
! ssh -t glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm/config/cat9kv \
    && sudo python3 cat9kv.py --config C1_LE1.yaml --attach && sudo python3 cat9kv.py --config C3_LE1.yaml --attach \
    && sudo ovs-vsctl list-ports BR_C1_SP1_LE1_1 && sudo ovs-vsctl list-ports BR_C3_SP1_LE1_1'
```

Expected: `C1_LE1 tap1701-8 -> BR_C1_SP1_LE1_1`, `C3_LE1 tap3701-8 -> BR_C3_SP1_LE1_1`, and each `list-ports` prints exactly that TAP. Confirm
the leaves did not blink: `ssh glide-wired.laukapu.com 'ps -o etimes= -p $(pgrep -f "name C1_LE1")'` shows an uptime in days.

- [ ] **Step 2: Launch both spines**

```bash
! ssh -t glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm/config/cat9kv \
    && sudo python3 cat9kv.py --config C1_SP1.yaml && sudo python3 cat9kv.py --config C3_SP1.yaml \
    && sudo ovs-vsctl list-ports BR_C1_SP1_LE1_1 && sudo ovs-vsctl list-ports BR_C3_SP1_LE1_1'
```

Expected: `C1_SP1 instance created.` / `C1_SP1 GigabitEthernet1/0/1 -> C1_LE1: BR_C1_SP1_LE1_1` (same for `C3_SP1`); each bridge now lists
two TAPs (`tap1701-8` + `tap1702-1`; `tap3701-8` + `tap3702-1`).

- [ ] **Step 3: Wait for boot (about 4.5 minutes; console is silent between the loader line and the banner)**

Poll from the Mac without sudo until SSH answers on both:

```bash
for ip in 192.168.12.182 192.168.14.182; do until ssh glide-wired.laukapu.com "nc -z -w2 $ip 22"; do sleep 30; done; echo "$ip ssh up"; done
```

Then verify the wire from the leaf side (CDP is on by default on Catalyst; the neighbor should appear within a minute of the spine's ports coming up):

```bash
ssh glide-wired.laukapu.com "~/repos/n9kv-kvm/config/cat9kv/ssh_c1_le1 'show cdp neighbors GigabitEthernet1/0/8'"
ssh glide-wired.laukapu.com "~/repos/n9kv-kvm/config/cat9kv/ssh_c3_le1 'show cdp neighbors GigabitEthernet1/0/8'"
```

Expected: `C1_SP1` on `Gig 1/0/1` (and `C3_SP1`). If the neighbor is missing, check `show interfaces GigabitEthernet1/0/8` on the leaf (should be
`up/up` now that the TAP has a peer) and `show cdp` on the spine (should say CDP is enabled) before touching anything else.

---

### Task 6: Provision the spines into ND, Recalculate & Deploy, collect the evidence

**Files:** none in the repo (evidence is collected under `~/tmp/snap_*` on glide and copied into the handoff-back in Task 8).

- [ ] **Step 1: Snapshot both fabrics before the change (the "before" for question 1)**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
    && uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421_pre_spine --nd-ip 10.10.20.10 \
    && uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431_pre_spine --nd-ip 10.10.20.20'
```

Expected: `snapshot written to ...` twice; `interfaces_CAMPUS1_C1_LE1.json` and `interfaces_CAMPUS1_C3_LE1.json` exist.

- [ ] **Step 2: Add the spines (discovery, add, role, Recalculate & Deploy in one phase)**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
    && uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 --phase switches'
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
    && uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase switches'
```

Expected per controller: `shallowDiscovery` for `CAMPUS1` naming only the spine IP, one `POST /fabrics/CAMPUS1/switches`, the spine listed,
then `configSave` + `deploy` on `CAMPUS1` with no `still pending after deploy` line (the phase also recalculates SITE1/SITE2/ISN, which are already
converged and should print nothing new). If `CAMPUS1` reports pending lines after the second deploy, read the failed command:

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh && uv run python -c "
from config.nd.provision.nd_client import NDClient, NDCredentials
c = NDClient(NDCredentials.from_env(\"10.10.20.10\")); c.login()
for r in c.get(\"/fabrics/CAMPUS1/deploymentHistory\").get(\"deploymentRecords\", [])[:5]: print(r)"'
```

A Cat9kv parser rejection of an underlay command (the MTU story from 2026-09-11) is the likely failure shape; fix it in the fabric `settings`
of both topology files, re-run the phase, and record the change in the provision README.

- [ ] **Step 3: Confirm the link exists with a policy**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
    && uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421_spine --nd-ip 10.10.20.10 \
    && uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431_spine --nd-ip 10.10.20.20 && python3 -c "
import json
KEYS = (\"linkId\", \"srcSwitchId\", \"srcInterfaceName\", \"dstSwitchId\", \"dstInterfaceName\", \"srcSwitchName\", \"dstSwitchName\")
for nd in (\"nd421\", \"nd431\"):
    for l in json.load(open(f\"$HOME/tmp/snap_{nd}_spine/links_CAMPUS1.json\")):
        print(nd, l.get(\"configData\", {}).get(\"policyType\"), {k: l.get(k) for k in KEYS})"'
```

Expected: exactly one link per controller between `CAT9KV1702 GigabitEthernet1/0/1` and `CAT9KV1701 GigabitEthernet1/0/8` (either direction) with
`policyType` `iosXeNumbered` (any non-empty value satisfies the request; record what lands). Save the printed line for Task 8 item 1.

**Fallback if the link is present but `configData` is `{}` (discovered-only), or absent:** create it explicitly, then Recalculate & Deploy again:

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh && uv run python -c "
from config.nd.provision.nd_client import NDClient, NDCredentials
c = NDClient(NDCredentials.from_env(\"10.10.20.10\")); c.login()
body = {\"links\": [{\"srcFabricName\": \"CAMPUS1\", \"srcSwitchName\": \"C1_SP1\", \"srcSwitchId\": \"CAT9KV1702\", \"srcInterfaceName\": \"GigabitEthernet1/0/1\",
                    \"dstFabricName\": \"CAMPUS1\", \"dstSwitchName\": \"C1_LE1\", \"dstSwitchId\": \"CAT9KV1701\", \"dstInterfaceName\": \"GigabitEthernet1/0/8\",
                    \"configData\": {\"policyType\": \"iosXeNumbered\", \"templateInputs\": {}}}]}
print(c.post(\"/links\", json=body))
print(c.post(\"/fabrics/CAMPUS1/actions/configSave\", None, timeout=1800)); print(c.post(\"/fabrics/CAMPUS1/actions/deploy\", None, timeout=1800))"'
```

If ND rejects an empty `templateInputs`, read the `iosXeNumbered` required inputs with the nd-openapi `get_schema iosXeNumbered` tool and fill
them from the `intraFabricSubnetRange` pool (`10.44.0.0/22`). If this fallback is what worked, add a `campus: links:` section to both topology
files and a `phase_campus_links` mirroring `phase_isn`'s link loop (that is a follow-on task, not part of this plan).

- [ ] **Step 4: Collect the leaf endpoint interface record and answer question 1**

```bash
ssh glide-wired.laukapu.com 'python3 -c "
import json
for nd, leaf in ((\"nd421\", \"C1_LE1\"), (\"nd431\", \"C3_LE1\")):
    pre = {i[\"interfaceName\"]: i for i in json.load(open(f\"$HOME/tmp/snap_{nd}_pre_spine/interfaces_CAMPUS1_{leaf}.json\"))}
    post = {i[\"interfaceName\"]: i for i in json.load(open(f\"$HOME/tmp/snap_{nd}_spine/interfaces_CAMPUS1_{leaf}.json\"))}
    print(nd, \"Gi1/0/8 after:\", json.dumps(post[\"GigabitEthernet1/0/8\"], indent=1))
    changed = [n for n in pre if n != \"GigabitEthernet1/0/8\" and pre[n] != post.get(n)]
    print(nd, \"other interfaces whose record changed:\", changed)"'
```

Expected: the `Gi1/0/8` record now carries the link's interface policy (record `configData.mode`, `policyType` and every non-default field
verbatim for Task 8 item 2); `other interfaces whose record changed` is `[]` on both (the answer to question 1). If it is not empty, list the
names and the diff in the handoff-back; do not "fix" it.

- [ ] **Step 5: Zero pending, and the two controllers still mirror**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh && uv run config/nd/provision/snapshot.py diff ~/tmp/snap_nd421_spine ~/tmp/snap_nd431_spine \
  --map S1_BG1=S3_BG1 --map S1_SP1=S3_SP1 --map S1_LE1=S3_LE1 --map S1_LE2=S3_LE2 --map S1_LE3=S3_LE3 --map S1_LE4=S3_LE4 \
  --map S1_TOR1=S3_TOR1 --map S2_BG1=S4_BG1 --map S2_SP1=S4_SP1 --map S2_LE1=S4_LE1 --map WAN1=WAN2 --map C1_LE1=C3_LE1 --map C1_SP1=C3_SP1'
```

Expected: no `CAMPUS1` differences beyond serials/IPs that the diff already normalizes (any pre-existing SITE/ISN noise is unchanged from the
2026-09-14 baseline). Pending config was already checked by `config_deploy`; re-confirm with
`uv run python -c "...c.get('/fabrics/CAMPUS1/switches/CAT9KV1701/pendingConfig')..."` printing an empty `pendingConfigs` for both leaf and spine on
both controllers.

---

### Task 7: Intent-only corruption probe (item 3) and the restore path (item 4)

Runs against the leaf endpoint on each controller. Intent only: never call `deploy`. Work from the scratchpad on the Mac against ND directly
(`ND_USERNAME` / `ND_PASSWORD` from `env_prod` are needed; run on glide if the Mac cannot reach 10.10.20.x).

**Files:** `<scratchpad>/xe_link_probe.py` (throwaway; not committed).

- [ ] **Step 1: Write the probe**

```python
"""Intent-only overwrite of the campus leaf's link endpoint with iosXeAccess, then restore. Never deploys."""
import copy
import json
import sys

sys.path.insert(0, "/Users/arobel/repos/n9kv-kvm/config/nd/provision")
from nd_client import NDClient, NDCredentials  # noqa: E402

ND_IP, LEAF, PORT, FABRIC = sys.argv[1], sys.argv[2], "GigabitEthernet1/0/8", "CAMPUS1"  # e.g. 10.10.20.10 CAT9KV1701
c = NDClient(NDCredentials.from_env(ND_IP))
c.login()
path = f"/fabrics/{FABRIC}/switches/{LEAF}/interfaces/{PORT}"
before = c.get(path)
link_before = [l for l in c.paged("/links", "links", params={"fabricName": FABRIC})]
print("BEFORE", json.dumps(before, sort_keys=True))
corrupt = copy.deepcopy(before)
policy = {"policyType": "iosXeAccess", "adminState": True, "accessVlan": 100, "mtu": 1500}
corrupt["configData"] = {"mode": "access", "networkOS": {"networkOSType": "ios-xe", "policy": policy}}
resp = c.request("PUT", path, json=corrupt)  # request() returns the Response; a 4xx here is ND rejecting the overwrite
print("PUT iosXeAccess ->", resp.status_code, resp.text[:300])
mid = c.get(path)
print("MID", json.dumps(mid, sort_keys=True))
print("LINK unchanged:", link_before == [l for l in c.paged("/links", "links", params={"fabricName": FABRIC})])
resp = c.request("PUT", path, json=before)
print("PUT snapshot ->", resp.status_code)
after = c.get(path)
print("RESTORED byte-identical:", json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True))
print("PENDING", c.get(f"/fabrics/{FABRIC}/switches/{LEAF}/pendingConfig"))
```

- [ ] **Step 2: Run it on both controllers**

```bash
cd /Users/arobel/repos/n9kv-kvm && source env_prod/env.sh && uv run python <scratchpad>/xe_link_probe.py 10.10.20.10 CAT9KV1701 | tee <scratchpad>/probe_421.txt
cd /Users/arobel/repos/n9kv-kvm && source env_prod/env.sh && uv run python <scratchpad>/xe_link_probe.py 10.10.20.20 CAT9KV3701 | tee <scratchpad>/probe_431.txt
```

Expected: either `PUT iosXeAccess -> 204` with `MID` showing `iosXeAccess`, or `REJECTED` with ND's message (both are valid answers; record
which per build). `LINK unchanged: True`, `RESTORED byte-identical: True`, `PENDING` shows an empty `pendingConfigs` list.

- [ ] **Step 3: If the snapshot PUT does not restore byte-for-byte**

Run Recalculate & Deploy on `CAMPUS1` (this *is* a deploy, but of the original intent; it is the documented recovery path for the fabric):

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
    && uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 --phase deploy'
```

Then re-read the interface record and the links list, and confirm both equal the Task 6 snapshot. Record in the handoff-back which restore path
worked (item 4).

---

### Task 8: Handoff-back document, provision README evidence, PR

**Files:**

- Create: `/Users/arobel/docs/superpowers/cat9kv/handoff-back-ansible-nd-2026-09-14-delete-side-guard.md`
- Modify: `config/nd/provision/README.md` (the campus bullet gets the observed `policyType`, endpoint field shape, and the restore path)

- [ ] **Step 1: Write the handoff-back**

Sections, in this order, with the raw API values pasted from Tasks 6-7 (no paraphrase):

1. `## What exists now` table: controller, spine hostname, serial, mgmt IP, role; bridge; leaf endpoint `GigabitEthernet1/0/8`; console port.
2. `## Item 1: the link` per controller: `linkId`, `policyType`, `srcSwitchId`, `srcInterfaceName`, `dstSwitchId`, `dstInterfaceName`, plus
   `srcSwitchName` / `dstSwitchName`, and a sentence on whether the switch-ID fields are populated the same way the ISN `ebgpVrfLite` links are.
3. `## Item 2: the leaf endpoint interface record after Recalculate` per controller: the `Gi1/0/8` JSON, and the list of other interfaces whose
   record changed (expected empty).
4. `## Item 3: intent-only iosXeAccess overwrite` per controller: accepted (status) or rejected (message); link record unchanged; restore
   byte-identical; pending lines zero.
5. `## Item 4: restore path`: `PUT` of the snapshot, or Recalculate & Deploy, whichever Task 7 proved.
6. `## Inventory variables to set` for the ansible-nd side:

   ```ini
   nd_test_xe_fabric_link_switch_ip=192.168.12.181      # 192.168.14.181 on ND 4.3.1
   nd_test_xe_fabric_link_interface_name=GigabitEthernet1/0/8
   nd_test_xe_fabric_link_corruptible=true
   ```

7. `## Answers to your questions`: (1) from Task 6 step 4; (2) the observed policy type per build; (3) the headroom numbers from Task 4 step 1
   and the post-launch load; (4) Option B: `POST /fabrics/{f}/switchActions/preProvision` exists on 4.2.1 and 4.3.1 and the links schema has an
   intra-fabric `preprovision` policy type, the request body is NX-OS shaped, campus support untested because Option A was cheaper to trust.
8. `## Rebuild / recovery`: how to recreate the link from scratch (`bridges_config_ovs.sh`, `cat9kv.py --attach` on the leaf, spine launch,
   `provision.py --phase switches`, `--phase deploy` to recover from anything the corruption step leaves behind).

Run: `uv run pymarkdown scan /Users/arobel/docs/superpowers/cat9kv/handoff-back-ansible-nd-2026-09-14-delete-side-guard.md` -- Expected: no findings.

- [ ] **Step 2: Fold the evidence into the provision README and commit**

Extend the `CAMPUS1` bullet in `config/nd/provision/README.md` with the observed link `policyType`, the endpoint interface policy, whether the
intent-only `iosXeAccess` PUT is accepted, and the restore path. Then:

```bash
uv run pymarkdown scan config/nd/provision/README.md
git add config/nd/provision/README.md
git commit -m "provision README: CAMPUS1 leaf-spine link as observed on both controllers (policy type, endpoint record, intent-only restore path)"
```

- [ ] **Step 3: Open the PR**

```bash
git push -u origin campus-spine-link
gh pr create --title "CAMPUS1: Cat9kv spine + one leaf-spine link per controller (fabric-link guard testbed)" --body-file <scratchpad>/pr_body.md
```

The PR body summarizes the design decisions above, links the handoff (path only; it lives outside the repo), and lists what was verified on the
lab (link present with policy on both controllers, zero pending, snapshot diff clean, probe outcome). End the body with the attribution lines the
session was given.

---

## Self-review

- **Spec coverage:** item 1 (link fields) Task 6 step 3 + Task 8; item 2 (endpoint record) Task 6 step 4; item 3 (intent-only PUT) Task 7;
  item 4 (restore path) Task 7 step 3 + Task 8; question 1 Task 6 step 4; question 2 Task 6 step 3; question 3 Task 4 step 1 + design decision 7;
  question 4 design decision 6 + Task 8; "which port" (`1/0/8`) design decision 1 + Task 8 item 6; headroom sanity check before launching Task 4;
  "nothing else depends on the link" holds by construction (`CAMPUS1` has no links to any other fabric).
- **Placeholders:** none; the only values not known in advance are ND's observed responses, which the tasks capture verbatim.
- **Type consistency:** `isl_ports: List[int]` is used with that name in Tasks 1-3; `OVSPortManager.attach_port` / `SwitchVMManager.attach_switch`
  / `--attach` match between Task 1 and Task 5; bridge and serial names are identical across Tasks 2-8.
