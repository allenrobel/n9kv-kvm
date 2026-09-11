# Cat9kv Campus Leaf Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one ND-managed Catalyst 9000v leaf per Nexus Dashboard controller (`C1_LE1` on ND 4.2.1, `C3_LE1` on ND 4.3.1) in a new `vxlanCampus` fabric `CAMPUS1`, so
the `cisco.nd` IOS-XE interface tests can run.

**Architecture:** A new self-contained `config/cat9kv/` launcher subsystem mirrors `config/8000v/` (raw QEMU + OVS TAPs + day-0 ISO), with the Cat9kv-specific launch
parameters from the CML node definition. The existing ND provisioner gains the `CAMPUS1` fabric in both topology files and a platform-based credential rule. Lab bringup
and ND provisioning run on glide against both controllers.

**Tech Stack:** Python 3.13, PyYAML, Jinja2, pytest (run with `uv run pytest`), QEMU/KVM, Open vSwitch, genisoimage, Nexus Dashboard REST (`config/nd/provision/`).

**Spec:** `docs/superpowers/specs/2026-09-11-cat9kv-campus-leaf-design.md`

## Global Constraints

- Line length is 169 everywhere (`black`, `flake8`, `pylint`, `pymarkdown`). Validate Python with `uv run black --check`, `uv run flake8`, `uv run mypy`; Markdown with
  `uv run pymarkdown scan <file>`.

- Never commit `env_prod/`.
- Branch is `cat9kv-campus-leaf`; the user merges through a PR. Commit messages end with the attribution lines the session was given.
- Hosts: `C1_LE1` sid 1701, `BR_ND_DATA_12`, 192.168.12.181/24, gw 192.168.12.1; `C3_LE1` sid 3701, `BR_ND_DATA_14`, 192.168.14.181/24, gw 192.168.14.1. Serial
  `CAT9KV<sid>`. Fabric `CAMPUS1`, type `vxlanCampus`, ASN `65003`.

- Cat9kv launch: 4 vCPU, 18432 MB, `e1000` NICs, minimum 9 NICs, IDE disk, BIOS boot (`-machine type=pc`), 2 serial ports, day-0 ISO volume label `CDROM` with
  `iosxe_config.txt` + `conf/vswitch.xml`.

- Base image `/iso1/cml/cat9kv-17.15.03/cat9kv_prd.17.15.03.qcow2` on glide; per-VM artifacts in `/iso2/iosxe/config/`.
- Lab host: `glide-wired.laukapu.com`; repo checkout at `~/repos/n9kv-kvm`; `sudo` needs a password there (run privileged steps via `! ssh -t ...` from the user's
  terminal or ask the user).

---

### Task 1: Launcher `config/cat9kv/cat9kv.py` with per-switch YAMLs and tests

**Files:**

- Create: `config/cat9kv/global_config.yaml`
- Create: `config/cat9kv/C1_LE1.yaml`, `config/cat9kv/C3_LE1.yaml`
- Create: `config/cat9kv/vswitch.xml` (copy of `/iso1/cml/cat9kv-17.15.03/vswitch.xml` on glide)
- Create: `config/cat9kv/cat9kv.py` (start from a copy of `config/8000v/8000v.py`)
- Create: `config/cat9kv/tests/conftest.py`, `config/cat9kv/tests/test_cat9kv.py`

**Interfaces:**

- Produces: `SwitchConfig` (dataclass; fields `name, role, sid, mgmt_bridge, neighbors, isl_bridges, mgmt_ip, mgmt_gw, ram, vcpus, disk_size, interface_type,
  image_name`; properties `serial -> str`, `telnet_port -> int`, `monitor_port -> int`), `GlobalConfig` (adds `min_nics: int = 9`), `guest_interface(index: int) -> str`,
  `SwitchVMManager._generate_interfaces(config) -> List[NetworkInterface]` where `NetworkInterface.bridge` is `Optional[str]` (`None` = padding TAP, not attached to
  OVS), `Cat9kvQEMUBuilder.build_command(config, global_config, interfaces) -> List[str]`, `ConfigLoader.load_global_config(path) -> GlobalConfig`,
  `ConfigLoader.load_switch_config(path) -> SwitchConfig`.

- Task 2 reads the same per-switch YAML and derives the serial the same way (`f"CAT9KV{sid}"`).

- [ ] **Step 1: Create the data files**

`config/cat9kv/global_config.yaml`:

```yaml
# global_config.yaml - Global settings for all Catalyst 9000v switches
base_mac: "52:54:00"  # quoted to prevent YAML time parsing
cdrom_path: /iso2/iosxe/config
# CML 2.9 refplat image (beta, no TAC support). Boot disk is copied per VM; never launch the extracted file itself.
default_image: cat9kv_prd.17.15.03.qcow2
default_interface_type: e1000
default_ram: 18432  # MB; the image does not boot with less
default_vcpus: 4
image_path: /iso1/cml/cat9kv-17.15.03
# The image refuses to boot with fewer NICs than this; NICs beyond mgmt + isl_bridges are padded with unattached TAPs.
min_nics: 9
```

`config/cat9kv/C1_LE1.yaml`:

```yaml
---
# C1_LE1.yaml - Catalyst 9000v campus leaf managed by ND 4.2.1 (fabric CAMPUS1, no fabric links).
# C<n> marks the campus fabric; n follows the odd-site = ND 4.2.1 rule (S1/S2 are ND 4.2.1, S3/S4 the ND 4.3.1 mirror).
name: C1_LE1
role: Campus Leaf
sid: 1701
mgmt_bridge: BR_ND_DATA_12
mgmt_ip: 192.168.12.181/24
mgmt_gw: 192.168.12.1
neighbors: []
isl_bridges: []
```

`config/cat9kv/C3_LE1.yaml`:

```yaml
---
# C3_LE1.yaml - Catalyst 9000v campus leaf managed by ND 4.3.1 (fabric CAMPUS1, no fabric links); mirror of C1_LE1.
name: C3_LE1
role: Campus Leaf
sid: 3701
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.181/24
mgmt_gw: 192.168.14.1
neighbors: []
isl_bridges: []
```

`config/cat9kv/vswitch.xml`: copy it from glide unchanged (serial placeholder `CMLUADP`, `port_count` 24):

```bash
scp glide-wired.laukapu.com:/iso1/cml/cat9kv-17.15.03/vswitch.xml config/cat9kv/vswitch.xml
grep -c "<port lpn=" config/cat9kv/vswitch.xml   # expect 24
grep prod_serial_number config/cat9kv/vswitch.xml # expect <prod_serial_number>CMLUADP</prod_serial_number>
```

- [ ] **Step 2: Write the failing tests**

`config/cat9kv/tests/conftest.py`:

```python
"""Make the cat9kv package importable without installing it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

`config/cat9kv/tests/test_cat9kv.py`:

```python
"""Pure parts of the Cat9kv launcher: config loading, interface generation, QEMU command."""

from pathlib import Path

import pytest

from cat9kv import Cat9kvQEMUBuilder, ConfigLoader, GlobalConfig, SwitchConfig, SwitchVMManager, guest_interface

HERE = Path(__file__).resolve().parents[1]


def _c1_le1() -> SwitchConfig:
    return ConfigLoader.load_switch_config(HERE / "C1_LE1.yaml")


def _globals() -> GlobalConfig:
    return ConfigLoader.load_global_config(HERE / "global_config.yaml")


def test_shipped_yamls_load_with_the_expected_identity():
    c1, c3 = _c1_le1(), ConfigLoader.load_switch_config(HERE / "C3_LE1.yaml")
    assert (c1.sid, c1.mgmt_bridge, c1.mgmt_ip, c1.mgmt_gw) == (1701, "BR_ND_DATA_12", "192.168.12.181/24", "192.168.12.1")
    assert (c3.sid, c3.mgmt_bridge, c3.mgmt_ip, c3.mgmt_gw) == (3701, "BR_ND_DATA_14", "192.168.14.181/24", "192.168.14.1")
    assert c1.isl_bridges == [] and c1.neighbors == []


def test_serial_and_ports_derive_from_sid():
    cfg = _c1_le1()
    assert cfg.serial == "CAT9KV1701"
    assert cfg.telnet_port == 11701 and cfg.monitor_port == 21701


def test_global_config_carries_the_cat9kv_launch_parameters():
    gcfg = _globals()
    assert gcfg.default_ram == 18432 and gcfg.default_vcpus == 4
    assert gcfg.default_interface_type == "e1000" and gcfg.min_nics == 9
    assert gcfg.image_path == "/iso1/cml/cat9kv-17.15.03" and gcfg.default_image == "cat9kv_prd.17.15.03.qcow2"


def test_guest_interface_names():
    assert guest_interface(0) == "GigabitEthernet0/0"
    assert guest_interface(1) == "GigabitEthernet1/0/1"
    assert guest_interface(8) == "GigabitEthernet1/0/8"


