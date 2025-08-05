#!/usr/bin/env python3
"""
File system operations for containers
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FileSystemManager:
    """Handles file system operations for containers"""

    def __init__(self, base_path: Path = Path("/var/lib/lxc")) -> None:
        self.base_path: Path = base_path

    def get_container_path(self, container_name: str) -> Path:
        """Get container base directory path"""
        return self.base_path / container_name

    def get_rootfs_path(self, container_name: str) -> Path:
        """Get container rootfs path"""
        return self.get_container_path(container_name) / "rootfs"

    def create_container_directories(self, container_name: str) -> None:
        """Create container directory structure"""
        container_path: Path = self.get_container_path(container_name)
        rootfs_path: Path = self.get_rootfs_path(container_name)

        container_path.mkdir(parents=True, exist_ok=True)
        rootfs_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created directories for container: {container_name}")
