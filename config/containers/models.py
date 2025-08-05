#!/usr/bin/env python3
"""
Data models for container management system
"""

from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class VLANConfig:
    """Immutable VLAN configuration"""
    vlan_id: int
    ip_address: str
    netmask: str
    description: str = ""

    def __post_init__(self) -> None:
        if not (1 <= self.vlan_id <= 4094):
            raise ValueError(f"Invalid VLAN ID: {self.vlan_id}")

@dataclass(frozen=True)
class NetworkInterface:
    """Network interface configuration"""
    name: str
    ip_address: str
    netmask: str
    bridge: str
    mac_address: str
    description: str = ""

@dataclass(frozen=True)
class ContainerSpec:
    """Complete container specification"""
    name: str
    management_interface: NetworkInterface
    test_interface: NetworkInterface
    vlans: List[VLANConfig]
    gateway_ip: str
    memory_kb: int = 1048576
    vcpus: int = 2

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Container name cannot be empty")
        if not self.vlans:
            raise ValueError("At least one VLAN must be configured")
