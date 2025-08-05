#!/usr/bin/env python3
"""
Interfaces and protocols for container management system
"""

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Protocol

from models import ContainerSpec


class CommandExecutor(Protocol):
    """Protocol for command execution"""

    def run(
        self, command: List[str], check: bool = True, input_text: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """Execute a command"""
        ...


class ConfigurationGenerator(ABC):
    """Abstract base for configuration generators"""

    @abstractmethod
    def generate(self, spec: ContainerSpec, output_path: Path) -> None:
        """Generate configuration file"""
        pass
