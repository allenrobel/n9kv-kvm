#!/usr/bin/env python3
"""
Package installation for containers
"""

import subprocess
import logging
from pathlib import Path
from typing import List

from interfaces import CommandExecutor
from filesystem import FileSystemManager

logger = logging.getLogger(__name__)

class PackageInstaller:
    """Handles package installation in containers"""
    
    CORE_PACKAGES: List[str] = [
        'iputils-ping', 'iputils-tracepath', 'mtr-tiny', 'netcat-openbsd',
        'tcpdump', 'curl', 'wget', 'bind9-dnsutils', 'net-tools', 'iproute2',
        'iptables', 'bridge-utils', 'ethtool', 'socat', 'openssh-server',
        'vim', 'nano', 'htop', 'frr', 'python3', 'locales', 'vlan'
    ]
    
    OPTIONAL_PACKAGES: List[str] = ['nmap', 'iperf3', 'hping3']
    
    def __init__(self, executor: CommandExecutor, fs_manager: FileSystemManager) -> None:
        self.executor: CommandExecutor = executor
        self.fs_manager: FileSystemManager = fs_manager
    
    def install_packages(self, container_name: str) -> None:
        """Install packages in container"""
        rootfs_path: Path = self.fs_manager.get_rootfs_path(container_name)
        install_script: str = self._generate_install_script()
        
        try:
            logger.info(f"Installing packages in container: {container_name}")
            self.executor.run([
                'sudo', 'chroot', str(rootfs_path),
                '/bin/bash', '-c', install_script
            ])
            logger.info("Package installation completed successfully")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to install packages: {e}")
    
    def _generate_install_script(self) -> str:
        """Generate package installation script"""
        core_packages_str: str = ' \\\n    '.join(self.CORE_PACKAGES)
        optional_installs: str = '\n'.join([
            f"apt install -y {pkg} || echo \"{pkg} not available, skipping\""
            for pkg in self.OPTIONAL_PACKAGES
        ])
        
        return f"""
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C
export LANG=C

# Update and add universe repository
apt update
apt install -y software-properties-common
add-apt-repository universe -y
apt update

# Install core packages
apt install -y \\
    {core_packages_str}

# Generate locales
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8

# Install optional packages
{optional_installs}

# Configure FRR
if systemctl list-unit-files | grep -q frr.service; then
    systemctl enable frr
fi

# Clean up
apt clean
rm -rf /var/lib/apt/lists/*
"""