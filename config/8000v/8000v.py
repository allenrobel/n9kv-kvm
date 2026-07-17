#!/usr/bin/env python3
"""
Catalyst 8000V VM Manager

Manager for creating and configuring Cisco Catalyst 8000V (IOS-XE) VMs using
QEMU/KVM with YAML-based configuration files. Structurally mirrors
config/nexus9000v/nexus9000v.py; kept self-contained per repo convention.

Host networking uses Open vSwitch. TAP interfaces are created in Python and
attached to OVS bridges directly (QEMU's built-in bridge helper only speaks
Linux bridge and cannot attach to OVS). Each bridge is set to forward reserved
multicast frames (other-config:forward-bpdu=true) so LACP / STP / LLDP / CDP
PDUs cross the link.

The default image is the Serial + EFI variant, so the VM boots via OVMF
firmware and its console is on the serial port (telnet localhost 10000+sid).

IOS-XE numbers NICs flatly in PCI order:
  index 0 -> GigabitEthernet1 = management (mgmt_bridge)
  index i -> GigabitEthernet(i+1) = WAN/ISN link i (isl_bridges[i-1])
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

    image_path: str = "/iso1/iosxe"
    cdrom_path: str = "/iso2/iosxe/config"
    bios_file: str = "/usr/share/ovmf/OVMF.fd"
    default_image: str = "c8000v-universalk9_16G_serial_efi.17.15.05.qcow2"
    base_mac: str = "52:54:00"

    # Default VM settings. C8000V minimum RAM is 4096 MB.
    default_ram: int = 8192
    default_vcpus: int = 4
    default_disk_size: Optional[str] = None  # no resize by default; the 16G image variant carries its disk
    default_interface_type: str = "virtio-net-pci"


@dataclass
class NetworkInterface:
    """Represents a network interface configuration."""

    name: str
    bridge: str
    mac: str
    interface_type: str = "virtio-net-pci"
    tap: Optional[str] = None  # host-side TAP device attached to the OVS bridge


@dataclass
class RouterConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for a Catalyst 8000V router VM."""

    name: str
    role: str
    sid: int
    mgmt_bridge: str
    neighbors: List[str] = field(default_factory=list)
    isl_bridges: List[str] = field(default_factory=list)

    # Day-0 management config. Consumed by startup_config.py (which renders the
    # IOS-XE day-0 config / boot ISO); accepted here so the launcher and the
    # config generator share one per-router YAML schema. The launcher itself
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

    @property
    def telnet_port(self) -> int:
        """Telnet console port derived from sid (10000 + sid)."""
        return 10000 + self.sid

    @property
    def monitor_port(self) -> int:
        """QEMU monitor port derived from sid (20000 + sid)."""
        return 20000 + self.sid


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
    def validate_files(self, config: RouterConfig, global_config: GlobalConfig) -> List[str]:
        """Return a list of missing-file issues (empty if all present)."""
        raise NotImplementedError

    @abstractmethod
    def build_command(self, config: RouterConfig, global_config: GlobalConfig, interfaces: List[NetworkInterface]) -> List[str]:
        """Build QEMU command arguments."""
        raise NotImplementedError