def test_interfaces_are_padded_to_min_nics_with_unattached_taps():
    interfaces = SwitchVMManager(_globals())._generate_interfaces(_c1_le1())  # pylint: disable=protected-access
    assert len(interfaces) == 9
    assert interfaces[0].name == "MGMT" and interfaces[0].bridge == "BR_ND_DATA_12" and interfaces[0].tap == "tap1701-0"
    assert interfaces[0].mac == "52:54:00:11:00:01"
    assert all(iface.bridge is None for iface in interfaces[1:])
    assert [iface.tap for iface in interfaces[1:]] == [f"tap1701-{i}" for i in range(1, 9)]
    assert interfaces[3].mac == "52:54:00:11:03:01"
    assert all(iface.interface_type == "e1000" for iface in interfaces)


def test_isl_bridges_take_the_first_front_panel_slots_before_padding():
    cfg = SwitchConfig(name="X", role="Campus Leaf", sid=1702, mgmt_bridge="BR_ND_DATA_12", neighbors=["A", "B"], isl_bridges=["BR_A", "BR_B"])
    interfaces = SwitchVMManager(_globals())._generate_interfaces(cfg)  # pylint: disable=protected-access
    assert [iface.bridge for iface in interfaces] == ["BR_ND_DATA_12", "BR_A", "BR_B"] + [None] * 6
    assert interfaces[1].name == "FP_1" and interfaces[3].name == "PAD_3"


