#!/usr/bin/env python3
"""
Bridge and VLAN management
"""

import logging
import subprocess
from typing import List

from interfaces import CommandExecutor

logger = logging.getLogger(__name__)


class BridgeVLANManager:
    """Manages bridge VLAN configuration"""

    def __init__(self, executor: CommandExecutor) -> None:
        self.executor: CommandExecutor = executor

    def enable_vlan_filtering(self, bridge_name: str) -> None:
        """Enable VLAN filtering on bridge"""
        try:
            self.executor.run(
                [
                    "sudo",
                    "ip",
                    "link",
                    "set",
                    bridge_name,
                    "type",
                    "bridge",
                    "vlan_filtering",
                    "1",
                ]
            )
            logger.info(f"Enabled VLAN filtering on bridge: {bridge_name}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to enable VLAN filtering on {bridge_name}: {e}")

    def disable_vlan_filtering(self, bridge_name: str) -> None:
        """Disable VLAN filtering on bridge"""
        try:
            self.executor.run(
                [
                    "sudo",
                    "ip",
                    "link",
                    "set",
                    bridge_name,
                    "type",
                    "bridge",
                    "vlan_filtering",
                    "0",
                ]
            )
            logger.info(f"Disabled VLAN filtering on bridge: {bridge_name}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to disable VLAN filtering on {bridge_name}: {e}")

    def add_vlan_to_bridge(self, bridge_name: str, vlan_id: int) -> None:
        """Add VLAN to bridge"""
        try:
            self.executor.run(
                [
                    "sudo",
                    "bridge",
                    "vlan",
                    "add",
                    "vid",
                    str(vlan_id),
                    "dev",
                    bridge_name,
                    "self",
                ]
            )
            logger.info(f"Added VLAN {vlan_id} to bridge {bridge_name}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to add VLAN {vlan_id} to {bridge_name}: {e}")

    def configure_bridge_vlans(self, bridge_name: str, vlan_ids: List[int]) -> None:
        """Configure VLANs on bridge"""
        if not vlan_ids:
            logger.info(f"No VLANs configured for bridge {bridge_name}, disabling VLAN filtering")
            self.disable_vlan_filtering(bridge_name)
            return
            
        self.enable_vlan_filtering(bridge_name)

        for vlan_id in vlan_ids:
            self.add_vlan_to_bridge(bridge_name, vlan_id)
