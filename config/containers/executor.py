#!/usr/bin/env python3
"""
Command execution implementation
"""

import subprocess
from typing import List, Optional


class SystemCommandExecutor:
    """System command executor implementation"""

    def run(
        self, command: List[str], check: bool = True, input_text: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """Execute system command with optional input"""
        kwargs = {"check": check, "capture_output": True, "text": True}

        if input_text:
            kwargs["input"] = input_text

        return subprocess.run(command, **kwargs)
