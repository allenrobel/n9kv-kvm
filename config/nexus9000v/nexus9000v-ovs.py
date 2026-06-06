#!/usr/bin/env python3
"""
Nexus 9000v VM Manager

Manager for creating and configuring Cisco Nexus 9000v VMs using QEMU/KVM
with YAML-based configuration files.

Host networking uses Open vSwitch. TAP interfaces are created in Python and
attached to OVS bridges directly (QEMU's built-in bridge helper only speaks
Linux bridge and cannot attach to OVS). Each bridge is set to forward reserved
multicast frames (other-config:forward-bpdu=true) so LACP / STP / LLDP / CDP
PDUs cross the link -- without this, vPC peer-links never bundle.
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

    image_path: str = "/iso1/nxos"
    cdrom_path: str = "/iso2/nxos/config"
    bios_file: str = "/usr/share/ovmf/OVMF.fd"
    default_image: str = "nexus9300v64.10.3.8.M.qcow2"
    base_mac: str = "52:54:00"

    # Default VM settings
    default_ram: int = 16384
    default_vcpus: int = 4
    default_disk_size: str = "32G"
    default_interface_type: str = "e1000"

    # External storage settings
    default_external_storage_size: str = "20G"  # Add this
    external_storage_enabled: bool = True  # Add this


@dataclass
class NetworkInterface:
    """Represents a network interface configuration."""

    name: str
    bridge: str
    mac: str
    interface_type: str = "e1000"
    tap: Optional[str] = None  # host-side TAP device attached to the OVS bridge


@dataclass
class SwitchConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for a Nexus switch VM."""

    name: str
    role: str
    sid: int
    mgmt_bridge: str
    neighbors: List[str] = field(default_factory=list)
    isl_bridges: List[str] = field(default_factory=list)

    # Optional VM settings (will use globals if not specified)
    ram: Optional[int] = None
    vcpus: Optional[int] = None
    disk_size: Optional[str] = None
    interface_type: Optional[str] = None
    image_name: Optional[str] = None

    # External storage settings
    external_storage_size: Optional[str] = None  # Add this
    enable_external_storage: Optional[bool] = None  # Add this

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
        # Remove any quotes and whitespace
        base_mac = base_mac.strip().strip("\"'")

        # Validate format
        parts = base_mac.split(":")
        if len(parts) != 3:
            raise ValueError(f"Base MAC must have 3 octets (e.g., '52:54:00'), got: {base_mac}")

        # Validate each part is valid hex
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


class QEMUCommandBuilder(ABC):  # pylint: disable=too-few-public-methods
    """Abstract base for QEMU command builders."""

    @abstractmethod
    def build_command(self, config: SwitchConfig, global_config: GlobalConfig, interfaces: List[NetworkInterface]) -> List[str]:
        """Build QEMU command arguments."""
        raise NotImplementedError