class C8000vQEMUBuilder(QEMUCommandBuilder):
    """QEMU command builder for Catalyst 8000V routers."""

    def validate_files(self, config: RouterConfig, global_config: GlobalConfig) -> List[str]:
        """Return missing-file issues. The image is EFI, so OVMF is required."""
        issues = []
        if not Path(global_config.bios_file).exists():
            issues.append(f"BIOS file not found: {global_config.bios_file} (install with: sudo apt install ovmf)")

        image_name = config.image_name or global_config.default_image
        image_path = Path(global_config.image_path) / image_name
        if not image_path.exists():
            issues.append(f"C8000V image not found: {image_path}")
        return issues

    def build_command(self, config: RouterConfig, global_config: GlobalConfig, interfaces: List[NetworkInterface]) -> List[str]:
        """Build complete QEMU command for a C8000V router."""
        cmd = ["qemu-system-x86_64"]
        cmd.extend(self._build_system_args(config))
        cmd.extend(self._build_cpu_memory_args(config, global_config))
        cmd.extend(self._build_storage_args(config, global_config))
        cmd.extend(self._build_network_args(interfaces))
        cmd.extend(self._build_misc_args(config, global_config))
        return cmd

    def _build_system_args(self, config: RouterConfig) -> List[str]:
        """Build system-level QEMU arguments."""
        serial = f"00000000{config.sid}"
        return [
            "-smbios",
            f"type=1,manufacturer=Cisco,product=C8000V,serial={serial}",
            "-enable-kvm",
            "-machine",
            "type=q35,accel=kvm,kernel-irqchip=on",
            "-cpu",
            "host",
        ]

    def _build_cpu_memory_args(self, config: RouterConfig, global_config: GlobalConfig) -> List[str]:
        """Build CPU and memory arguments."""
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

    def _build_storage_args(self, config: RouterConfig, global_config: GlobalConfig) -> List[str]:
        """Build storage-related arguments (per-VM disk + day-0 cdrom ISO)."""
        cdrom_image = Path(global_config.cdrom_path) / f"{config.name}.iso"
        vm_disk = Path(global_config.cdrom_path) / f"{config.name}.qcow2"

        return [
            "-device",
            "ahci,id=ahci0,bus=pcie.0",
            "-drive",
            f"file={cdrom_image},media=cdrom",
            "-drive",
            f"file={vm_disk},if=none,id=drive-sata-disk0,format=qcow2,cache=writethrough",
            "-device",
            "ide-hd,bus=ahci0.0,drive=drive-sata-disk0,bootindex=1",
        ]

    def _build_network_args(self, interfaces: List[NetworkInterface]) -> List[str]:
        """Build network interface arguments.

        TAPs are pre-created and attached to OVS by OVSPortManager, so QEMU
        must NOT manage them: script=no / downscript=no.
        """
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

    def _build_misc_args(self, config: RouterConfig, global_config: GlobalConfig) -> List[str]:
        """Build miscellaneous arguments (serial console, monitor, EFI bios)."""
        return [
            "-rtc",
            "clock=host,base=localtime",
            "-nographic",
            "-bios",
            global_config.bios_file,
            "-serial",
            f"telnet:localhost:{config.telnet_port},server=on,wait=off",
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
        """Create iface.tap, attach to iface.bridge on OVS, bring it up.

        Idempotent: any stale tap/port of the same name is cleared first.
        """
        if not iface.tap:
            raise ValueError(f"Interface '{iface.name}' has no TAP name assigned")
        if not cls.bridge_exists(iface.bridge):
            raise RuntimeError(
                f"OVS bridge '{iface.bridge}' not found. "
                f"Create it first via netplan / bridges_config.sh."
            )
        cls.teardown_port(iface)  # clear stale state from a prior run
        cls._run(["ip", "tuntap", "add", "dev", iface.tap, "mode", "tap"])
        cls._run(["ip", "link", "set", "dev", iface.tap, "mtu", str(cls.MTU)])
        cls._run(["ovs-vsctl", "--may-exist", "add-port", iface.bridge, iface.tap])
        cls._run(["ovs-vsctl", "set", "int", iface.tap, f"mtu_request={cls.MTU}"])
        cls.ensure_forward_bpdu(iface.bridge)
        cls._run(["ip", "link", "set", "dev", iface.tap, "up"])

    @classmethod
    def teardown_port(cls, iface: NetworkInterface) -> None:
        """Remove iface.tap from OVS and delete it. Safe if already absent."""
        if not iface.tap:
            return
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
    def load_router_config(config_path: Path) -> RouterConfig:
        """Load router configuration from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Router config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return RouterConfig(**data)


class RouterVMManager:
    """Main manager for Catalyst 8000V router VMs."""

    def __init__(
        self,
        global_config: GlobalConfig,
        mac_generator: Optional[MACAddressGenerator] = None,
        qemu_builder: Optional[QEMUCommandBuilder] = None,
    ):
        self.global_config = global_config
        self.mac_generator = mac_generator or StandardMACGenerator()
        self.qemu_builder = qemu_builder or C8000vQEMUBuilder()
        self.disk_manager = DiskManager()

    def create_router(self, config: RouterConfig, dry_run: bool = False, debug: bool = False) -> Dict[str, Any]:
        """Create and start a C8000V router VM."""

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
        # so the command can be inspected on machines without /iso1, /iso2, OVMF.
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
        """Deterministic, unique, <=15-char host TAP name (e.g. 'tap9101-1')."""
        name = f"tap{sid}-{index}"
        if len(name) > 15:  # IFNAMSIZ
            raise ValueError(f"TAP name exceeds 15 chars: {name}")
        return name

    def _generate_interfaces(self, config: RouterConfig) -> List[NetworkInterface]:
        """Generate network interface configurations.

        Index 0 is GigabitEthernet1 (management); index i is GigabitEthernet(i+1).
        """
        interfaces = []
        interface_type = config.interface_type or self.global_config.default_interface_type

        mgmt_mac = self.mac_generator.generate_mgmt_mac(config.sid, self.global_config.base_mac)
        interfaces.append(
            NetworkInterface(
                name="MGMT",
                bridge=config.mgmt_bridge,
                mac=mgmt_mac,
                interface_type=interface_type,
                tap=self._tap_name(config.sid, 0),
            )
        )

        for i, bridge in enumerate(config.isl_bridges, 1):
            eth_mac = self.mac_generator.generate_ethernet_mac(config.sid, i, self.global_config.base_mac)
            interfaces.append(
                NetworkInterface(
                    name=f"WAN_{i}",
                    bridge=bridge,
                    mac=eth_mac,
                    interface_type=interface_type,
                    tap=self._tap_name(config.sid, i),
                )
            )

        return interfaces

    def _setup_network(self, interfaces: List[NetworkInterface]) -> None:
        """Create TAPs and attach them to their OVS bridges."""
        for iface in interfaces:
            OVSPortManager.setup_port(iface)

    def teardown_router(self, config: RouterConfig) -> None:
        """Remove all TAP interfaces for a router (run after stopping its VM)."""
        for iface in self._generate_interfaces(config):
            OVSPortManager.teardown_port(iface)
        print(f"Removed TAP interfaces for {config.name}")

    def _prepare_vm_disk(self, config: RouterConfig) -> None:
        """Prepare the per-VM disk image."""
        image_name = config.image_name or self.global_config.default_image
        source_image = Path(self.global_config.image_path) / image_name
        dest_disk = Path(self.global_config.cdrom_path) / f"{config.name}.qcow2"
        disk_size = config.disk_size or self.global_config.default_disk_size

        dest_disk.parent.mkdir(parents=True, exist_ok=True)
        self.disk_manager.create_vm_disk(source_image, dest_disk, disk_size)

    def _start_vm(self, qemu_cmd: List[str], config: RouterConfig, debug: bool = False) -> subprocess.Popen[Any]:
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

            for i, neighbor in enumerate(config.neighbors):
                bridge = config.isl_bridges[i]
                print(f"{config.name} GigabitEthernet{i + 2} -> {neighbor}: {bridge}")

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


def main():
    """Main entry point."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="Catalyst 8000V VM Manager")
    parser.add_argument("--config", type=Path, help="Router configuration file (YAML)")
    parser.add_argument("--global-config", type=Path, default=Path("global_config.yaml"), help="Global configuration file (default: global_config.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="Show command without executing")
    parser.add_argument("--teardown", action="store_true", help="Remove the router's TAP interfaces and exit")
    parser.add_argument("--create-samples", action="store_true", help="Create sample config files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing sample files (used with --create-samples)")
    parser.add_argument("--list-routers", action="store_true", help="List all router config files in current directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug output and show QEMU command/output")

    args = parser.parse_args()

    if args.create_samples:
        create_sample_configs(force=args.force)
        return

    if args.list_routers:
        router_files = list(Path.cwd().glob("*.yaml"))
        router_files = [f for f in router_files if f.name != "global_config.yaml"]
        print("Available router configurations:")
        for f in sorted(router_files):
            print(f"  {f.name}")
        return

    if args.teardown:
        if not args.config:
            print("Error: --teardown requires --config")
            sys.exit(1)
        global_config = ConfigLoader.load_global_config(args.global_config)
        router_config = ConfigLoader.load_router_config(args.config)
        RouterVMManager(global_config).teardown_router(router_config)
        return

    if not args.config:
        print("Error: --config required")
        print("Use --list-routers to see available configs")
        print("Use --create-samples to create sample configs")
        sys.exit(1)

    try:
        global_config = ConfigLoader.load_global_config(args.global_config)
        router_config = ConfigLoader.load_router_config(args.config)

        manager = RouterVMManager(global_config)

        result = manager.create_router(router_config, dry_run=args.dry_run, debug=args.debug)

        if args.dry_run:
            print("QEMU Command:")
            print(result["command"])
            print("\nInterfaces:")
            for i, iface in enumerate(result["interfaces"]):
                print(f"  GigabitEthernet{i + 1} ({iface.name}): {iface.bridge} -> {iface.mac} (tap: {iface.tap})")
            print("\nPorts:")
            print(f"  Telnet: {router_config.telnet_port}")
            print(f"  Monitor: {router_config.monitor_port}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
