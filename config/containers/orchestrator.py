#!/usr/bin/env python3
"""
Container creation orchestrator
"""

import logging
from pathlib import Path
from typing import List

from bridge import BridgeVLANManager
from filesystem import FileSystemManager
from interfaces import CommandExecutor, ConfigurationGenerator
from libvirt_manager import LibvirtDomainManager, LibvirtXMLGenerator
from models import ContainerSpec
from packages import PackageInstaller
from rootfs import RootfsBuilder

logger = logging.getLogger(__name__)


class ContainerOrchestrator:
    """Orchestrates container creation process"""

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
        self.package_installer: PackageInstaller = package_installer
        self.config_generators: List[ConfigurationGenerator] = config_generators
        self.xml_generator: LibvirtXMLGenerator = xml_generator
        self.domain_manager: LibvirtDomainManager = domain_manager

    def create_container(self, spec: ContainerSpec, force_ipv4: bool = True) -> None:
        """Create complete container"""
        logger.info(f"Creating container: {spec.name}")

        try:
            # Setup bridge VLANs
            self._setup_bridge_vlans(spec)

            # Create filesystem structure
            self.fs_manager.create_container_directories(spec.name)

            # Create rootfs
            self.rootfs_builder.create_ubuntu_rootfs(spec.name, force_ipv4=force_ipv4)

            # Install packages
            self.package_installer.install_packages(spec.name)

            # Generate configurations
            self._generate_configurations(spec)

            # Create and define libvirt domain
            self._create_libvirt_domain(spec)

            logger.info(f"Container {spec.name} created successfully!")
            self._print_usage_info(spec)

        except Exception as e:
            logger.error(f"Failed to create container {spec.name}: {e}")
            raise

    def _setup_bridge_vlans(self, spec: ContainerSpec) -> None:
        """Setup bridge VLAN configuration"""
        vlan_ids: List[int] = [vlan.vlan_id for vlan in spec.vlans]
        self.bridge_manager.configure_bridge_vlans(spec.test_interface.bridge, vlan_ids)

    def _generate_configurations(self, spec: ContainerSpec) -> None:
        """Generate all configuration files"""
        rootfs_path: Path = self.fs_manager.get_rootfs_path(spec.name)

        for generator in self.config_generators:
            generator.generate(spec, rootfs_path)

    def _create_libvirt_domain(self, spec: ContainerSpec) -> None:
        """Create and define libvirt domain"""
        rootfs_path: Path = self.fs_manager.get_rootfs_path(spec.name)
        xml_file: Path = Path(f"/tmp/{spec.name}.xml")

        self.xml_generator.generate_xml(spec, rootfs_path, xml_file)
        self.domain_manager.undefine_domain(spec.name)  # Remove if exists
        self.domain_manager.define_domain(xml_file)

    def _print_usage_info(self, spec: ContainerSpec) -> None:
        """Print usage information"""
        print(f"\n{'='*50}")
        print(f"Container '{spec.name}' created successfully!")
        print(f"{'='*50}")

        print(f"\nNetwork Configuration:")
        mgmt = spec.management_interface
        print(
            f"  {mgmt.name}: {mgmt.ip_address}/{mgmt.netmask} -> {mgmt.bridge} (Management)"
        )

        if spec.vlans:
            for vlan in spec.vlans:
                test = spec.test_interface
                print(
                    f"  {test.name}.{vlan.vlan_id}: {vlan.ip_address}/{vlan.netmask} -> {test.bridge} (VLAN {vlan.vlan_id})"
                )
            
            print(f"\nBridge VLAN Configuration:")
            vlan_ids = [v.vlan_id for v in spec.vlans]
            print(
                f"  Bridge {spec.test_interface.bridge} configured with VLANs: {vlan_ids}"
            )
        else:
            test = spec.test_interface
            print(
                f"  {test.name}: {test.ip_address}/{test.netmask} -> {test.bridge} (Direct)"
            )
            print(f"\nBridge Configuration:")
            print(f"  Bridge {test.bridge} configured without VLANs")

        print(f"\nContainer Management:")
        print(f"  Start:   sudo virsh -c lxc:/// start {spec.name}")
        print(f"  Console: sudo virsh -c lxc:/// console {spec.name}")
        print(f"  Stop:    sudo virsh -c lxc:/// shutdown {spec.name}")
        print(f"  Status:  sudo virsh -c lxc:/// list")

        print(f"\nNetwork Testing (inside container):")
        print(f"  network-test show-config     - Show configuration")
        print(f"  network-test mgmt-ping <ip>  - Ping via management")

        if spec.vlans:
            for vlan in spec.vlans:
                print(
                    f"  network-test vlan{vlan.vlan_id}-ping <ip> - Ping via VLAN {vlan.vlan_id}"
                )
        else:
            print(f"  network-test test-ping <ip>  - Ping via test interface")

        print(f"  network-test zebra-cli       - Access FRR/Zebra CLI")
        print(f"  network-test show-vlans      - Show VLAN interfaces")
        print(f"\nConsole Disconnect: Ctrl + ] (don't use 'exit')")