def test_switch_config_rejects_mismatched_neighbors_and_bad_sid():
    with pytest.raises(ValueError, match="neighbors"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A"], isl_bridges=[])
    with pytest.raises(ValueError, match="SID"):
        SwitchConfig(name="X", role="r", sid=17, mgmt_bridge="B")


def test_qemu_command_matches_the_cml_node_definition():
    gcfg, cfg = _globals(), _c1_le1()
    interfaces = SwitchVMManager(gcfg)._generate_interfaces(cfg)  # pylint: disable=protected-access
    cmd = Cat9kvQEMUBuilder().build_command(cfg, gcfg, interfaces)
    joined = " ".join(cmd)
    assert cmd[0] == "qemu-system-x86_64"
    assert "-machine type=pc,accel=kvm" in joined
    assert "-bios" not in cmd and "ahci" not in joined
    assert "-m 18432" in joined and "-smp 4,sockets=1,cores=4,threads=1" in joined
    assert "file=/iso2/iosxe/config/C1_LE1.qcow2,if=ide,format=qcow2,cache=writethrough" in joined
    assert "file=/iso2/iosxe/config/C1_LE1.iso,media=cdrom" in joined
    assert "-boot order=c" in joined
    assert cmd.count("-serial") == 2 and "-serial telnet:localhost:11701,server=on,wait=off" in joined and "-serial null" in joined
    assert "-monitor telnet:localhost:21701,server,nowait" in joined
    assert cmd.count("-netdev") == 9 and joined.count("e1000,netdev=") == 9
    assert "tap,id=MGMT,ifname=tap1701-0,script=no,downscript=no" in joined
    assert "-name C1_LE1" in joined
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest config/cat9kv/tests -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cat9kv'`.

- [ ] **Step 4: Create the launcher from the C8000V launcher and apply the Cat9kv edits**

```bash
cp config/8000v/8000v.py config/cat9kv/cat9kv.py
```

Then make these edits in `config/cat9kv/cat9kv.py` (everything not listed stays as copied):

1. Replace the module docstring:

```python
"""
Catalyst 9000v VM Manager

Manager for creating and configuring Cisco Catalyst 9000v (IOS-XE, CML 2.9
refplat image) VMs using QEMU/KVM with YAML-based configuration files.
Structurally mirrors config/8000v/8000v.py; kept self-contained per repo
convention.

Host networking uses Open vSwitch. TAP interfaces are created in Python and
attached to OVS bridges directly (QEMU's built-in bridge helper only speaks
Linux bridge and cannot attach to OVS). Each bridge is set to forward reserved
multicast frames (other-config:forward-bpdu=true) so LACP / STP / LLDP / CDP
PDUs cross the link.

Launch parameters come from the CML node definition (cat9000v-uadp): 4 vCPU,
18432 MB, e1000 NICs, IDE boot disk, BIOS boot, two serial ports (console on
the first, telnet localhost 10000+sid), minimum nine NICs. NICs beyond
mgmt + isl_bridges are padded with TAPs that are created but attached to no
bridge, so the image boots without a throwaway bridge.

IOS-XE numbers the NICs in PCI order:
  index 0 -> GigabitEthernet0/0   = management (mgmt_bridge)
  index i -> GigabitEthernet1/0/i = front-panel port i (isl_bridges[i-1], or padding)
"""
```

1. Replace `GlobalConfig`:

```python
@dataclass
class GlobalConfig:  # pylint: disable=too-many-instance-attributes
    """Global configuration settings."""

    image_path: str = "/iso1/cml/cat9kv-17.15.03"
    cdrom_path: str = "/iso2/iosxe/config"
    default_image: str = "cat9kv_prd.17.15.03.qcow2"
    base_mac: str = "52:54:00"

    # Default VM settings from the CML node definition. The image does not boot with less RAM.
    default_ram: int = 18432
    default_vcpus: int = 4
    default_disk_size: Optional[str] = None  # no resize; the image carries a 16 GiB virtual disk
    default_interface_type: str = "e1000"
    min_nics: int = 9  # image minimum (CML min_count); padded with unattached TAPs
```

1. In `NetworkInterface`, make `bridge: Optional[str]` and document it:

```python
@dataclass
class NetworkInterface:
    """Represents a network interface configuration."""

    name: str
    bridge: Optional[str]  # None = padding NIC: TAP exists so the guest sees a port, but it is attached to no bridge
    mac: str
    interface_type: str = "e1000"
    tap: Optional[str] = None  # host-side TAP device
```

1. Rename `RouterConfig` to `SwitchConfig` everywhere (class, type hints, `load_router_config` -> `load_switch_config`, `RouterVMManager` -> `SwitchVMManager`,
   `create_router` -> `create_switch`, `teardown_router` -> `teardown_switch`, `router_config` -> `switch_config`, `--list-routers` -> `--list-switches`) and add the
   serial property after `monitor_port`:

```python
    @property
    def serial(self) -> str:
        """Switch serial written into the day-0 conf/vswitch.xml (ND keys the switch on it; pinning it avoids
        serial churn on reload). startup_config.py derives the same value from the same YAML."""
        return f"CAT9KV{self.sid}"
```

1. Add a module-level helper right after the `SwitchConfig` class:

```python
def guest_interface(index: int) -> str:
    """IOS-XE name of the NIC at PCI index `index`: 0 is management, 1..N are front-panel ports."""
    return "GigabitEthernet0/0" if index == 0 else f"GigabitEthernet1/0/{index}"
```

1. Replace `C8000vQEMUBuilder` with `Cat9kvQEMUBuilder`:

```python
class Cat9kvQEMUBuilder(QEMUCommandBuilder):
    """QEMU command builder for Catalyst 9000v switches (CML node definition: driver csr1000v, disk_driver ide,
    nic_driver e1000, BIOS boot, two serial ports)."""

    def validate_files(self, config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
        """Return missing-file issues. BIOS boot: no OVMF needed."""
        image_name = config.image_name or global_config.default_image
        image_path = Path(global_config.image_path) / image_name
        if not image_path.exists():
            return [f"Cat9kv image not found: {image_path}"]
        return []

    def build_command(self, config: SwitchConfig, global_config: GlobalConfig, interfaces: List[NetworkInterface]) -> List[str]:
        """Build complete QEMU command for a Cat9kv switch."""
        cmd = ["qemu-system-x86_64"]
        cmd.extend(self._build_system_args())
        cmd.extend(self._build_cpu_memory_args(config, global_config))
        cmd.extend(self._build_storage_args(config, global_config))
        cmd.extend(self._build_network_args(interfaces))
        cmd.extend(self._build_misc_args(config))
        return cmd

    @staticmethod
    def _build_system_args() -> List[str]:
        """i440fx ('pc') carries the legacy IDE controller the image expects; q35 does not."""
        return ["-enable-kvm", "-machine", "type=pc,accel=kvm", "-cpu", "host"]

    @staticmethod
    def _build_cpu_memory_args(config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
        ram = config.ram or global_config.default_ram
        vcpus = config.vcpus or global_config.default_vcpus
        return [
            "-smp",
            f"{vcpus},sockets=1,cores={vcpus},threads=1",
            "-m",
            str(ram),
            "-object",
            f"memory-backend-ram,id=ram-node0,size={ram}M",
            "-numa",
            f"node,nodeid=0,cpus=0-{vcpus-1},memdev=ram-node0",
        ]

    @staticmethod
    def _build_storage_args(config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
        """Per-VM IDE disk + day-0 cdrom ISO (both under cdrom_path)."""
        cdrom_image = Path(global_config.cdrom_path) / f"{config.name}.iso"
        vm_disk = Path(global_config.cdrom_path) / f"{config.name}.qcow2"
        return [
            "-drive",
            f"file={vm_disk},if=ide,format=qcow2,cache=writethrough",
            "-drive",
            f"file={cdrom_image},media=cdrom",
        ]

    @staticmethod
    def _build_network_args(interfaces: List[NetworkInterface]) -> List[str]:
        """TAPs are pre-created by OVSPortManager, so QEMU must NOT manage them: script=no / downscript=no."""
        args = []
        for iface in interfaces:
            args.extend(
                [
                    "-netdev",
                    f"tap,id={iface.name},ifname={iface.tap},script=no,downscript=no",
                    "-device",
                    f"{iface.interface_type},netdev={iface.name},mac={iface.mac}",
                ]
            )
        return args

    @staticmethod
    def _build_misc_args(config: SwitchConfig) -> List[str]:
        """Console on the first serial port, a second (unused) serial port as the node definition declares, monitor."""
        return [
            "-rtc",
            "clock=host,base=localtime",
            "-nographic",
            "-boot",
            "order=c",
            "-serial",
            f"telnet:localhost:{config.telnet_port},server=on,wait=off",
            "-serial",
            "null",
            "-monitor",
            f"telnet:localhost:{config.monitor_port},server,nowait",
            "-name",
            config.name,
        ]
```

1. In `OVSPortManager`, make `setup_port` and `teardown_port` skip OVS for padding NICs:

```python
    @classmethod
    def setup_port(cls, iface: NetworkInterface) -> None:
        """Create iface.tap and bring it up; attach it to iface.bridge on OVS unless bridge is None (padding NIC).

        Idempotent: any stale tap/port of the same name is cleared first.
        """
        if not iface.tap:
            raise ValueError(f"Interface '{iface.name}' has no TAP name assigned")
        if iface.bridge is not None and not cls.bridge_exists(iface.bridge):
            raise RuntimeError(f"OVS bridge '{iface.bridge}' not found. Create it first via netplan / bridges_config_ovs.sh.")
        cls.teardown_port(iface)  # clear stale state from a prior run
        cls._run(["ip", "tuntap", "add", "dev", iface.tap, "mode", "tap"])
        cls._run(["ip", "link", "set", "dev", iface.tap, "mtu", str(cls.MTU)])
        if iface.bridge is not None:
            cls._run(["ovs-vsctl", "--may-exist", "add-port", iface.bridge, iface.tap])
            cls._run(["ovs-vsctl", "set", "int", iface.tap, f"mtu_request={cls.MTU}"])
            cls.ensure_forward_bpdu(iface.bridge)
        cls._run(["ip", "link", "set", "dev", iface.tap, "up"])

    @classmethod
    def teardown_port(cls, iface: NetworkInterface) -> None:
        """Remove iface.tap from OVS (if attached) and delete it. Safe if already absent."""
        if not iface.tap:
            return
        if iface.bridge is not None:
            cls._run(["ovs-vsctl", "--if-exists", "del-port", iface.bridge, iface.tap], check=False)
        cls._run(["ip", "link", "del", "dev", iface.tap], check=False)
```

1. In `SwitchVMManager.__init__`, default `qemu_builder or Cat9kvQEMUBuilder()`. Replace `_generate_interfaces`:

```python
    def _generate_interfaces(self, config: SwitchConfig) -> List[NetworkInterface]:
        """Generate network interface configurations.

        Index 0 is GigabitEthernet0/0 (management); index i is GigabitEthernet1/0/i. Front-panel slots beyond
        isl_bridges are padded up to global_config.min_nics with TAPs attached to no bridge.
        """
        interface_type = config.interface_type or self.global_config.default_interface_type
        base_mac = self.global_config.base_mac
        interfaces = [
            NetworkInterface(
                name="MGMT",
                bridge=config.mgmt_bridge,
                mac=self.mac_generator.generate_mgmt_mac(config.sid, base_mac),
                interface_type=interface_type,
                tap=self._tap_name(config.sid, 0),
            )
        ]
        for i, bridge in enumerate(config.isl_bridges, 1):
            interfaces.append(
                NetworkInterface(
                    name=f"FP_{i}",
                    bridge=bridge,
                    mac=self.mac_generator.generate_ethernet_mac(config.sid, i, base_mac),
                    interface_type=interface_type,
                    tap=self._tap_name(config.sid, i),
                )
            )
        for i in range(len(config.isl_bridges) + 1, self.global_config.min_nics):
            interfaces.append(
                NetworkInterface(
                    name=f"PAD_{i}",
                    bridge=None,
                    mac=self.mac_generator.generate_ethernet_mac(config.sid, i, base_mac),
                    interface_type=interface_type,
                    tap=self._tap_name(config.sid, i),
                )
            )
        return interfaces
```

1. In `_start_vm`, replace the neighbor print loop with:

```python
            for i, neighbor in enumerate(config.neighbors, 1):
                print(f"{config.name} {guest_interface(i)} -> {neighbor}: {config.isl_bridges[i - 1]}")
```

1. Replace `create_sample_configs` bodies:

```python
    global_config = {
        "image_path": "/iso1/cml/cat9kv-17.15.03",
        "cdrom_path": "/iso2/iosxe/config",
        "default_image": "cat9kv_prd.17.15.03.qcow2",
        "base_mac": "52:54:00",  # yaml.dump quotes this so it round-trips as a string
        "default_ram": 18432,
        "default_vcpus": 4,
        "default_interface_type": "e1000",
        "min_nics": 9,
    }
    _write_sample(out_dir / "global_config.yaml", global_config, force)

    switches = [
        {
            "name": "C1_LE1",
            "role": "Campus Leaf",
            "sid": 1701,
            "mgmt_bridge": "BR_ND_DATA_12",
            "mgmt_ip": "192.168.12.181/24",
            "mgmt_gw": "192.168.12.1",
            "neighbors": [],
            "isl_bridges": [],
        },
    ]

    for switch in switches:
        _write_sample(out_dir / f"{switch['name']}.yaml", switch, force)
```

1. In `main()`: description `"Catalyst 9000v VM Manager"`, `--config` help `"Switch configuration file (YAML)"`, `--list-switches` (help "List all switch config files in
   current directory", printing "Available switch configurations:"), and the dry-run interface print becomes:

```python
            for i, iface in enumerate(result["interfaces"]):
                print(f"  {guest_interface(i)} ({iface.name}): {iface.bridge or '(unattached)'} -> {iface.mac} (tap: {iface.tap})")
```

- [ ] **Step 5: Run the tests to verify they pass, then lint**

Run: `uv run pytest config/cat9kv/tests -v`
Expected: 8 passed.

Run: `uv run black --check config/cat9kv && uv run flake8 config/cat9kv && uv run mypy config/cat9kv/cat9kv.py`
Expected: no output from black/flake8 beyond "would reformat" absence; mypy "Success". Fix any finding.

Run: `cd config/cat9kv && uv run python cat9kv.py --config C1_LE1.yaml --dry-run; cd -`
Expected: warning that the image is missing (this is the Mac), the QEMU command, nine interface lines (`GigabitEthernet0/0 (MGMT): BR_ND_DATA_12 ...` then eight
`(unattached)`), ports 11701/21701.

- [ ] **Step 6: Commit**

```bash
git add config/cat9kv/global_config.yaml config/cat9kv/C1_LE1.yaml config/cat9kv/C3_LE1.yaml config/cat9kv/vswitch.xml config/cat9kv/cat9kv.py config/cat9kv/tests/
git commit -m "cat9kv: launcher for the Catalyst 9000v campus leaves (C1_LE1, C3_LE1)"
```

---

### Task 2: Day-0 generator `config/cat9kv/startup_config.py`

**Files:**

- Create: `config/cat9kv/startup_config.py` (start from a copy of `config/8000v/startup_config.py`)
- Create: `config/cat9kv/iosxe_startup_config.j2`
- Create: `config/cat9kv/tests/test_startup_config.py`

**Interfaces:**

- Consumes: per-switch YAML keys `name, sid, mgmt_ip, mgmt_gw`; `config/cat9kv/vswitch.xml` from Task 1.
- Produces: `serial_for(switch: dict) -> str`, `render_config(switch: dict, password: str, env: Environment) -> str`, `render_vswitch_xml(serial: str, template_path:
  Path = VSWITCH_XML) -> str`, `stage_day0(config_text: str, vswitch_text: str, staging: Path) -> None`, `build_iso(config_text: str, vswitch_text: str, hostname: str,
  out_dir: Path) -> Path`. CLI: `startup_config.py <yaml> | --all [--print]`.

- [ ] **Step 1: Write the failing tests**

`config/cat9kv/tests/test_startup_config.py`:

```python
"""Day-0 rendering and ISO staging for the Cat9kv (no genisoimage needed: subprocess is stubbed)."""

from pathlib import Path

import pytest

import startup_config
from startup_config import SERIAL_PLACEHOLDER, build_iso, load_yaml, render_config, render_vswitch_xml, serial_for, stage_day0

HERE = Path(__file__).resolve().parents[1]


def test_serial_for_matches_the_launcher_rule():
    assert serial_for({"sid": 1701}) == "CAT9KV1701"
    assert serial_for({"sid": "3701"}) == "CAT9KV3701"


def test_render_config_puts_mgmt_in_mgmt_vrf_with_dotted_mask():
    text = render_config(load_yaml(HERE / "C1_LE1.yaml"), "pw", startup_config._env())  # ggignore: unit-test placeholder, not a credential
    assert text.startswith("hostname C1_LE1\n")
    assert "interface GigabitEthernet0/0\n vrf forwarding Mgmt-vrf\n ip address 192.168.12.181 255.255.255.0\n no shutdown\n" in text
    assert "ip route vrf Mgmt-vrf 0.0.0.0 0.0.0.0 192.168.12.1\n" in text
    assert "username admin privilege 15 secret 0 pw\n" in text  # ggignore: unit-test placeholder, not a credential
    assert "line vty 0 15\n login local\n transport input ssh\n" in text
    assert "crypto key generate rsa modulus 2048" in text
    assert "GigabitEthernet1/0/" not in text  # front-panel ports are left at their defaults
    assert text.endswith("end\n")


def test_render_config_requires_a_prefix_length():
    with pytest.raises(ValueError, match="prefix"):
        switch = {"name": "X", "sid": 1702, "mgmt_ip": "192.168.12.182", "mgmt_gw": "192.168.12.1"}
        render_config(switch, "pw", startup_config._env())  # ggignore: unit-test placeholder, not a credential


def test_render_vswitch_xml_substitutes_only_the_serial():
    original = (HERE / "vswitch.xml").read_text(encoding="utf-8")
    text = render_vswitch_xml("CAT9KV1701")
    assert "<prod_serial_number>CAT9KV1701</prod_serial_number>" in text
    assert SERIAL_PLACEHOLDER not in text
    assert "<port_count>24</port_count>" in text and text.count("<port lpn=") == 24
    assert text.replace("CAT9KV1701", "CMLUADP") == original


def test_render_vswitch_xml_rejects_a_template_without_the_placeholder(tmp_path):
    bad = tmp_path / "vswitch.xml"
    bad.write_text("<switch></switch>", encoding="utf-8")
    with pytest.raises(ValueError, match="prod_serial_number"):
        render_vswitch_xml("CAT9KV1701", bad)


def test_stage_day0_writes_the_two_files_the_image_expects(tmp_path):
    stage_day0("hostname X\nend\n", "<switch/>", tmp_path)
    assert (tmp_path / "iosxe_config.txt").read_text(encoding="utf-8") == "hostname X\nend\n"
    assert (tmp_path / "conf" / "vswitch.xml").read_text(encoding="utf-8") == "<switch/>"


def test_build_iso_labels_the_volume_cdrom_and_uses_rock_ridge_and_joliet(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, check):
        calls.append(cmd)
        assert check is True
        staging = Path(cmd[-1])
        assert (staging / "iosxe_config.txt").exists() and (staging / "conf" / "vswitch.xml").exists()

    monkeypatch.setattr(startup_config.subprocess, "run", fake_run)
    monkeypatch.setattr(startup_config, "_iso_tool", lambda: "genisoimage")
    iso = build_iso("hostname X\nend\n", "<switch/>", "C1_LE1", tmp_path / "out")
    assert iso == tmp_path / "out" / "C1_LE1.iso"
    assert calls == [["genisoimage", "-o", str(iso), "-V", "CDROM", "-r", "-J", calls[0][-1]]]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest config/cat9kv/tests/test_startup_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'startup_config'`.

- [ ] **Step 3: Write the template**

`config/cat9kv/iosxe_startup_config.j2`:

```jinja
hostname {{ hostname }}
!
vrf definition Mgmt-vrf
 address-family ipv4
 exit-address-family
!
username admin privilege 15 secret 0 {{ admin_password }}
!
ip domain name lab.local
ip ssh version 2
!
interface GigabitEthernet0/0
 vrf forwarding Mgmt-vrf
 ip address {{ mgmt_ip_addr }} {{ mgmt_netmask }}
 no shutdown
!
ip route vrf Mgmt-vrf 0.0.0.0 0.0.0.0 {{ mgmt_gw }}
!
line vty 0 15
 login local
 transport input ssh
!
event manager applet GENERATE_RSA_KEYS
 event timer countdown time 60
 action 1.0 cli command "enable"
 action 2.0 cli command "crypto key generate rsa modulus 2048"
 action 3.0 cli command "configure terminal"
 action 4.0 cli command "no event manager applet GENERATE_RSA_KEYS"
 action 5.0 cli command "end"
 action 6.0 cli command "write memory"
!
end
```

- [ ] **Step 4: Write the generator**

```bash
cp config/8000v/startup_config.py config/cat9kv/startup_config.py
```

Then rewrite these parts of `config/cat9kv/startup_config.py`:

Module docstring:

```python
"""Generate the IOS-XE day-0 config and boot ISO for Catalyst 9000v switches.

Single source of truth: the per-switch YAML (e.g. C1_LE1.yaml) that cat9kv.py already reads, plus
global_config.yaml. Renders iosxe_startup_config.j2 to iosxe_config.txt, substitutes the switch serial into
vswitch.xml (the ASIC selector the image reads as conf/vswitch.xml), and wraps both in <cdrom_path>/<name>.iso
with volume label CDROM, which the Cat9kv consumes on first boot. The admin password is read from
$IOSXE_PASSWORD, falling back to $NXOS_PASSWORD; it is an error if neither is set.

Usage (ISO build writes to global_config.yaml cdrom_path, usually needs sudo):
    sudo -E python3 startup_config.py C1_LE1.yaml    # build one ISO
    sudo -E python3 startup_config.py --all          # build every switch YAML ISO
    python3 startup_config.py --print C1_LE1.yaml    # render the config to STDOUT only
"""
```

Constants (replace the `HERE`/`GLOBAL_CONFIG`/`TEMPLATE` block):

```python
HERE = Path(__file__).resolve().parent
GLOBAL_CONFIG = HERE / "global_config.yaml"
TEMPLATE = "iosxe_startup_config.j2"
VSWITCH_XML = HERE / "vswitch.xml"
SERIAL_PLACEHOLDER = "<prod_serial_number>CMLUADP</prod_serial_number>"
ISO_VOLUME_LABEL = "CDROM"  # the image looks for this label
```

Remove `derive_interfaces`. Replace `render_config` and add the serial / vswitch / staging helpers:

```python
def serial_for(switch: dict) -> str:
    """Serial written into conf/vswitch.xml; must match cat9kv.py's SwitchConfig.serial (CAT9KV<sid>)."""
    return f"CAT9KV{int(switch['sid'])}"


def render_config(switch: dict, password: str, env: Environment) -> str:
    """Render the IOS-XE day-0 config text for one switch."""
    mgmt_ip = switch["mgmt_ip"]
    if "/" not in mgmt_ip:
        raise ValueError(f"{switch['name']}: mgmt_ip must include a prefix (e.g. /24), got {mgmt_ip!r}")
    mgmt = IPv4Interface(mgmt_ip)  # IOS-XE wants address + dotted netmask, not CIDR
    context = {
        "hostname": switch["name"],
        "admin_password": password,
        "mgmt_ip_addr": str(mgmt.ip),
        "mgmt_netmask": str(mgmt.network.netmask),
        "mgmt_gw": switch["mgmt_gw"],
    }
    rendered = env.get_template(TEMPLATE).render(**context)
    return rendered.rstrip("\n") + "\n"


def render_vswitch_xml(serial: str, template_path: Path = VSWITCH_XML) -> str:
    """The committed vswitch.xml with the CML serial placeholder replaced; nothing else (port_count stays 24, as
    Cisco's node definition ships it regardless of NIC count)."""
    text = template_path.read_text(encoding="utf-8")
    if SERIAL_PLACEHOLDER not in text:
        raise ValueError(f"{template_path}: expected the placeholder {SERIAL_PLACEHOLDER}")
    return text.replace(SERIAL_PLACEHOLDER, f"<prod_serial_number>{serial}</prod_serial_number>")


def stage_day0(config_text: str, vswitch_text: str, staging: Path) -> None:
    """Lay out the ISO root: iosxe_config.txt and conf/vswitch.xml."""
    (staging / "conf").mkdir(parents=True, exist_ok=True)
    (staging / "iosxe_config.txt").write_text(config_text, encoding="utf-8")
    (staging / "conf" / "vswitch.xml").write_text(vswitch_text, encoding="utf-8")


def build_iso(config_text: str, vswitch_text: str, hostname: str, out_dir: Path) -> Path:
    """Wrap the staged day-0 files in <hostname>.iso (ISO9660 + Rock Ridge + Joliet, volume label CDROM)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    iso_path = out_dir / f"{hostname}.iso"
    tool = _iso_tool()
    with tempfile.TemporaryDirectory() as staging:
        stage_day0(config_text, vswitch_text, Path(staging))
        subprocess.run([tool, "-o", str(iso_path), "-V", ISO_VOLUME_LABEL, "-r", "-J", staging], check=True)
    return iso_path
```

In `main()`: argparse description `"Generate the Cat9kv IOS-XE day-0 config / boot ISO."`, `yaml` help `"Per-switch YAML (e.g. C1_LE1.yaml)"`, `--all` help `"Build ISOs
for every switch YAML in this dir"`, error text `"provide a switch YAML or --all"` / `"pass either a switch YAML or --all, not both"`, and the loop body:

```python
        try:
            switch = load_yaml(path)
            text = render_config(switch, password, env)
            if args.print_only:
                print(text)
                continue
            iso = build_iso(text, render_vswitch_xml(serial_for(switch)), switch["name"], out_dir)
            print(f"Built {iso} (serial {serial_for(switch)})")
```

- [ ] **Step 5: Run the tests, then lint and render**

Run: `uv run pytest config/cat9kv/tests -v`
Expected: 15 passed.

Run: `uv run black --check config/cat9kv && uv run flake8 config/cat9kv && uv run mypy config/cat9kv/startup_config.py`
Expected: clean.

Run: `cd config/cat9kv && IOSXE_PASSWORD=x uv run python startup_config.py --print C1_LE1.yaml; cd -`
Expected: the rendered config with `hostname C1_LE1` and `ip address 192.168.12.181 255.255.255.0`.

- [ ] **Step 6: Commit**

```bash
git add config/cat9kv/startup_config.py config/cat9kv/iosxe_startup_config.j2 config/cat9kv/tests/test_startup_config.py
git commit -m "cat9kv: day-0 config + CDROM ISO generator (iosxe_config.txt + conf/vswitch.xml with pinned serial)"
```

---

### Task 3: Console/SSH helpers and `config/cat9kv/README.md`

**Files:**

- Create: `config/cat9kv/con_c1_le1`, `config/cat9kv/ssh_c1_le1`, `config/cat9kv/con_c3_le1`, `config/cat9kv/ssh_c3_le1`
- Create: `config/cat9kv/README.md`

**Interfaces:**

- Consumes: telnet ports 11701 / 13701 (Task 1), mgmt IPs.

- [ ] **Step 1: Write the helpers (one line each, executable, same style as `config/8000v/con_wan1`)**

```bash
printf 'telnet localhost 11701\n' > config/cat9kv/con_c1_le1
printf 'telnet localhost 13701\n' > config/cat9kv/con_c3_le1
printf 'ssh admin@192.168.12.181\n' > config/cat9kv/ssh_c1_le1
printf 'ssh admin@192.168.14.181\n' > config/cat9kv/ssh_c3_le1
chmod +x config/cat9kv/con_c1_le1 config/cat9kv/con_c3_le1 config/cat9kv/ssh_c1_le1 config/cat9kv/ssh_c3_le1
```

Check: `stat -f '%Sp %N' config/8000v/con_wan1 config/cat9kv/con_c1_le1` shows the same mode bits.

- [ ] **Step 2: Write `config/cat9kv/README.md`**

````markdown
# Catalyst 9000v (Cat9kv) Configuration Management

Launches Cisco Catalyst 9000v switch VMs under QEMU/KVM with OVS TAP wiring, mirroring the
`config/8000v/` pattern. The image is the UADP flavor from the CML 2.9 reference platform
(`cat9kv_prd.17.15.03.qcow2`, IOS-XE 17.15.03): a **beta with no TAC support**, about 250 kbps of
dataplane, and it may crash under traffic load. It is fine for what the lab needs: an ND-managed
Catalyst leaf for the `cisco.nd` IOS-XE interface integration tests.

Design: `docs/superpowers/specs/2026-09-11-cat9kv-campus-leaf-design.md`.

## Files

- `cat9kv.py` - the launcher (raw QEMU process, not libvirt; manage by PID)
- `startup_config.py` + `iosxe_startup_config.j2` + `vswitch.xml` - day-0 config / boot ISO generator
- `global_config.yaml` - global defaults (image paths, RAM, vCPUs, NIC type, minimum NIC count)
- `C1_LE1.yaml`, `C3_LE1.yaml` - per-switch configs (ND 4.2.1 and ND 4.3.1 campus leaves)
- `con_c1_le1` / `ssh_c1_le1`, `con_c3_le1` / `ssh_c3_le1` - console / SSH one-liners
- `tests/` - pytest for the pure parts (`uv run pytest config/cat9kv/tests`)

## Launch parameters (from the CML node definition)

4 vCPU, 18432 MB (less does not boot), `e1000` NICs, IDE boot disk, BIOS boot (`-machine pc`, no OVMF),
two serial ports with the console on the first (`telnet localhost 10000+sid`). Boot takes up to 600 s and
is done when the console shows `Press RETURN to get started!` or `%SSH-5-ENABLED:`.

## Interface mapping

IOS-XE numbers the NICs in PCI order:

- `GigabitEthernet0/0` = management, attached to `mgmt_bridge` (vrf `Mgmt-vrf` in the day-0 config)
- `GigabitEthernet1/0/1..N` = one per `isl_bridges` entry (front-panel ports)
- `GigabitEthernet1/0/N+1..8` = padding: the image refuses to boot with fewer than nine NICs
  (`min_nics` in `global_config.yaml`), so the launcher creates TAPs for them but attaches them to no bridge

The campus leaves have no fabric links (`isl_bridges: []`): the interface tests need `GigabitEthernet1/0/1`
free of any ND fabric link, and no underlay adjacency is exercised.

TAP names are `tap<sid>-<index>` (e.g. `tap1701-0`). Bridges are referenced, not created - create them first
via `config/bridges/`.

## Day-0 behavior

`startup_config.py` renders `iosxe_startup_config.j2` into `iosxe_config.txt`, substitutes the switch serial
(`CAT9KV<sid>`) into `vswitch.xml`, and wraps both in `<cdrom_path>/<name>.iso` with volume label `CDROM`
(`genisoimage -V CDROM -r -J`). The image reads `iosxe_config.txt` as its startup config and
`conf/vswitch.xml` as the ASIC selector (`board_id 20612` = UADP; `port_count 24` is left as Cisco ships it
regardless of NIC count). Pinning the serial keeps ND's switch identity stable across reloads.

The rendered config puts `GigabitEthernet0/0` in `Mgmt-vrf` with a vrf default route, creates the `admin`
user, enables SSH, and installs a one-shot EEM applet that generates the RSA keypair 60 seconds after boot
and then removes itself.

## Bringup

```bash
# 1. Build the day-0 boot ISO (password from $IOSXE_PASSWORD or $NXOS_PASSWORD)
sudo -E python3 startup_config.py C1_LE1.yaml

# 2. Launch the VM (copies the base qcow2, creates TAPs, starts QEMU)
sudo python3 cat9kv.py --config C1_LE1.yaml

# 3. Watch it boot (up to 10 minutes; RSA keys generate ~60 s after boot)
./con_c1_le1
```

## Other operations

```bash
python3 cat9kv.py --config C1_LE1.yaml --dry-run    # inspect the QEMU command
python3 cat9kv.py --config C1_LE1.yaml --debug      # launch with QEMU output + status checks
python3 cat9kv.py --list-switches                   # list switch YAMLs
python3 cat9kv.py --create-samples                  # write samples to ./samples/ (skip existing)
sudo python3 cat9kv.py --config C1_LE1.yaml --teardown  # remove TAPs after stopping the VM
python3 startup_config.py --print C1_LE1.yaml       # render day-0 config to STDOUT
sudo -E python3 startup_config.py --all             # build day-0 ISOs for every switch YAML
```

## ND placement

Each leaf is the only member of a `vxlanCampus` fabric named `CAMPUS1` on its controller (ND 4.2.1 for
`C1_LE1`, ND 4.3.1 for `C3_LE1`); `config/nd/provision/` creates the fabric and adds the switch. Catalyst
switches cannot join the NX-OS `vxlanIbgp` fabrics (SITE1/SITE2).
````

Run: `uv run pymarkdown scan config/cat9kv/README.md`
Expected: no findings.

- [ ] **Step 3: Commit**

```bash
git add config/cat9kv/con_c1_le1 config/cat9kv/con_c3_le1 config/cat9kv/ssh_c1_le1 config/cat9kv/ssh_c3_le1 config/cat9kv/README.md
git commit -m "cat9kv: console/ssh helpers and README"
```

---

### Task 4: Provisioner: `CAMPUS1` in both topologies and a platform-based credential rule

**Files:**

- Modify: `config/nd/provision/provision.py` (`_switch_password`, module docstring line "Credentials:")
- Modify: `config/nd/provision/topology_nd421.yaml`, `config/nd/provision/topology_nd431.yaml`
- Modify: `config/nd/provision/tests/test_provision_payloads.py` (the four `_switch_password` tests)
- Modify: `config/nd/provision/tests/test_topology.py::test_shipped_topologies_load_and_mirror`
- Modify: `config/nd/provision/README.md`

**Interfaces:**

- Consumes: `topology.Fabric`, `topology.Switch(platform="ios-xe")`, `provision._platform(fabric)`.
- Produces: `_switch_password(fabric: Fabric) -> str` now keyed on switch platform.

- [ ] **Step 1: Update the tests to the platform rule**

In `config/nd/provision/tests/test_provision_payloads.py`, replace the four `test_switch_password_*` tests with:

```python
def _fabric(name: str, ftype: str, asn: str, platform: str) -> Fabric:
    return Fabric(name=name, type=ftype, asn=asn, switches=[Switch("SW", "10.0.0.1", "leaf", platform)])


def test_switch_password_uses_iosxe_for_an_ios_xe_external_fabric(monkeypatch):
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-pw")  # ggignore: unit-test placeholder, not a credential
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    assert _switch_password(_fabric("ISN", "externalConnectivity", "65535", "ios-xe")) == "iosxe-pw"  # ggignore: unit-test placeholder, not a credential


def test_switch_password_uses_iosxe_for_an_ios_xe_campus_fabric(monkeypatch):
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-pw")  # ggignore: unit-test placeholder, not a credential
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    assert _switch_password(_fabric("CAMPUS1", "vxlanCampus", "65003", "ios-xe")) == "iosxe-pw"  # ggignore: unit-test placeholder, not a credential


def test_switch_password_uses_nxos_for_an_nx_os_vxlan_fabric(monkeypatch):
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-pw")  # ggignore: unit-test placeholder, not a credential
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    assert _switch_password(_fabric("SITE2", "vxlanIbgp", "65002", "nx-os")) == "nxos-pw"  # ggignore: unit-test placeholder, not a credential


def test_switch_password_uses_nxos_for_a_fabric_with_no_switches(monkeypatch):
    monkeypatch.delenv("IOSXE_PASSWORD", raising=False)
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    assert _switch_password(Fabric(name="EMPTY", type="vxlanCampus", asn="1")) == "nxos-pw"  # ggignore: unit-test placeholder, not a credential


def test_switch_password_raises_when_iosxe_unset_for_an_ios_xe_fabric(monkeypatch):
    monkeypatch.delenv("IOSXE_PASSWORD", raising=False)
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    with pytest.raises(SystemExit, match="IOSXE_PASSWORD"):
        _switch_password(_fabric("CAMPUS1", "vxlanCampus", "65003", "ios-xe"))


def test_switch_password_raises_when_nxos_unset_for_an_nx_os_fabric(monkeypatch):
    monkeypatch.delenv("NXOS_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="NXOS_PASSWORD"):
        _switch_password(_fabric("SITE2", "vxlanIbgp", "65002", "nx-os"))
```

In `config/nd/provision/tests/test_topology.py::test_shipped_topologies_load_and_mirror`, change the fabric-list assertion and add the campus checks:

```python
    assert [f.name for f in t421.fabrics] == [f.name for f in t431.fabrics] == ["SITE1", "SITE2", "ISN", "CAMPUS1"]
    assert t421.fabric_groups[0].members == t431.fabric_groups[0].members == ["SITE1", "SITE2", "ISN"]
    assert t421.switch_fabric("S1_BG1") == "SITE1" and t431.switch_fabric("S3_BG1") == "SITE1"
    assert t421.switch_fabric("C1_LE1") == "CAMPUS1" and t431.switch_fabric("C3_LE1") == "CAMPUS1"
    campus421, campus431 = t421.fabrics[3], t431.fabrics[3]
    assert campus421.type == campus431.type == "vxlanCampus" and campus421.asn == campus431.asn == "65003"
    assert campus421.settings == campus431.settings
    assert [(s.role, s.platform) for s in campus421.switches] == [(s.role, s.platform) for s in campus431.switches] == [("leaf", "ios-xe")]
    assert [s.ip for s in campus421.switches] == ["192.168.12.181"] and [s.ip for s in campus431.switches] == ["192.168.14.181"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest config/nd/provision/tests -q`
Expected: the campus password test and the no-switches test fail (`_switch_password` still keys on `externalConnectivity`), and `test_shipped_topologies_load_and_mirror`
fails on the fabric list.

- [ ] **Step 3: Change `_switch_password`**

Replace it in `config/nd/provision/provision.py`:

```python
def _switch_password(fabric: Fabric) -> str:
    """IOSXE_PASSWORD when the fabric's switches are ios-xe (the WAN router in ISN, the Catalyst leaf in CAMPUS1);
    NXOS_PASSWORD otherwise. Keyed on the switch platform, not the fabric type: a vxlanCampus fabric holds Catalyst
    switches. Fail loud: an unset password must not silently fall back or add switches ND can never SSH into."""
    if fabric.switches and _platform(fabric) == "ios-xe":
        value = os.environ.get("IOSXE_PASSWORD")
        if not value:
            raise SystemExit(f"IOSXE_PASSWORD is not set; it is required to add IOS-XE switches to fabric {fabric.name}")
        return value
    value = os.environ.get("NXOS_PASSWORD")
    if not value:
        raise SystemExit(f"NXOS_PASSWORD is not set; it is required to add NX-OS switches to fabric {fabric.name}")
    return value
```

Note `phase_switches` already calls `_switch_password` with a `Fabric` built from the *missing* switches only, so the platform check sees exactly the switches about to
be discovered.

- [ ] **Step 4: Add `CAMPUS1` to both topology files**

Append after the `ISN` fabric entry (before `fabric_groups:`) in `config/nd/provision/topology_nd421.yaml`:

```yaml
  - name: CAMPUS1
    type: vxlanCampus           # Campus VXLAN EVPN (Easy_Fabric_IOS_XE): the only fabric type that takes Catalyst 9000
    asn: "65003"
    settings:
      management:               # 10.4x pools, disjoint from SITE1 (10.1x), SITE2 (10.2x) and ND's campus default vrfLite pool 10.33.0.0/16
        bgpLoopbackIpRange: 10.41.0.0/22
        nveLoopbackIpRange: 10.42.0.0/22
        anycastRendezvousPointIpRange: 10.43.0.0/24
        intraFabricSubnetRange: 10.44.0.0/22
        vrfLiteSubnetRange: 10.45.0.0/16
    switches:
      # One Catalyst 9000v leaf, no fabric links: GigabitEthernet1/0/1 must stay free for the cisco.nd IOS-XE interface tests.
      - {hostname: C1_LE1, ip: 192.168.12.181, role: leaf, platform: ios-xe}
```

Same block in `config/nd/provision/topology_nd431.yaml` with `{hostname: C3_LE1, ip: 192.168.14.181, role: leaf, platform: ios-xe}`. Also update the header comments of
both files: "SITE1/SITE2/ISN" wording is fine; add nothing else.

Check the mirror still holds: `diff config/nd/provision/topology_nd421.yaml config/nd/provision/topology_nd431.yaml` shows only the header lines, hostnames and mgmt IPs.

- [ ] **Step 5: Run the tests, lint**

Run: `uv run pytest config/nd/provision/tests -q`
Expected: all pass (the dry-run phase tests read `topology_nd421.yaml`; `CAMPUS1` reads 404 from the stub and is treated like any absent fabric).

If `test_phase_fabrics_*` or `test_phase_deploy_*` fail because they count fabrics or POSTs, extend their expected lists with `CAMPUS1` in the same position as the
topology (after `ISN`); do not weaken the assertions.

Run: `uv run black --check config/nd/provision && uv run flake8 config/nd/provision && uv run mypy config/nd/provision/provision.py`
Expected: clean.

Run: `uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd421.yaml --phase fabrics --dry-run` (needs `ND_*` env; on the Mac source
`env_prod/env.sh`)
Expected: a `would POST /fabrics` line for `CAMPUS1` with `"type": "vxlanCampus", "bgpAsn": "65003"` and a `would PUT` merging the five pools.

- [ ] **Step 6: Update `config/nd/provision/README.md`**

- First paragraph: "Provisions one lab testbed (fabrics, MSD, switches, ISN links, overlay, campus leaf) ...".
- Files list: "`topology_nd421.yaml` / `topology_nd431.yaml` - the two testbeds (SITE1/SITE2/ISN/MSD plus the CAMPUS1 Catalyst 9000v leaf on each controller); they
  differ only in hostnames and mgmt IPs".

- Snapshot diff example: append `--map C1_LE1=C3_LE1` to the `--map` list.
- Add a gotcha bullet at the end:

```markdown
- `CAMPUS1` is a `vxlanCampus` fabric (Campus VXLAN EVPN) holding one Catalyst 9000v leaf with no links; it exists so the `cisco.nd` IOS-XE interface
  tests have an ND-managed Catalyst. `_switch_password` picks `IOSXE_PASSWORD` by switch platform (`ios-xe`), so both `ISN` and `CAMPUS1` use it.
  The leaf is added with `preserveConfig: false` (ND owns its config, like the NX-OS fabrics).
```

Run: `uv run pymarkdown scan config/nd/provision/README.md`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add config/nd/provision/provision.py config/nd/provision/topology_nd421.yaml config/nd/provision/topology_nd431.yaml \
  config/nd/provision/tests/test_provision_payloads.py config/nd/provision/tests/test_topology.py config/nd/provision/README.md
git commit -m "provision: CAMPUS1 vxlanCampus fabric with the Cat9kv leaf on both controllers; credential by switch platform"
```

---

### Task 5: Inventory, env, and repo docs

**Files:**

- Modify: `config/ansible/dynamic_inventory.py`
- Modify: `env/02-ansible.sh`
- Modify (local only, never committed): `env_prod/02-ansible.sh` (or wherever `ND_FABRIC_ISN` lives in `env_prod/`)
- Modify: `README.md` (topology section, project structure tree)
- Modify: `CLAUDE.md` (layout table, conventions)

- [ ] **Step 1: Dynamic inventory**

In `config/ansible/dynamic_inventory.py`:

After the `S4_LE1_IP4_INTERFACE_2` line add:

```python
# CAMPUS1 (Catalyst 9000v campus leaves, one per controller; .18x is the campus-leaf block)
C1_LE1_IP4 = environ.get("C1_LE1_IP4", "192.168.12.181")
C3_LE1_IP4 = environ.get("C3_LE1_IP4", "192.168.14.181")
```

After `MSD_FABRIC = ...` add:

```python
CAMPUS1_FABRIC = environ.get("ND_FABRIC_CAMPUS1", "CAMPUS1")
```

After `S4_LE1_HOSTNAME = ...` add:

```python
# CAMPUS1
C1_LE1_HOSTNAME = environ.get("C1_LE1_HOSTNAME", "C1_LE1")
C3_LE1_HOSTNAME = environ.get("C3_LE1_HOSTNAME", "C3_LE1")
```

In `output["all"]["vars"]` add, next to the other fabric / IP / hostname entries:

```python
            "CAMPUS1_FABRIC": CAMPUS1_FABRIC,
            "C1_LE1_IP4": C1_LE1_IP4,
            "C3_LE1_IP4": C3_LE1_IP4,
            "C1_LE1_HOSTNAME": C1_LE1_HOSTNAME,
            "C3_LE1_HOSTNAME": C3_LE1_HOSTNAME,
```

Add a new top-level group after `"nxos"` (IOS-XE switches are not `cisco.nxos.nxos`):

```python
    "iosxe": {
        "children": ["C1_LE1", "C3_LE1"],
        "vars": {
            "ansible_become": "true",
            "ansible_become_method": "enable",
            "ansible_connection": "ansible.netcommon.network_cli",
            "ansible_network_os": "cisco.ios.ios",
        },
    },
```

and add `"iosxe"` to `output["all"]["children"]`. Update the module docstring naming convention paragraph with one sentence: "Catalyst 9000v campus leaves use
`C<n>_LE<idx>` (`C1_LE1` on ND 4.2.1, `C3_LE1` on ND 4.3.1)."

Run: `uv run python config/ansible/dynamic_inventory.py | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["all"]["vars"]["C1_LE1_IP4"],
d["all"]["vars"]["CAMPUS1_FABRIC"], d["iosxe"]["children"])'`
Expected: `192.168.12.181 CAMPUS1 ['C1_LE1', 'C3_LE1']`.

Run: `uv run black --check config/ansible && uv run flake8 config/ansible`
Expected: clean.

- [ ] **Step 2: Env scripts**

In `env/02-ansible.sh`, after `export ND_FABRIC_ISN=ISN` add:

```bash
export ND_FABRIC_CAMPUS1=CAMPUS1
```

Add the same line to the matching file under `env_prod/` (find it with `grep -l ND_FABRIC_ISN env_prod/*.sh`). Do **not** stage anything under `env_prod/`. Confirm with
`git status --short env_prod/` printing nothing staged (the directory is untracked; it must stay that way).

- [ ] **Step 3: `README.md`**

In "Topology built by this repository", add to the ND 4.2.1 bullet list:

```markdown
  - CAMPUS1 (Campus VXLAN EVPN) - Catalyst 9000v leaf (C1_LE1), no fabric links; exists for the cisco.nd IOS-XE interface tests
```

and to the ND 4.3.1 list:

```markdown
  - CAMPUS1 (Campus VXLAN EVPN) - Catalyst 9000v leaf (C3_LE1), mirror of C1_LE1
```

In the mermaid graph, inside each controller subgraph but outside its MSD subgraph, add a standalone node (`C1_LE1[Campus Leaf - C1_LE1]` under ND421, `C3_LE1[Campus
Leaf - C3_LE1]` under ND431) with a `CAMPUS1` subgraph wrapper:

```mermaid
        subgraph CAMPUS1_421["CAMPUS1 Fabric (Campus VXLAN EVPN)"]
            C1_LE1[Campus Leaf - C1_LE1]
        end
```

(and `CAMPUS1_431` / `C3_LE1` for the other controller). Add `C1_LE1,C3_LE1` to the `class ... leaf` line if one exists; otherwise leave styling alone.

In "Project Structure", add a `cat9kv` subtree under `config` between `bridges` and `containers` listing: `C1_LE1.yaml`, `C3_LE1.yaml`, `cat9kv.py`, `con_c1_le1`,
`con_c3_le1`, `global_config.yaml`, `iosxe_startup_config.j2`, `README.md`, `ssh_c1_le1`, `ssh_c3_le1`, `startup_config.py`, `tests/`, `vswitch.xml`.

Run: `uv run pymarkdown scan README.md`
Expected: no new findings (compare with `git stash; uv run pymarkdown scan README.md; git stash pop` if the file already had findings).

- [ ] **Step 4: `CLAUDE.md`**

Add a row to the layout table after the `config/8000v/` row:

```markdown
| `config/cat9kv/` | Catalyst 9000v (IOS-XE) launcher mirroring `config/8000v/`. `C1_LE1.yaml`/`C3_LE1.yaml` are the `CAMPUS1` leaves. See its README. |
```

In "Conventions", extend the hostname sentence: after "Roles: `BG` ..., `H` (host container)." add: "Catalyst 9000v campus leaves use `C<n>_LE<idx>` (`C1_LE1` on ND
4.2.1, `C3_LE1` on the ND 4.3.1 mirror); their `sid` uses SRII role digit `7` (1701, 3701) and their mgmt IPs the `.18x` block."

