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
  index i -> GigabitEthernet1/0/i = front-panel port i (the isl_bridges entry whose isl_ports value is i, or padding)
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)


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


@dataclass
class NetworkInterface:
    """Represents a network interface configuration."""

    name: str
    bridge: Optional[str]  # None = padding NIC: TAP exists so the guest sees a port, but it is attached to no bridge
    mac: str
    interface_type: str = "e1000"
    tap: Optional[str] = None  # host-side TAP device


@dataclass
class SwitchConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for a Catalyst 9000v switch VM."""

    name: str
    role: str
    sid: int
    mgmt_bridge: str
    neighbors: List[str] = field(default_factory=list)
    isl_bridges: List[str] = field(default_factory=list)
    # Front-panel port number for each isl_bridges entry (GigabitEthernet1/0/<port>). Defaults to 1..N. Lets a link sit on a
    # non-contiguous port (the campus leaf keeps 1/0/1..1/0/7 free for the cisco.nd tests and carries its spine link on 1/0/8).
    isl_ports: List[int] = field(default_factory=list)

    # Day-0 management config. Consumed by startup_config.py (which renders the
    # IOS-XE day-0 config / boot ISO); accepted here so the launcher and the
    # config generator share one per-switch YAML schema. The launcher itself
    # derives mgmt wiring from mgmt_bridge and does not use these directly.
    mgmt_ip: Optional[str] = None
    mgmt_gw: Optional[str] = None

    # Optional VM settings (will use globals if not specified)
    ram: Optional[int] = None
    vcpus: Optional[int] = None
    disk_size: Optional[str] = None
    interface_type: Optional[str] = None
    image_name: Optional[str] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.sid < 1000 or self.sid > 9999:
            raise ValueError(f"SID must be a 4-digit value between 1000-9999, got {self.sid}")
        if len(self.neighbors) != len(self.isl_bridges):
            raise ValueError("Number of neighbors must match number of ISL bridges")
        if not self.isl_ports:
            self.isl_ports = list(range(1, len(self.isl_bridges) + 1))
        else:
            self.isl_ports = [int(port) for port in self.isl_ports]  # YAML may hand back a string ("8"); coerce, don't reject
        if len(self.isl_ports) != len(self.isl_bridges):
            raise ValueError("Number of isl_ports must match number of ISL bridges")
        if len(set(self.isl_ports)) != len(self.isl_ports) or any(port < 1 for port in self.isl_ports):
            raise ValueError(f"isl_ports must be unique front-panel port numbers >= 1, got {self.isl_ports}")
        if any(port > 48 for port in self.isl_ports):
            raise ValueError(f"isl_ports must be <= 48 (highest front-panel port on any platform this launcher supports), got {self.isl_ports}")

    @property
    def telnet_port(self) -> int:
        """Telnet console port derived from sid (10000 + sid)."""
        return 10000 + self.sid

    @property
    def monitor_port(self) -> int:
        """QEMU monitor port derived from sid (20000 + sid)."""
        return 20000 + self.sid

    @property
    def serial(self) -> str:
        """Switch serial written into the day-0 conf/vswitch.xml (ND keys the switch on it; pinning it avoids
        serial churn on reload). startup_config.py derives the same value from the same YAML."""
        return f"CAT9KV{self.sid}"


def guest_interface(index: int) -> str:
    """IOS-XE name of the NIC at PCI index `index`: 0 is management, 1..N are front-panel ports."""
    return "GigabitEthernet0/0" if index == 0 else f"GigabitEthernet1/0/{index}"


class MACAddressGenerator(Protocol):
    """Protocol for MAC address generation strategies."""

    def generate_mgmt_mac(self, sid: int, base_mac: str) -> str:
        """Generate management interface MAC address."""
        raise NotImplementedError

    def generate_ethernet_mac(self, sid: int, port: int, base_mac: str) -> str:
        """Generate ethernet interface MAC address."""
        raise NotImplementedError


class StandardMACGenerator:
    """Standard MAC address generator using predictable format."""

    def _validate_base_mac(self, base_mac: str) -> str:
        """Validate and normalize base MAC address."""
        base_mac = base_mac.strip().strip("\"'")

        parts = base_mac.split(":")
        if len(parts) != 3:
            raise ValueError(f"Base MAC must have 3 octets (e.g., '52:54:00'), got: {base_mac}")

        try:
            for part in parts:
                int(part, 16)
        except ValueError as exc:
            raise ValueError(f"Invalid hex in base MAC: {base_mac}") from exc

        return base_mac

    def generate_mgmt_mac(self, sid: int, base_mac: str) -> str:
        """Generate management interface MAC."""
        base_mac = self._validate_base_mac(base_mac)
        # split the 4-digit decimal sid into two 2-digit halves: octet4=sid_hi, octet6=sid_lo
        sid_hi, sid_lo = divmod(sid, 100)
        return f"{base_mac}:{sid_hi:02x}:00:{sid_lo:02x}"

    def generate_ethernet_mac(self, sid: int, port: int, base_mac: str) -> str:
        """Generate ethernet interface MAC."""
        base_mac = self._validate_base_mac(base_mac)
        # split the 4-digit decimal sid into two 2-digit halves: octet4=sid_hi, octet6=sid_lo
        sid_hi, sid_lo = divmod(sid, 100)
        return f"{base_mac}:{sid_hi:02x}:{port:02x}:{sid_lo:02x}"


class QEMUCommandBuilder(ABC):
    """Abstract base for QEMU command builders."""

    @abstractmethod
    def validate_files(self, config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
        """Return a list of missing-file issues (empty if all present)."""
        raise NotImplementedError

    @abstractmethod
    def build_command(self, config: SwitchConfig, global_config: GlobalConfig, interfaces: List[NetworkInterface]) -> List[str]:
        """Build QEMU command arguments."""
        raise NotImplementedError


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


class ProcessValidator:  # pylint: disable=too-few-public-methods
    """Validates system requirements and process status."""

    @staticmethod
    def check_system_requirements() -> List[str]:
        """Check system requirements and return any issues."""
        issues = []

        import os  # pylint: disable=import-outside-toplevel

        if os.geteuid() != 0:
            issues.append("Script should be run with sudo for TAP/OVS access")

        try:
            subprocess.run(["kvm-ok"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            issues.append("KVM may not be available or kvm-ok not installed")

        return issues

    @staticmethod
    def check_bridges(bridges: List[str]) -> List[str]:
        """Check if required OVS bridges exist."""
        issues = []
        try:
            for bridge in bridges:
                # `ovs-vsctl br-exists` exits 0 if present, 2 if not.
                result = subprocess.run(["ovs-vsctl", "br-exists", bridge], capture_output=True, check=False)
                if result.returncode != 0:
                    issues.append(f"OVS bridge '{bridge}' not found")
        except FileNotFoundError:
            issues.append("ovs-vsctl not found - is openvswitch-switch installed?")

        return issues


class OVSPortManager:
    """Creates host TAP interfaces and attaches them to OVS bridges.

    Replaces QEMU's built-in bridge helper (-netdev bridge,...), which only
    speaks Linux bridge and cannot attach to Open vSwitch.
    """

    MTU = 9216

    @staticmethod
    def _run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    @classmethod
    def bridge_exists(cls, bridge: str) -> bool:
        # `ovs-vsctl br-exists` exits 0 if present, 2 if not.
        return cls._run(["ovs-vsctl", "br-exists", bridge], check=False).returncode == 0

    @classmethod
    def ensure_forward_bpdu(cls, bridge: str) -> None:
        """Make the bridge forward LACP/STP/LLDP/CDP (reserved multicast).

        Without this OVS silently drops 01:80:c2:00:00:0x frames. Idempotent,
        so safe to call per-port.
        """
        cls._run(["ovs-vsctl", "set", "bridge", bridge, "other-config:forward-bpdu=true"])

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

    @classmethod
    def teardown_port(cls, iface: NetworkInterface) -> None:
        """Remove iface.tap from OVS (if attached) and delete it. Safe if already absent."""
        if not iface.tap:
            return
        if iface.bridge is not None:
            cls._run(["ovs-vsctl", "--if-exists", "del-port", iface.bridge, iface.tap], check=False)
        cls._run(["ip", "link", "del", "dev", iface.tap], check=False)


class DiskManager:  # pylint: disable=too-few-public-methods
    """Manages VM disk operations."""

    @staticmethod
    def create_vm_disk(source_image: Path, dest_disk: Path, size: Optional[str]) -> None:
        """Create the per-VM disk from the base image; resize only if size is set."""
        try:
            subprocess.run(["cp", str(source_image), str(dest_disk)], check=True)
            if size:
                subprocess.run(["qemu-img", "resize", str(dest_disk), size], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create VM disk: {e}") from e


class ConfigLoader:
    """Handles loading and merging of configuration files."""

    @staticmethod
    def load_global_config(config_path: Optional[Path] = None) -> GlobalConfig:
        """Load global configuration, with optional override file."""
        global_config = GlobalConfig()

        if config_path and config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                for key, value in data.items():
                    if hasattr(global_config, key):
                        # base_mac can be parsed as a time by YAML; force str
                        if key == "base_mac" and not isinstance(value, str):
                            setattr(global_config, key, str(value))
                        else:
                            setattr(global_config, key, value)

        return global_config

    @staticmethod
    def load_switch_config(config_path: Path) -> SwitchConfig:
        """Load switch configuration from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Switch config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return SwitchConfig(**data)


