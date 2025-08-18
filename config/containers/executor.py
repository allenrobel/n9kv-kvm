#!/usr/bin/env python3
"""
Command execution implementation
"""

import subprocess
from typing import List, Optional


class SystemCommandExecutor:
    """System command executor implementation"""

    def run(self, command: List[str], check: bool = True, input_text: Optional[str] = None, stream_output: bool = False) -> subprocess.CompletedProcess:
        """Execute system command with optional input

        Args:
            command: Command and arguments to execute
            check: Whether to raise exception on non-zero exit
            input_text: Optional input to send to the command
            stream_output: Whether to stream output in real-time
        """
        # Long-running commands that should stream output
        long_running_commands = ["debootstrap", "apt-get", "apt", "wget", "curl"]

        # Auto-enable streaming for known long-running commands
        if not stream_output and any(cmd in command for cmd in long_running_commands):
            stream_output = True

        if stream_output:
            # Stream output in real-time for long-running commands
            if input_text:
                # For commands that need input, use Popen with stdin
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True  # Line buffered
                )

                # Send input and close stdin
                if input_text:
                    process.stdin.write(input_text)
                    process.stdin.close()

                output_lines = []
                for line in process.stdout:
                    print(line.rstrip())  # Show real-time output
                    output_lines.append(line)

                process.wait()

            else:
                # No input needed, simpler streaming
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)  # Line buffered

                output_lines = []
                for line in process.stdout:
                    print(line.rstrip())  # Show real-time output
                    output_lines.append(line)

                process.wait()

            # Check exit code if requested
            if check and process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command, "".join(output_lines))

            # Return compatible result
            result = subprocess.CompletedProcess(command, process.returncode, "".join(output_lines), "")
            return result

        else:
            # Normal captured execution for short commands
            kwargs = {"check": check, "capture_output": True, "text": True}

            if input_text:
                kwargs["input"] = input_text

            return subprocess.run(command, **kwargs)