In "Two testbeds share one host" bullet, append: "Each controller also has a `CAMPUS1` campus fabric with one Catalyst 9000v leaf (`C1_LE1` / `C3_LE1`, `.181`)."

Run: `uv run pymarkdown scan CLAUDE.md`
Expected: no new findings.

- [ ] **Step 5: Commit**

```bash
git add config/ansible/dynamic_inventory.py env/02-ansible.sh README.md CLAUDE.md
git status --short   # must not list anything under env_prod/
git commit -m "inventory/env/docs: C1_LE1 and C3_LE1 campus leaves, CAMPUS1 fabric"
```

---

### Task 6: Bring both Cat9kv VMs up on glide (acceptance 1)

**Files:** none in the repo. Runs on `glide-wired.laukapu.com`.

**Interfaces:**

- Consumes: Tasks 1-3 on the branch; `/iso1/cml/cat9kv-17.15.03/cat9kv_prd.17.15.03.qcow2`; `env_prod/env.sh` on glide for `IOSXE_PASSWORD`.
- Produces: running QEMU processes named `C1_LE1` and `C3_LE1`; SSH reachable at 192.168.12.181 / 192.168.14.181.

- [ ] **Step 1: Push the branch and check it out on glide**

```bash
git push -u origin cat9kv-campus-leaf
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && git fetch origin && git checkout cat9kv-campus-leaf && git pull --ff-only && git log --oneline -1'
```

