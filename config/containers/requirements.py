#!/usr/bin/env python3
"""
Requirements checker for container management system
"""

import logging
import sys
from typing import List

from interfaces import CommandExecutor

logger = logging.getLogger(__name__)


class RequirementsChecker:
    """Checks system requirements for container creation"""

    REQUIRED_TOOLS: List[str] = ["debootstrap", "virsh", "chroot", "bridge"]
    REQUIRED_PYTHON_MODULES: List[str] = ["jinja2"]

    def __init__(self, executor: CommandExecutor) -> None:
        self.executor: CommandExecutor = executor

    def check_all_requirements(self) -> bool:
        """Check all system requirements"""
        checks: List[bool] = [
            self._check_python_version(),
            self._check_system_tools(),
            self._check_python_modules(),
            self._check_libvirt_lxc(),
        ]

        return all(checks)

    def _check_python_version(self) -> bool:
        """Check Python version"""
        if sys.version_info < (3, 10):
            logger.error(f"Python 3.10+ required, current: {sys.version}")
            return False

        logger.info(f"✓ Python version: {sys.version}")
        return True

    def _check_system_tools(self) -> bool:
        """Check required system tools"""
        import shutil

        missing_tools: List[str] = []
        for tool in self.REQUIRED_TOOLS:
            if not shutil.which(tool):
                missing_tools.append(tool)
            else:
                logger.info(f"✓ {tool} available")

        if missing_tools:
            logger.error(f"Missing tools: {', '.join(missing_tools)}")
            logger.info(
                "Install with: sudo apt install debootstrap libvirt-daemon-driver-lxc bridge-utils"
            )
            return False

        return True

    def _check_python_modules(self) -> bool:
        """Check required Python modules"""
        missing_modules: List[str] = []

        for module in self.REQUIRED_PYTHON_MODULES:
            try:
                __import__(module)
                if module == "jinja2":
                    import jinja2

                    logger.info(f"✓ Jinja2 version: {jinja2.__version__}")
            except ImportError:
                missing_modules.append(module)

        if missing_modules:
            logger.error(f"Missing Python modules: {', '.join(missing_modules)}")
            logger.info("Install with: pip install -r requirements.txt")
            return False

        return True

    def _check_libvirt_lxc(self) -> bool:
        """Check libvirt LXC support"""
        try:
            self.executor.run(["sudo", "virsh", "-c", "lxc:///", "list"])
            logger.info("✓ libvirt LXC driver working")
            return True
        except Exception:
            logger.error("✗ libvirt LXC driver not working")
            logger.info("Install with: sudo apt install libvirt-daemon-driver-lxc")
            return False