class SwitchVMManager:
    """Main manager for Catalyst 9000v switch VMs."""

    def __init__(
        self,
        global_config: GlobalConfig,
        mac_generator: Optional[MACAddressGenerator] = None,
        qemu_builder: Optional[QEMUCommandBuilder] = None,
    ):
        self.global_config = global_config
        self.mac_generator = mac_generator or StandardMACGenerator()
        self.qemu_builder = qemu_builder or Cat9kvQEMUBuilder()
        self.disk_manager = DiskManager()

    def create_switch(self, config: SwitchConfig, dry_run: bool = False, debug: bool = False) -> Dict[str, Any]:
        """Create and start a Cat9kv switch VM."""

        if debug:
            issues = ProcessValidator.check_system_requirements()
            if issues:
                print("System requirement issues:")
                for issue in issues:
                    print(f"  - {issue}")
                print()

            all_bridges = [config.mgmt_bridge] + config.isl_bridges
            bridge_issues = ProcessValidator.check_bridges(all_bridges)
            if bridge_issues:
                print("Bridge issues:")
                for issue in bridge_issues:
                    print(f"  - {issue}")
                print()

        # Missing lab files abort a real launch but only warn in --dry-run,
        # so the command can be inspected on machines without /iso1, /iso2.
        file_issues = self.qemu_builder.validate_files(config, self.global_config)
        if file_issues:
            if dry_run:
                for issue in file_issues:
                    print(f"Warning: {issue}")
            else:
                raise FileNotFoundError("; ".join(file_issues))

        interfaces = self._generate_interfaces(config)

        if not dry_run:
            self._prepare_vm_disk(config)
            self._setup_network(interfaces)

        qemu_cmd = self.qemu_builder.build_command(config, self.global_config, interfaces)

        if dry_run:
            return {
                "command": " ".join(qemu_cmd),
                "interfaces": interfaces,
                "config": config,
                "global_config": self.global_config,
            }

        process = self._start_vm(qemu_cmd, config, debug=debug)

        return {
            "process_id": process.pid,
            "telnet_port": config.telnet_port,
            "monitor_port": config.monitor_port,
            "interfaces": interfaces,
            "config": config,
        }

    @staticmethod
    def _tap_name(sid: int, index: int) -> str:
        """Deterministic, unique, <=15-char host TAP name (e.g. 'tap1701-1')."""
        name = f"tap{sid}-{index}"
        if len(name) > 15:  # IFNAMSIZ
            raise ValueError(f"TAP name exceeds 15 chars: {name}")
        return name

    def _generate_interfaces(self, config: SwitchConfig) -> List[NetworkInterface]:
        """Generate network interface configurations.

        Index 0 is GigabitEthernet0/0 (management); index i is GigabitEthernet1/0/i. Front-panel slots not named in
        isl_ports are padded up to `max(min_nics, highest port + 1)` with TAPs attached to no bridge.
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

    def _setup_network(self, interfaces: List[NetworkInterface]) -> None:
        """Create TAPs and attach them to their OVS bridges."""
        for iface in interfaces:
            OVSPortManager.setup_port(iface)

    def teardown_switch(self, config: SwitchConfig) -> None:
        """Remove all TAP interfaces for a switch (run after stopping its VM)."""
        for iface in self._generate_interfaces(config):
            OVSPortManager.teardown_port(iface)
        print(f"Removed TAP interfaces for {config.name}")

    def attach_switch(self, config: SwitchConfig) -> None:
        """Attach a running switch's existing TAPs to the bridges the YAML names (re-cable without a reload).
        Attaches only; it does not remove a TAP from a bridge that the YAML no longer names."""
        for iface in self._generate_interfaces(config):
            OVSPortManager.attach_port(iface)
            if iface.bridge is not None:
                print(f"{config.name} {iface.tap} -> {iface.bridge}")

    def _prepare_vm_disk(self, config: SwitchConfig) -> None:
        """Prepare the per-VM disk image."""
        image_name = config.image_name or self.global_config.default_image
        source_image = Path(self.global_config.image_path) / image_name
        dest_disk = Path(self.global_config.cdrom_path) / f"{config.name}.qcow2"
        disk_size = config.disk_size or self.global_config.default_disk_size

        dest_disk.parent.mkdir(parents=True, exist_ok=True)
        self.disk_manager.create_vm_disk(source_image, dest_disk, disk_size)

    def _start_vm(self, qemu_cmd: List[str], config: SwitchConfig, debug: bool = False) -> subprocess.Popen[Any]:
        """Start the VM process."""
        try:
            if debug:
                print("QEMU Command:")
                print(" ".join(qemu_cmd))
                print("\n" + "=" * 50 + "\n")

            if debug:
                process: subprocess.Popen[Any] = subprocess.Popen(qemu_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

                import time  # pylint: disable=import-outside-toplevel

                time.sleep(2)

                if process.poll() is not None:
                    output, _ = process.communicate()
                    print("QEMU process exited immediately. Output:")
                    print(output)
                    raise RuntimeError(f"QEMU process failed with exit code: {process.returncode}")

            else:
                process = subprocess.Popen(qemu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # pylint: disable=consider-using-with

            print(f"{config.name} instance created.")
            print(f"Role: {config.role}")
            print(f"SID: {config.sid}")

            for port, neighbor, bridge in zip(config.isl_ports, config.neighbors, config.isl_bridges):
                print(f"{config.name} {guest_interface(port)} -> {neighbor}: {bridge}")

            print(f"\nConsole access: telnet localhost {config.telnet_port}")
            print(f"Monitor access: telnet localhost {config.monitor_port}")
            print(f"Process ID: {process.pid}")

            if debug:
                import time  # pylint: disable=import-outside-toplevel

                time.sleep(1)
                if process.poll() is not None:
                    print(f"WARNING: Process {process.pid} has already exited!")
                else:
                    print(f"Process {process.pid} is running successfully")

            return process

        except Exception as e:
            raise RuntimeError(f"Failed to start VM: {e}") from e


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
            "neighbors": ["C1_SP1"],
            "isl_bridges": ["BR_C1_SP1_LE1_1"],
            "isl_ports": [8],
        },
    ]

    for switch in switches:
        _write_sample(out_dir / f"{switch['name']}.yaml", switch, force)


def main():
    """Main entry point."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="Catalyst 9000v VM Manager")
    parser.add_argument("--config", type=Path, help="Switch configuration file (YAML)")
    parser.add_argument("--global-config", type=Path, default=Path("global_config.yaml"), help="Global configuration file (default: global_config.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="Show command without executing")
    parser.add_argument("--teardown", action="store_true", help="Remove the switch's TAP interfaces and exit")
    parser.add_argument(
        "--attach",
        action="store_true",
        help="Attach the running switch's existing TAPs to their bridges (re-cable live) and exit; attaches only, does not remove a TAP "
        "from a bridge the YAML no longer names",
    )
    parser.add_argument("--create-samples", action="store_true", help="Create sample config files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing sample files (used with --create-samples)")
    parser.add_argument("--list-switches", action="store_true", help="List all switch config files in current directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug output and show QEMU command/output")

    args = parser.parse_args()

    if args.create_samples:
        create_sample_configs(force=args.force)
        return

    if args.list_switches:
        switch_files = list(Path.cwd().glob("*.yaml"))
        switch_files = [f for f in switch_files if f.name != "global_config.yaml"]
        print("Available switch configurations:")
        for f in sorted(switch_files):
            print(f"  {f.name}")
        return

    if args.teardown:
        if not args.config:
            print("Error: --teardown requires --config")
            sys.exit(1)
        global_config = ConfigLoader.load_global_config(args.global_config)
        switch_config = ConfigLoader.load_switch_config(args.config)
        SwitchVMManager(global_config).teardown_switch(switch_config)
        return

    if args.attach:
        if not args.config:
            print("Error: --attach requires --config")
            sys.exit(1)
        global_config = ConfigLoader.load_global_config(args.global_config)
        switch_config = ConfigLoader.load_switch_config(args.config)
        SwitchVMManager(global_config).attach_switch(switch_config)
        return

    if not args.config:
        print("Error: --config required")
        print("Use --list-switches to see available configs")
        print("Use --create-samples to create sample configs")
        sys.exit(1)

    try:
        global_config = ConfigLoader.load_global_config(args.global_config)
        switch_config = ConfigLoader.load_switch_config(args.config)

        manager = SwitchVMManager(global_config)

        result = manager.create_switch(switch_config, dry_run=args.dry_run, debug=args.debug)

        if args.dry_run:
            print("QEMU Command:")
            print(result["command"])
            print("\nInterfaces:")
            for i, iface in enumerate(result["interfaces"]):
                print(f"  {guest_interface(i)} ({iface.name}): {iface.bridge or '(unattached)'} -> {iface.mac} (tap: {iface.tap})")
            print("\nPorts:")
            print(f"  Telnet: {switch_config.telnet_port}")
            print(f"  Monitor: {switch_config.monitor_port}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