Expected: glide's checkout is at the branch head. Untracked `state*` dirs there are unaffected.

- [ ] **Step 2: Dry-run the launcher on glide (no sudo needed)**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm/config/cat9kv && python3 cat9kv.py --config C1_LE1.yaml --dry-run && python3 cat9kv.py --config C3_LE1.yaml --dry-run'
```

Expected: no "image not found" warning (the base image is present), the QEMU command, nine interface lines each.

- [ ] **Step 3: Build the ISOs and launch (needs sudo on glide, which prompts for a password)**

Ask the user to run, from their terminal:

```bash
! ssh -t glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh && cd config/cat9kv && sudo -E python3 startup_config.py --all \
  && sudo python3 cat9kv.py --config C1_LE1.yaml && sudo python3 cat9kv.py --config C3_LE1.yaml'
```

Expected: `Built /iso2/iosxe/config/C1_LE1.iso (serial CAT9KV1701)`, same for C3_LE1, then two "instance created" blocks with console ports 11701 / 13701.

- [ ] **Step 4: Watch the boot (up to 600 s)**

```bash
ssh glide-wired.laukapu.com 'pgrep -af "name C[13]_LE1" | grep -o "name C._LE1"; \
  for p in 11701 13701; do echo "== $p"; (sleep 1; printf "\r\n"; sleep 2) | timeout 6 telnet localhost $p 2>/dev/null | tail -5; done'
