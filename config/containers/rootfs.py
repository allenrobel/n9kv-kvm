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
    ) -> None:
        """Create Ubuntu rootfs with retry logic"""
        rootfs_path: Path = self.fs_manager.get_rootfs_path(container_name)

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    f"Creating Ubuntu rootfs (attempt {attempt}/{max_attempts})"
                )

                self.executor.run(
                    [
                        "sudo",
                        "debootstrap",
                        "--arch=amd64",
                        "--verbose",
                        "--option=Acquire::ForceIPv4=true",
                        "jammy",
                        str(rootfs_path),
                        mirror,
                    ]
                )

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
