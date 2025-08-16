#!/usr/bin/env python3
"""
Container rootfs creation
"""

import logging
import subprocess
from pathlib import Path

from filesystem import FileSystemManager
from interfaces import CommandExecutor

logger = logging.getLogger(__name__)


class RootfsBuilder:
    """Builds container root filesystem"""

    def __init__(
        self, executor: CommandExecutor, fs_manager: FileSystemManager
    ) -> None:
        self.executor: CommandExecutor = executor
        self.fs_manager: FileSystemManager = fs_manager

    def create_ubuntu_rootfs(
        self,
        container_name: str,
        mirror: str = "http://us.archive.ubuntu.com/ubuntu/",
        max_attempts: int = 3,
        force_ipv4: bool = True,
    ) -> None:
        """Create Ubuntu rootfs with retry logic"""
        rootfs_path: Path = self.fs_manager.get_rootfs_path(container_name)

        for attempt in range(1, max_attempts + 1):
            try:
                ip_mode = "IPv4" if force_ipv4 else "IPv4/IPv6"
                logger.info(
                    f"Creating Ubuntu rootfs (attempt {attempt}/{max_attempts}) using {ip_mode}"
                )

                # Build debootstrap command
                cmd = [
                    "sudo",
                    "debootstrap",
                    "--arch=amd64",
                    "--verbose",
                    "jammy",
                    str(rootfs_path),
                    mirror,
                ]
                
                # Set environment to force IPv4 if requested
                import os
                env = os.environ.copy() if force_ipv4 else None
                if force_ipv4:
                    env['WGET_OPTIONS'] = '--inet4-only'
                    # Also try setting APT options for newer systems
                    env['APT_CONFIG'] = '/dev/stdin'
                    # Use sudo -E to preserve environment
                    cmd[0:1] = ["sudo", "-E"]
                
                if force_ipv4:
                    # For IPv4-only, pass APT config via stdin
                    apt_config = "Acquire::ForceIPv4 \"true\";\n"
                    self.executor.run(cmd, input_text=apt_config)
                else:
                    self.executor.run(cmd)

                logger.info(f"Successfully created rootfs on attempt {attempt}")
                return

            except subprocess.CalledProcessError as e:
                if attempt < max_attempts:
                    logger.warning(f"Attempt {attempt} failed, retrying...")
                    self._cleanup_failed_rootfs(rootfs_path)
                else:
                    raise RuntimeError(
                        f"Failed to create rootfs after {max_attempts} attempts: {e}"
                    )

    def _cleanup_failed_rootfs(self, rootfs_path: Path) -> None:
        """Clean up failed rootfs creation"""
        try:
            self.executor.run(["sudo", "rm", "-rf", str(rootfs_path)], check=False)
            rootfs_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to cleanup rootfs: {e}")