```

Poll every few minutes (Monitor or a background loop) until the console of each shows `Press RETURN to get started!` or `%SSH-5-ENABLED:`. If the console shows a loop on
`vswitch.xml` or a NIC-count error, record the message verbatim and bump `min_nics` to 25 in `global_config.yaml` as the fallback the spec allows.

- [ ] **Step 5: Verify SSH from glide**

```bash
ssh glide-wired.laukapu.com 'source ~/repos/n9kv-kvm/env_prod/env.sh; for ip in 192.168.12.181 192.168.14.181; \
  do sshpass -p "$IOSXE_PASSWORD" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 admin@$ip "show version | include Cisco IOS XE|uptime" ; done'
```

(If `sshpass` is absent on glide, run `ssh admin@192.168.12.181` interactively via `! ssh -t glide-wired.laukapu.com ssh admin@192.168.12.181`.) Expected: both answer
with the IOS-XE 17.15.03 version line. Also confirm `show version | include Processor board ID` prints `CAT9KV1701` / `CAT9KV3701`.

- [ ] **Step 6: Record findings**

If the day-0 config needed anything beyond the template (a `license boot level` line, SNMP), add it to `iosxe_startup_config.j2`, rebuild the ISO, and commit with a
message that states what the console demanded. Otherwise nothing to commit.

---

### Task 7: Provision `CAMPUS1` on both controllers (acceptance 2 and 3)

**Files:** none in the repo (unless a finding forces a provisioner change).

**Interfaces:**

- Consumes: Task 4 topology files; Task 6 running leaves; `env_prod/env.sh` (`ND_*`, `IOSXE_PASSWORD`).

- [ ] **Step 1: Dry run both controllers**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
  && uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 --phase fabrics --dry-run \
  && uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase fabrics --dry-run'
```

