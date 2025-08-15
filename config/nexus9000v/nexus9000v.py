#!/usr/bin/env python3
"""
Nexus 9000v VM Manager

Manager for creating and configuring Cisco Nexus 9000v VMs using QEMU/KVM
with YAML-based configuration files.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol

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


@dataclass
class NetworkInterface:
    """Represents a network interface configuration."""

    name: str
    bridge: str
    mac: str
    interface_type: str = "e1000"


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

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.sid < 1 or self.sid > 255:
            raise ValueError(f"SID must be between 1-255, got {self.sid}")
        if len(self.neighbors) != len(self.isl_bridges):
            raise ValueError("Number of neighbors must match number of ISL bridges")


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

    def generate_mgmt_mac(self, sid: int, base_mac: str) -> str:
        """Generate management interface MAC."""
        return f"{base_mac}:{sid:02x}:00:01"

    def generate_ethernet_mac(self, sid: int, port: int, base_mac: str) -> str:
        """Generate ethernet interface MAC."""
        return f"{base_mac}:{sid:02x}:01:{port:02d}"


class QEMUCommandBuilder(ABC):  # pylint: disable=too-few-public-methods
    """Abstract base for QEMU command builders."""

    @abstractmethod
    def build_command(
        self,
        config: SwitchConfig,
        global_config: GlobalConfig,
        interfaces: List[NetworkInterface],
    ) -> List[str]:
        """Build QEMU command arguments."""
        raise NotImplementedError


class NexusQEMUBuilder(QEMUCommandBuilder):  # pylint: disable=too-few-public-methods
    """QEMU command builder for Nexus 9000v switches."""

    def build_command(
        self,
        config: SwitchConfig,
        global_config: GlobalConfig,
        interfaces: List[NetworkInterface],
    ) -> List[str]:
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
        """Build network interface arguments."""
        args = []
        for iface in interfaces:
            args.extend(
                [
                    "-netdev",
                    f"bridge,id={iface.name},br={iface.bridge}",
                    "-device",
                    f"{iface.interface_type},netdev={iface.name},mac={iface.mac}",
                ]
            )
        return args

    def _build_misc_args(self, config: SwitchConfig, global_config: GlobalConfig) -> List[str]:
        """Build miscellaneous arguments."""
        telnet_port = f"90{config.sid:02d}"
        monitor_port = f"44{config.sid:02d}"

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
    def get_disk_info(disk_path: Path) -> Dict[str, str]:
        """Get disk information."""
        try:
            result = subprocess.run(
                ["qemu-img", "info", str(disk_path)],
                capture_output=True,
                text=True,
                check=True,
            )
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
        mac_generator: MACAddressGenerator = None,
        qemu_builder: QEMUCommandBuilder = None,
    ):
        self.global_config = global_config
        self.mac_generator = mac_generator or StandardMACGenerator()
        self.qemu_builder = qemu_builder or NexusQEMUBuilder()
        self.disk_manager = DiskManager()

    def create_switch(self, config: SwitchConfig, dry_run: bool = False) -> Dict[str, any]:
        """Create and start a Nexus switch VM."""

        # Generate network interfaces
        interfaces = self._generate_interfaces(config)

        # Prepare VM disk
        if not dry_run:
            self._prepare_vm_disk(config)

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
        process = self._start_vm(qemu_cmd, config)

        return {
            "process_id": process.pid,
            "telnet_port": f"90{config.sid:02d}",
            "monitor_port": f"44{config.sid:02d}",
            "interfaces": interfaces,
            "config": config,
        }

    def _generate_interfaces(self, config: SwitchConfig) -> List[NetworkInterface]:
        """Generate network interface configurations."""
        interfaces = []
        interface_type = config.interface_type or self.global_config.default_interface_type

        # Management interface
        mgmt_mac = self.mac_generator.generate_mgmt_mac(config.sid, self.global_config.base_mac)
        interfaces.append(
            NetworkInterface(
                name="ND_DATA",
                bridge=config.mgmt_bridge,
                mac=mgmt_mac,
                interface_type=interface_type,
            )
        )

        # ISL interfaces
        for i, bridge in enumerate(config.isl_bridges, 1):
            eth_mac = self.mac_generator.generate_ethernet_mac(config.sid, i, self.global_config.base_mac)
            interfaces.append(
                NetworkInterface(
                    name=f"ISL_BRIDGE_{i}",
                    bridge=bridge,
                    mac=eth_mac,
                    interface_type=interface_type,
                )
            )

        return interfaces

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

    def _start_vm(self, qemu_cmd: List[str], config: SwitchConfig) -> subprocess.Popen:
        """Start the VM process."""
        try:
            # Start process
            process = subprocess.Popen(qemu_cmd)  # pylint: disable=consider-using-with

            print(f"{config.name} instance created.")
            print(f"Role: {config.role}")
            print(f"SID: {config.sid}")

            for i, neighbor in enumerate(config.neighbors):
                bridge = config.isl_bridges[i]
                print(f"{config.name} -> {neighbor}: {bridge}")

            print(f"\nConsole access: telnet localhost 90{config.sid:02d}")
            print(f"Monitor access: telnet localhost 44{config.sid:02d}")
            print(f"Process ID: {process.pid}")

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
        "base_mac": "52:54:00",
        "default_ram": 16384,
        "default_vcpus": 4,
        "default_disk_size": "32G",
        "default_interface_type": "e1000",
    }

    with open("global_config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(global_config, f, default_flow_style=False)
    print("Created global_config.yaml")

    # Switch configurations
    switches = [
        {
            "name": "ER1",
            "role": "Edge Router",
            "sid": 21,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["BG1", "BG2", "CR1"],
            "isl_bridges": ["BR_ER1_BG1", "BR_ER1_BG2", "BR_CR1_ER1"],
        },
        {
            "name": "BG1",
            "role": "Border Gateway",
            "sid": 31,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["ER1", "SP1"],
            "isl_bridges": ["BR_ER1_BG1", "BR_BG1_SP1"],
        },
        {
            "name": "BG2",
            "role": "Border Gateway",
            "sid": 32,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["ER1", "SP2"],
            "isl_bridges": ["BR_ER1_BG2", "BR_BG2_SP2"],
        },
        {
            "name": "CR1",
            "role": "Core Router",
            "sid": 11,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["ER1"],
            "isl_bridges": ["BR_CR1_ER1"],
        },
        {
            "name": "SP1",
            "role": "Spine Switch",
            "sid": 41,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["BG1", "LE1"],
            "isl_bridges": ["BR_BG1_SP1", "BR_SP1_LE1"],
        },
        {
            "name": "SP2",
            "role": "Spine Switch",
            "sid": 42,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["BG2", "LE2"],
            "isl_bridges": ["BR_BG2_SP2", "BR_SP2_LE2"],
        },
        {
            "name": "LE1",
            "role": "Leaf Switch",
            "sid": 51,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["SP1"],
            "isl_bridges": ["BR_SP1_LE1"],
            # Example of switch-specific overrides
            "ram": 8192,
            "vcpus": 2,
        },
        {
            "name": "LE2",
            "role": "Leaf Switch",
            "sid": 52,
            "mgmt_bridge": "BR_ND_DATA",
            "neighbors": ["SP2"],
            "isl_bridges": ["BR_SP2_LE2"],
            # Example of switch-specific overrides
            "ram": 8192,
            "vcpus": 2,
        },
    ]

    for switch in switches:
        filename = f"{switch['name']}.yaml"
        with open(filename, "w", encoding="utf-8") as f:
            yaml.dump(switch, f, default_flow_style=False)
        print(f"Created {filename}")


def main():
    """Main entry point."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="Nexus 9000v VM Manager")
    parser.add_argument("--config", type=Path, help="Switch configuration file (YAML)")
    parser.add_argument(
        "--global-config",
        type=Path,
        default=Path("global_config.yaml"),
        help="Global configuration file (default: global_config.yaml)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show command without executing")
    parser.add_argument("--create-samples", action="store_true", help="Create sample config files")
    parser.add_argument(
        "--list-switches",
        action="store_true",
        help="List all switch config files in current directory",
    )

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
        result = manager.create_switch(switch_config, dry_run=args.dry_run)

        if args.dry_run:
            print("QEMU Command:")
            print(result["command"])
            print("\nInterfaces:")
            for iface in result["interfaces"]:
                print(f"  {iface.name}: {iface.bridge} -> {iface.mac}")
            print("\nPorts:")
            print(f"  Telnet: 90{switch_config.sid:02d}")
            print(f"  Monitor: 44{switch_config.sid:02d}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
