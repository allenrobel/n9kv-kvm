#!/usr/bin/env python3

"""
bridge_monitor.py - Monitor Linux Bridge Statistics
Compatible with Cockpit integration
Requires Python 3.8+
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

# Configuration
LOG_FILE = "/var/log/bridge-monitor.log"
STATUS_FILE = "/tmp/bridge-status.json"


# Set up logging with fallback for permissions
def setup_logging():
    handlers = [logging.StreamHandler(sys.stdout)]

    # Try to add file handler, but don't fail if we can't write to log file
    try:
        handlers.append(logging.FileHandler(LOG_FILE))
    except PermissionError:
        # If we can't write to the main log file, try a user-accessible location
        try:
            user_log = "/tmp/bridge-monitor.log"
            handlers.append(logging.FileHandler(user_log))
        except Exception:
            # If all else fails, just use stdout
            pass

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=handlers)
    return logging.getLogger(__name__)


logger = setup_logging()


class BridgeMonitor:
    """Monitor for Linux bridges and their statistics"""

    def __init__(self):
        self.logger = logger

    def run_command(self, cmd: List[str], timeout: int = 10) -> Tuple[bool, str, str]:
        """Run a shell command and return success, stdout, stderr"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)

    def get_bridge_list(self) -> List[str]:
        """Get list of all bridges on the system"""
        bridges = []

        # Method 1: Use 'bridge link' command
        success, stdout, stderr = self.run_command(["bridge", "link"])
        if success:
            for line in stdout.split("\n"):
                if "master" in line:
                    match = re.search(r"master\s+(\w+)", line)
                    if match:
                        bridge_name = match.group(1)
                        if bridge_name not in bridges:
                            bridges.append(bridge_name)

        # Method 2: Fallback to /sys/class/net
        if not bridges:
            success, stdout, stderr = self.run_command(["ls", "/sys/class/net"])
            if success:
                for interface in stdout.split():
                    bridge_path = f"/sys/class/net/{interface}/bridge"
                    if os.path.exists(bridge_path):
                        bridges.append(interface)

        return sorted(bridges)

    def get_bridge_statistics(self, bridge_name: str) -> Dict:
        """Get detailed statistics for a specific bridge"""
        stats = {
            "name": bridge_name,
            "status": "unknown",
            "rx_bytes": 0,
            "rx_packets": 0,
            "rx_errors": 0,
            "rx_dropped": 0,
            "tx_bytes": 0,
            "tx_packets": 0,
            "tx_errors": 0,
            "tx_dropped": 0,
            "interfaces": [],
            "stp_state": "unknown",
        }

        # Get basic interface statistics using ip -s link show
        success, stdout, stderr = self.run_command(["ip", "-s", "link", "show", bridge_name])
        if success:
            lines = stdout.split("\n")
            for i, line in enumerate(lines):
                if bridge_name in line and "state" in line:
                    # Extract state
                    if "state UP" in line:
                        stats["status"] = "up"
                    elif "state DOWN" in line:
                        stats["status"] = "down"

                # Parse RX statistics
                if "RX:" in line and i + 1 < len(lines):
                    rx_line = lines[i + 1].strip()
                    rx_parts = rx_line.split()
                    if len(rx_parts) >= 4:
                        try:
                            stats["rx_bytes"] = int(rx_parts[0])
                            stats["rx_packets"] = int(rx_parts[1])
                            stats["rx_errors"] = int(rx_parts[2])
                            stats["rx_dropped"] = int(rx_parts[3])
                        except (ValueError, IndexError):
                            pass

                # Parse TX statistics
                if "TX:" in line and i + 1 < len(lines):
                    tx_line = lines[i + 1].strip()
                    tx_parts = tx_line.split()
                    if len(tx_parts) >= 4:
                        try:
                            stats["tx_bytes"] = int(tx_parts[0])
                            stats["tx_packets"] = int(tx_parts[1])
                            stats["tx_errors"] = int(tx_parts[2])
                            stats["tx_dropped"] = int(tx_parts[3])
                        except (ValueError, IndexError):
                            pass

        # Get bridge interfaces
        stats["interfaces"] = self.get_bridge_interfaces(bridge_name)

        # Get STP state
        stats["stp_state"] = self.get_stp_state(bridge_name)

        return stats

    def get_bridge_interfaces(self, bridge_name: str) -> List[str]:
        """Get list of interfaces attached to a bridge"""
        interfaces = []

        # Try using bridge command
        success, stdout, stderr = self.run_command(["bridge", "link", "show", "master", bridge_name])
        if success:
            for line in stdout.split("\n"):
                match = re.search(r"^\d+:\s+(\w+):", line)
                if match:
                    interfaces.append(match.group(1))

        # Fallback to /sys/class/net
        if not interfaces:
            bridge_path = f"/sys/class/net/{bridge_name}/brif"
            if os.path.exists(bridge_path):
                try:
                    interfaces = os.listdir(bridge_path)
                except OSError:
                    pass

        return sorted(interfaces)

    def get_stp_state(self, bridge_name: str) -> str:
        """Get Spanning Tree Protocol state for a bridge"""
        stp_file = f"/sys/class/net/{bridge_name}/bridge/stp_state"
        try:
            with open(stp_file, "r") as f:
                state = f.read().strip()
                return "enabled" if state == "1" else "disabled"
        except (OSError, FileNotFoundError):
            return "unknown"

    def format_bytes(self, bytes_value: int) -> str:
        """Format bytes in human readable format"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"

    def scan_bridges(self) -> Dict:
        """Main function to scan all bridges and their statistics"""
        self.logger.info("Scanning bridge statistics...")

        bridges = self.get_bridge_list()
        bridge_stats = []

        for bridge_name in bridges:
            try:
                stats = self.get_bridge_statistics(bridge_name)
                bridge_stats.append(stats)
                msg = f"Collected stats for bridge: {bridge_name}"
                self.logger.info(msg)
            except Exception as e:
                msg = f"Failed to collect stats for bridge {bridge_name}: {e}"
                self.logger.error(msg)

        result = {"timestamp": datetime.now(timezone.utc).isoformat(), "bridge_count": len(bridge_stats), "bridges": bridge_stats}

        # Write status file
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            os.chmod(STATUS_FILE, 0o644)
        except Exception as e:
            msg = f"Failed to write status file: {e}"
            self.logger.error(msg)

        return result


def print_table(data: Dict):
    """Print bridge data in table format"""
    bridges = data.get("bridges", [])

    if not bridges:
        print("No bridges found")
        return

    print(f"{'BRIDGE NAME':<15} {'STATUS':<8} {'RX BYTES':<12} {'TX BYTES':<12} {'RX PKTS':<10} {'TX PKTS':<10} {'INTERFACES':<20}")
    print(f"{'----------':<15} {'------':<8} {'--------':<12} {'--------':<12} {'-------':<10} {'-------':<10} {'----------':<20}")

    monitor = BridgeMonitor()
    for bridge in bridges:
        rx_bytes_str = monitor.format_bytes(bridge["rx_bytes"])
        tx_bytes_str = monitor.format_bytes(bridge["tx_bytes"])
        interfaces_str = ",".join(bridge["interfaces"][:3])  # Show first 3 interfaces
        if len(bridge["interfaces"]) > 3:
            interfaces_str += "..."

        print(
            f"{bridge['name']:<15} {bridge['status']:<8} {rx_bytes_str:<12} {tx_bytes_str:<12} "
            f"{bridge['rx_packets']:<10} {bridge['tx_packets']:<10} {interfaces_str:<20}"
        )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Monitor Linux Bridge Statistics")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--table", action="store_true", help="Output table")
    parser.add_argument("--bridge", type=str, help="Monitor specific bridge only")

    args = parser.parse_args()

    # If outputting JSON, disable logging to stdout to avoid contaminating JSON
    if args.json:
        # Remove the stdout handler to prevent log messages in JSON output
        root_logger = logging.getLogger()
        root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, logging.StreamHandler)]

    monitor = BridgeMonitor()

    try:
        if args.bridge:
            # Monitor specific bridge
            stats = monitor.get_bridge_statistics(args.bridge)
            data = {"timestamp": datetime.now(timezone.utc).isoformat(), "bridge_count": 1, "bridges": [stats]}
        else:
            # Monitor all bridges
            data = monitor.scan_bridges()

        if args.json:
            print(json.dumps(data, indent=2))
        elif args.table:
            print_table(data)
        else:
            print(f"Found {data['bridge_count']} bridges")
            print(f"Status file: {STATUS_FILE}")

    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        if not args.json:  # Only show error if not JSON mode
            msg = f"Error collecting bridge statistics: {e}"
            logger.error(msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