Expected: `SITE1`/`SITE2`/`ISN` report already applied; `CAMPUS1` shows a `would POST /fabrics` plus the settings merge.

- [ ] **Step 2: Create the fabrics**

Run the same two commands without `--dry-run`. Expected: HTTP 200/201 for the `CAMPUS1` create and PUT on each controller. If ND rejects the create body, print the
response, consult `mcp__nd-openapi__get_schema vxlanCampus` for the offending version, adjust `settings:` in both topology files, commit, and retry.

- [ ] **Step 3: Add the switches**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
  && uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd421.yaml --nd-ip 10.10.20.10 --phase switches'
```

then the 4.3.1 equivalent. Expected per controller: `shallowDiscovery` for `CAMPUS1` reports the leaf `manageable` with `model` `C9KV-UADP-8P` (or similar) and
`serialNumber` `CAT9KV1701`; the add succeeds; `wait_for_switches` returns; role `leaf` is already set; `config_deploy("CAMPUS1")` recalculates and deploys. The existing
fabrics are skipped (all switches present) apart from their idempotent recalculate + deploy.

If discovery reports `not manageable` with an SNMP reason, that is the "does ND want SNMPv3 on IOS-XE" unknown from the handoff: add the minimal `snmp-server` lines ND
asks for to the template, rebuild the ISO, apply them live over SSH, and re-run.

If the single-leaf deploy fails, capture the `deploymentHistory` lines the tool prints; a campus fabric with no spine may need `pendingConfig` inspection but must not
block acceptance 2.

- [ ] **Step 4: Acceptance 2 and 3 over the API**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh && python3 - <<EOF
import os, requests, urllib3
urllib3.disable_warnings()
for ip, serial in (("10.10.20.10", "CAT9KV1701"), ("10.10.20.20", "CAT9KV3701")):
    s = requests.Session(); s.verify = False
    s.post(f"https://{ip}/login", json={"userName": os.environ["ND_USERNAME"], "userPasswd": os.environ["ND_PASSWORD"], "domain": os.environ.get("ND_DOMAIN", "local")}).raise_for_status()
    sw = s.get(f"https://{ip}/api/v1/manage/fabrics/CAMPUS1/switches").json()["switches"]
    print(ip, [(x["hostname"], x["switchRole"], x.get("networkOSType"), x.get("discoveryStatus") or x.get("status")) for x in sw])
    ifs = s.get(f"https://{ip}/api/v1/manage/fabrics/CAMPUS1/switches/{serial}/interfaces").json()
    items = ifs.get("interfaces", ifs) if isinstance(ifs, dict) else ifs
    gi1 = [i for i in items if i.get("interfaceName") == "GigabitEthernet1/0/1"]
    print("  Gi1/0/1:", gi1[0].get("configData", {}).get("networkOS", {}).get("policy", {}).get("policyType") if gi1 else "MISSING")
EOF'
```

