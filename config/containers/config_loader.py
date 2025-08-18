#!/usr/bin/env python3
"""
Configuration loader for container specifications from YAML files
"""

from pathlib import Path
from typing import Any, Dict

import yaml

from models import ContainerSpec, NetworkInterface, VLANConfig


class ConfigLoader:
    """Loads container configurations from YAML files"""

    def __init__(self, config_file: str):
        """
        Initialize with path to YAML configuration file

        Args:
            config_file: Path to the YAML configuration file
        """
        self.config_file = Path(config_file)
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

    def load_config(self) -> Dict[str, Any]:
        """Load and parse the YAML configuration file"""
        with open(self.config_file, "r") as f:
            return yaml.safe_load(f)

    def create_container_spec(self, container_name: str) -> ContainerSpec:
        """
        Create a ContainerSpec from YAML configuration

        Args:
            container_name: Name of the container to create spec for

        Returns:
            ContainerSpec object

        Raises:
            KeyError: If container name not found in configuration
        """
        config = self.load_config()

        if container_name not in config["containers"]:
            raise KeyError(f"Container '{container_name}' not found in configuration")

        container_config = config["containers"][container_name]

        # Create management interface
        mgmt_iface_config = container_config["management_interface"]
        management_interface = NetworkInterface(
            name=mgmt_iface_config["name"],
            ip_address=mgmt_iface_config["ip_address"],
            netmask=mgmt_iface_config["netmask"],
            bridge=mgmt_iface_config["bridge"],
            mac_address=mgmt_iface_config["mac_address"],
            description=mgmt_iface_config.get("description", ""),
        )

        # Create test interface
        test_iface_config = container_config["test_interface"]
        test_interface = NetworkInterface(
            name=test_iface_config["name"],
            ip_address=test_iface_config["ip_address"],
            netmask=test_iface_config["netmask"],
            bridge=test_iface_config["bridge"],
            mac_address=test_iface_config["mac_address"],
            description=test_iface_config.get("description", ""),
        )

        # Create VLANs
        vlans = []
        for vlan_config in container_config.get("vlans", []):
            vlan = VLANConfig(
                vlan_id=vlan_config["vlan_id"], ip_address=vlan_config["ip_address"], netmask=vlan_config["netmask"], description=vlan_config.get("description", "")
            )
            vlans.append(vlan)

        return ContainerSpec(
            name=container_config["name"],
            management_interface=management_interface,
            test_interface=test_interface,
            vlans=vlans,
            gateway_ip=container_config["gateway_ip"],
            memory_kb=container_config.get("memory_kb", 1048576),
            vcpus=container_config.get("vcpus", 2),
        )

    def get_available_containers(self) -> list[str]:
        """Get list of available container names from configuration"""
        config = self.load_config()
        return list(config["containers"].keys())