class NexusQEMUBuilder(QEMUCommandBuilder):  # pylint: disable=too-few-public-methods
    """QEMU command builder for Nexus 9000v switches."""

    def build_command(self, config: SwitchConfig, global_config: GlobalConfig, interfaces: List[NetworkInterface]) -> List[str]:
        """Build complete QEMU command for Nexus switch."""

        # Validate required files
        self._validate_files(config, global_config)

        # Build command components
        cmd = ["qemu-system-x86_64"]
        cmd.extend(self._build_system_args(config))
        cmd.extend(self._build_cpu_memory_args(config, global_config))
        cmd.extend(self._build_storage_args(config, global_config))
        cmd.extend(self._build_network_args(interfaces))
        cmd.extend(self._build_misc_args(config, global_config))

        return cmd

    def _validate_files(self, config: SwitchConfig, global_config: GlobalConfig) -> None:
        """Validate required files exist."""
        bios_path = Path(global_config.bios_file)
        if not bios_path.exists():
            raise FileNotFoundError(f"BIOS file not found: {global_config.bios_file}\n" "Install with: sudo apt install ovmf")

        image_name = config.image_name or global_config.default_image
        image_path = Path(global_config.image_path) / image_name
        if not image_path.exists():
            raise FileNotFoundError(f"Nexus image not found: {image_path}")

    def _build_system_args(self, config: SwitchConfig) -> List[str]:
        """Build system-level QEMU arguments."""
        serial = f"00000000{config.sid}"
        return [
            "-smbios",
            f"type=1,manufacturer=Cisco,product=Nexus9000,serial={serial}",
            "-enable-kvm",
            "-machine",
            "type=q35,accel=kvm,kernel-irqchip=on",
            "-cpu",
            "host",
        ]

    def _build_cpu_memory_args(self, config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
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

    def _build_storage_args(self, config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
        """Build storage-related arguments."""
        cdrom_image = Path(global_config.cdrom_path) / f"{config.name}.iso"
        vm_disk = Path(global_config.cdrom_path) / f"{config.name}.qcow2"

        args = [
            "-device",
            "ahci,id=ahci0,bus=pcie.0",
            "-drive",
            f"file={cdrom_image},media=cdrom",
            "-drive",
            f"file={vm_disk},if=none,id=drive-sata-disk0,format=qcow2,cache=writethrough",
            "-device",
            "ide-hd,bus=ahci0.0,drive=drive-sata-disk0,bootindex=1",
        ]

        # Add external storage if enabled
        enable_external = config.enable_external_storage
        if enable_external is None:
            enable_external = global_config.external_storage_enabled

        if enable_external:
            external_disk = Path(global_config.cdrom_path) / f"{config.name}_external.qcow2"
            args.extend([
                "-drive",
                f"file={external_disk},if=none,id=drive-sata-disk1,format=qcow2,cache=writethrough",
                "-device",
                "ide-hd,bus=ahci0.1,drive=drive-sata-disk1",
            ])

        return args

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

    def _build_misc_args(self, config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
        """Build miscellaneous arguments."""
        telnet_port = config.telnet_port
        monitor_port = config.monitor_port

        return [
            "-rtc",
            "clock=host,base=localtime",
            "-nographic",
            "-bios",
            global_config.bios_file,
            "-serial",
            f"telnet:localhost:{telnet_port},server=on,wait=off",
            "-monitor",
            f"telnet:localhost:{monitor_port},server,nowait",
            "-name",
            config.name,
        ]


class ProcessValidator:  # pylint: disable=too-few-public-methods
    """Validates system requirements and process status."""

    @staticmethod
    def check_system_requirements() -> List[str]:
        """Check system requirements and return any issues."""
        issues = []

        # Check if running as root/sudo
        import os  # pylint: disable=import-outside-toplevel

        if os.geteuid() != 0:
            issues.append("Script should be run with sudo for TAP/OVS access")

        # Check if KVM is available
        try:
            subprocess.run(["kvm-ok"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            issues.append("KVM may not be available or kvm-ok not installed")

        # Check if bridges exist (we'll check this in the VM manager)
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

    @staticmethod
    def check_process_running(pid: int) -> bool:
        """Check if a process is still running."""
        try:
            import os  # pylint: disable=import-outside-toplevel

            os.kill(pid, 0)
            return True
        except OSError:
            return False


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

        Without this OVS silently drops 01:80:c2:00:00:0x frames and LACP
        peer-links never bundle. Idempotent, so safe to call per-port.
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


class DiskManager:
    """Manages VM disk operations."""

    @staticmethod
    def create_vm_disk(source_image: Path, dest_disk: Path, size: str) -> None:
        """Create VM disk from source image."""
        try:
            # Copy source image
            subprocess.run(["cp", str(source_image), str(dest_disk)], check=True)


            # Resize disk
            subprocess.run(["qemu-img", "resize", str(dest_disk), size], check=True)

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create VM disk: {e}") from e

    @staticmethod
    def create_external_storage(storage_path: Path, size: str) -> None:
        """Create external storage disk."""
        try:
            # Create a new qcow2 image for external storage
            subprocess.run(
                ["qemu-img", "create", "-f", "qcow2", str(storage_path), size],
                check=True
            )
            print(f"Created external storage: {storage_path} ({size})")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create external storage: {e}") from e

    @staticmethod
    def get_disk_info(disk_path: Path) -> Dict[str, str]:
        """Get disk information."""
        try:
            result = subprocess.run(["qemu-img", "info", str(disk_path)], capture_output=True, text=True, check=True)
            return {"output": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"error": str(e)}


class ConfigLoader:
    """Handles loading and merging of configuration files."""

    @staticmethod
    def load_global_config(config_path: Optional[Path] = None) -> GlobalConfig:
        """Load global configuration, with optional override file."""
        global_config = GlobalConfig()

        if config_path and config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                # Update global config with values from file
                for key, value in data.items():
                    if hasattr(global_config, key):
                        # Special handling for base_mac which might be parsed as time
                        if key == "base_mac":
                            if isinstance(value, str):
                                setattr(global_config, key, value)
                            else:
                                # Convert time object back to string format
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


class SwitchVMManager:  # pylint: disable=too-few-public-methods
    """Main manager for Nexus switch VMs."""

    def __init__(
        self,
        global_config: GlobalConfig,
        mac_generator: Optional[MACAddressGenerator] = None,
        qemu_builder: Optional[QEMUCommandBuilder] = None,
    ):
        self.global_config = global_config
        self.mac_generator = mac_generator or StandardMACGenerator()
        self.qemu_builder = qemu_builder or NexusQEMUBuilder()
        self.disk_manager = DiskManager()

    def create_switch(self, config: SwitchConfig, dry_run: bool = False, debug: bool = False) -> Dict[str, Any]:
        """Create and start a Nexus switch VM."""

        if debug:
            # Check system requirements
            issues = ProcessValidator.check_system_requirements()
            if issues:
                print("System requirement issues:")
                for issue in issues:
                    print(f"  - {issue}")
                print()

            # Check bridges
            all_bridges = [config.mgmt_bridge] + config.isl_bridges
            bridge_issues = ProcessValidator.check_bridges(all_bridges)
            if bridge_issues:
                print("Bridge issues:")
                for issue in bridge_issues:
                    print(f"  - {issue}")
                print()

        # Generate network interfaces
        interfaces = self._generate_interfaces(config)

        # Prepare VM disk and host networking
        if not dry_run:
            self._prepare_vm_disk(config)
            self._setup_network(interfaces)

        # Build QEMU command
        qemu_cmd = self.qemu_builder.build_command(config, self.global_config, interfaces)

        if dry_run:
            return {
                "command": " ".join(qemu_cmd),
                "interfaces": interfaces,
                "config": config,
                "global_config": self.global_config,
            }

        # Start VM
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
        """Deterministic, unique, <=15-char host TAP name (e.g. 'tap1501-1')."""
        name = f"tap{sid}-{index}"
        if len(name) > 15:  # IFNAMSIZ
            raise ValueError(f"TAP name exceeds 15 chars: {name}")
        return name

    def _generate_interfaces(self, config: SwitchConfig) -> List[NetworkInterface]:
        """Generate network interface configurations."""
        interfaces = []
        interface_type = config.interface_type or self.global_config.default_interface_type

        # Management interface (index 0)
        mgmt_mac = self.mac_generator.generate_mgmt_mac(config.sid, self.global_config.base_mac)
        interfaces.append(
            NetworkInterface(
                name="ND_DATA",
                bridge=config.mgmt_bridge,
                mac=mgmt_mac,
                interface_type=interface_type,
                tap=self._tap_name(config.sid, 0),
            )
        )

        # ISL interfaces (index 1..N)
        for i, bridge in enumerate(config.isl_bridges, 1):
            eth_mac = self.mac_generator.generate_ethernet_mac(config.sid, i, self.global_config.base_mac)
            interfaces.append(
                NetworkInterface(
                    name=f"ISL_BRIDGE_{i}",
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

    def teardown_switch(self, config: SwitchConfig) -> None:
        """Remove all TAP interfaces for a switch (run after stopping its VM)."""
        for iface in self._generate_interfaces(config):
            OVSPortManager.teardown_port(iface)
        print(f"Removed TAP interfaces for {config.name}")

    def _prepare_vm_disk(self, config: SwitchConfig) -> None:
        """Prepare VM disk image."""
        image_name = config.image_name or self.global_config.default_image
        source_image = Path(self.global_config.image_path) / image_name
        dest_disk = Path(self.global_config.cdrom_path) / f"{config.name}.qcow2"
        disk_size = config.disk_size or self.global_config.default_disk_size

        # Ensure destination directory exists
        dest_disk.parent.mkdir(parents=True, exist_ok=True)

        # Create VM disk
        self.disk_manager.create_vm_disk(source_image, dest_disk, disk_size)

        # Create external storage if enabled
        enable_external = config.enable_external_storage
        if enable_external is None:
            enable_external = self.global_config.external_storage_enabled

        if enable_external:
            external_size = config.external_storage_size or self.global_config.default_external_storage_size
            external_disk = Path(self.global_config.cdrom_path) / f"{config.name}_external.qcow2"

            # Only create if it doesn't already exist (to preserve data across restarts)
            if not external_disk.exists():
                self.disk_manager.create_external_storage(external_disk, external_size)
            else:
                print(f"Using existing external storage: {external_disk}")

    def _start_vm(self, qemu_cmd: List[str], config: SwitchConfig, debug: bool = False) -> subprocess.Popen:
        """Start the VM process."""
        try:
            if debug:
                print("QEMU Command:")
                print(" ".join(qemu_cmd))
                print("\n" + "=" * 50 + "\n")

            # Start process with proper output handling
            if debug:
                # In debug mode, show QEMU output
                process = subprocess.Popen(qemu_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

                # Give it a moment to start
                import time  # pylint: disable=import-outside-toplevel

                time.sleep(2)

                # Check if process is still running
                if process.poll() is not None:
                    # Process has exited, get output
                    output, _ = process.communicate()
                    print("QEMU process exited immediately. Output:")
                    print(output)
                    raise RuntimeError(f"QEMU process failed with exit code: {process.returncode}")

            else:
                # Normal mode - background process
                process = subprocess.Popen(qemu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # pylint: disable=consider-using-with

            print(f"{config.name} instance created.")
            print(f"Role: {config.role}")
            print(f"SID: {config.sid}")

            for i, neighbor in enumerate(config.neighbors):
                bridge = config.isl_bridges[i]
                print(f"{config.name} -> {neighbor}: {bridge}")

            print(f"\nConsole access: telnet localhost {config.telnet_port}")
            print(f"Monitor access: telnet localhost {config.monitor_port}")
            print(f"Process ID: {process.pid}")

            if debug:
                # Check process status after a moment
                import time  # pylint: disable=import-outside-toplevel

                time.sleep(1)
                if process.poll() is not None:
                    print(f"WARNING: Process {process.pid} has already exited!")
                else:
                    print(f"Process {process.pid} is running successfully")

            return process

        except Exception as e:
            raise RuntimeError(f"Failed to start VM: {e}") from e


def create_sample_configs():
    """Create sample configuration files."""

    # Global configuration
    global_config = {
        "image_path": "/iso1/nxos",
        "cdrom_path": "/iso2/nxos/config",
        "bios_file": "/usr/share/ovmf/OVMF.fd",
        "default_image": "nexus9300v64.10.3.8.M.qcow2",
        "base_mac": "52:54:00",  # Explicitly quoted to prevent YAML time parsing
        "default_ram": 16384,
        "default_vcpus": 4,
        "default_disk_size": "32G",
        "default_interface_type": "e1000",
        "default_external_storage_size": "20G",  # Add this
        "external_storage_enabled": True,  # Add this
    }

    with open("global_config.yaml", "w", encoding="utf-8") as f:
        # Use default_flow_style=False and allow_unicode=True for better formatting
        yaml.dump(global_config, f, default_flow_style=False, allow_unicode=True)
    print("Created global_config.yaml")

    # Switch configurations
    switches = [
        {
            "name": "S1_BG1",
            "role": "Border Gateway",
            "sid": 1301,
            "mgmt_bridge": "BR_ND_DATA_12",
            "neighbors": ["S2_BG1", "S1_SP1"],
            "isl_bridges": ["BR_ISN_S1_S2_1", "BR_S1_BG1_SP1_1"],
        },
        {
            "name": "S2_BG1",
            "role": "Border Gateway",
            "sid": 2301,
            "mgmt_bridge": "BR_ND_DATA_12",
            "neighbors": ["S1_BG1", "S2_SP1"],
            "isl_bridges": ["BR_ISN_S1_S2_1", "BR_S2_BG1_SP1_1"],
        },
        {
            "name": "S1_SP1",
            "role": "Spine Switch",
            "sid": 1401,
            "mgmt_bridge": "BR_ND_DATA_12",
            "neighbors": ["S1_BG1", "S1_LE1"],
            "isl_bridges": ["BR_S1_BG1_SP1_1", "BR_S1_SP1_LE1_1"],
        },
        {
            "name": "S2_SP1",
            "role": "Spine Switch",
            "sid": 2401,
            "mgmt_bridge": "BR_ND_DATA_12",
            "neighbors": ["S2_BG1", "S2_LE1"],
            "isl_bridges": ["BR_S2_BG1_SP1_1", "BR_S2_SP1_LE1_1"],
        },
        {
            "name": "S1_LE1",
            "role": "Leaf Switch",
            "sid": 1501,
            "mgmt_bridge": "BR_ND_DATA_12",
            "neighbors": ["S1_SP1"],
            "isl_bridges": ["BR_S1_SP1_LE1_1"],
            # Example of switch-specific overrides
            "ram": 8192,
            "vcpus": 2,
            "external_storage_size": "25G",
            "enable_external_storage": True
        },
        {
            "name": "S2_LE1",
            "role": "Leaf Switch",
            "sid": 2501,
            "mgmt_bridge": "BR_ND_DATA_12",
            "neighbors": ["S2_SP1"],
            "isl_bridges": ["BR_S2_SP1_LE1_1"],
            # Example of switch-specific overrides
            "ram": 8192,
            "vcpus": 2,
        },
    ]

    for switch in switches:
        filename = f"{switch['name']}.yaml"
        with open(filename, "w", encoding="utf-8") as f:
            yaml.dump(switch, f, default_flow_style=False, allow_unicode=True)
        print(f"Created {filename}")


def main():
    """Main entry point."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="Nexus 9000v VM Manager")
    parser.add_argument("--config", type=Path, help="Switch configuration file (YAML)")
    parser.add_argument("--global-config", type=Path, default=Path("global_config.yaml"), help="Global configuration file (default: global_config.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="Show command without executing")
    parser.add_argument("--teardown", action="store_true", help="Remove the switch's TAP interfaces and exit")
    parser.add_argument("--create-samples", action="store_true", help="Create sample config files")
    parser.add_argument("--list-switches", action="store_true", help="List all switch config files in current directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug output and show QEMU command/output")

    args = parser.parse_args()

    if args.create_samples:
        create_sample_configs()
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

    if not args.config:
        print("Error: --config required")
        print("Use --list-switches to see available configs")
        print("Use --create-samples to create sample configs")
        sys.exit(1)

    try:
        # Load configurations
        global_config = ConfigLoader.load_global_config(args.global_config)
        switch_config = ConfigLoader.load_switch_config(args.config)

        # Create VM manager
        manager = SwitchVMManager(global_config)

        # Create switch
        result = manager.create_switch(switch_config, dry_run=args.dry_run, debug=args.debug)

        if args.dry_run:
            print("QEMU Command:")
            print(result["command"])
            print("\nInterfaces:")
            for iface in result["interfaces"]:
                print(f"  {iface.name}: {iface.bridge} -> {iface.mac} (tap: {iface.tap})")
            print("\nPorts:")
            print(f"  Telnet: {switch_config.telnet_port}")
            print(f"  Monitor: {switch_config.monitor_port}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