Expected: each controller prints `[('C?_LE1', 'leaf', 'ios-xe', 'manageable'...)]` and `Gi1/0/1: iosXeTrunkHost`. If the interfaces payload shape differs, print one raw
entry and adapt the field path; the acceptance is the value, not the script.

- [ ] **Step 5: Mirror proof**

```bash
ssh glide-wired.laukapu.com 'cd ~/repos/n9kv-kvm && source env_prod/env.sh \
  && uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421 --nd-ip 10.10.20.10 \
  && uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431 --nd-ip 10.10.20.20 \
  && uv run config/nd/provision/snapshot.py diff ~/tmp/snap_nd421 ~/tmp/snap_nd431 \
  --map S1_BG1=S3_BG1 --map S1_SP1=S3_SP1 --map S1_LE1=S3_LE1 --map S1_LE2=S3_LE2 --map S1_LE3=S3_LE3 --map S1_LE4=S3_LE4 \
  --map S1_TOR1=S3_TOR1 --map S2_BG1=S4_BG1 --map S2_SP1=S4_SP1 --map S2_LE1=S4_LE1 --map WAN1=WAN2 --map C1_LE1=C3_LE1; echo rc=$?'
```

Expected: `rc=0` (empty diff), or only differences that pre-date this change (compare against the 2026-09-08 state described in the provisioner README). Any
`CAMPUS1`-specific diff is a finding to fix.

- [ ] **Step 6: Commit any provisioner or template fix made along the way**

```bash
git status --short
git add <files changed by findings>
git commit -m "cat9kv: <what the lab demanded>"
```

---

### Task 8: Wire the collection inventories, open the PR

**Files:**

- Modify (outside the repo): `~/ansible_collections/cisco/inventory.nd_interface_ethernet_access`, `...ethernet_trunk_host`, `...ethernet_routed`

- [ ] **Step 1: Point the XE variables at the campus leaf (ND 4.2.1 inventories)**

In each of the three files, replace:

```ini
nd_test_xe_fabric_name=ISN
nd_test_xe_switch_ip=192.168.12.112
```

with:

```ini
nd_test_xe_fabric_name=CAMPUS1
nd_test_xe_switch_ip=192.168.12.181
# nd_test_xe_interface_name=GigabitEthernet1/0/1   (default; must not be a port-channel member or a fabric link)
```

Check: `grep -n nd_test_xe ~/ansible_collections/cisco/inventory.nd_interface_ethernet_*`.

- [ ] **Step 2: Push and open the PR**

```bash
git push
gh pr create --base main --head cat9kv-campus-leaf --title "Cat9kv campus leaf per controller (CAMPUS1) for the cisco.nd IOS-XE interface tests" --body-file - <<'EOF'
## Summary

- New `config/cat9kv/` launcher + day-0 generator for the CML Catalyst 9000v image (IDE/BIOS/e1000, 18 GiB, nine NICs padded with
  unattached TAPs, CDROM ISO with `iosxe_config.txt` + `conf/vswitch.xml` and a pinned serial).
- `C1_LE1` (ND 4.2.1, 192.168.12.181) and `C3_LE1` (ND 4.3.1, 192.168.14.181), sids 1701/3701, each the only member of a `vxlanCampus` fabric `CAMPUS1` (ASN 65003).
- Provisioner: `CAMPUS1` in both topology files; `_switch_password` keyed on switch platform.
- Inventory/env/README/CLAUDE.md updated.

Spec: `docs/superpowers/specs/2026-09-11-cat9kv-campus-leaf-design.md`. Plan: `docs/superpowers/plans/2026-09-11-cat9kv-campus-leaf.md`.

## Lab verification

- [ ] both leaves boot to `%SSH-5-ENABLED:` and answer SSH from glide
- [ ] `GET /fabrics/CAMPUS1/switches` lists the leaf as `leaf`, manageable, `ios-xe` on both controllers
- [ ] `GigabitEthernet1/0/1` shows `policyType iosXeTrunkHost`
- [ ] `snapshot.py diff` with `--map C1_LE1=C3_LE1` is empty

## Test plan

- `uv run pytest config/cat9kv/tests config/nd/provision/tests`
- `uv run black --check config/ && uv run flake8 config/`

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01KjuQjkFVryFN7Y6UT2MMdz
EOF
```

Fill in the lab-verification checkboxes from Tasks 6 and 7 before handing the PR to the user. The `xe.yaml` scenario runs (acceptance 4) are the user's to trigger from
the collection root.
