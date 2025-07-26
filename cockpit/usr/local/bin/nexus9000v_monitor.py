#!/usr/bin/env python3

"""
nexus9000v_monitor.py - Monitor Nexus 9000v QEMU VMs
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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configuration
QEMU_BINARY = "qemu-system-x86_64"
LOG_FILE = "/var/log/nexus9000v-monitor.log"
STATUS_FILE = "/tmp/nexus9000v-status.json"

# Set up logging with fallback for permissions
def setup_logging():
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Try to add file handler, but don't fail if we can't write to log file
    try:
        handlers.append(logging.FileHandler(LOG_FILE))
    except PermissionError:
        # If we can't write to the main log file, try a user-accessible location
        try:
            user_log = "/tmp/nexus9000v-monitor.log"
            handlers.append(logging.FileHandler(user_log))
        except:
            # If all else fails, just use stdout
            pass
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    return logging.getLogger(__name__)

logger = setup_logging()


class NexusVMMonitor:
    """Monitor for Nexus 9000v VMs running under QEMU"""
    
    def __init__(self):
        self.logger = logger
        
    def run_command(self, cmd: List[str], timeout: int = 10) -> Tuple[bool, str, str]:
        """Run a shell command and return success, stdout, stderr"""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)
    
    def get_qemu_processes(self) -> List[Dict]:
        """Get all QEMU processes with their info"""
        processes = []
        
        success, stdout, stderr = self.run_command(["ps", "-eo", "pid,cmd"])
        if not success:
            self.logger.error(f"Failed to get process list: {stderr}")
            return processes
        
        for line in stdout.split('\n')[1:]:  # Skip header
            line = line.strip()
            if not line or QEMU_BINARY not in line:
                continue
                
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
                
            try:
                pid = int(parts[0])
                cmdline = parts[1]
                processes.append({"pid": pid, "cmdline": cmdline})
            except ValueError:
                continue
                
        return processes
    
    def is_nexus9000v(self, cmdline: str) -> bool:
        """Detect if a QEMU process is running a Nexus 9000v VM"""
        # Look for Nexus indicators
        if re.search(r'nexus|n9k|n9000|nxos', cmdline, re.IGNORECASE):
            return True
        
        # Check for typical Nexus parameters
        typical_params = [r'-cpu.*Nehalem', r'-smp.*1', r'-m.*[34]096']
        matches = sum(1 for param in typical_params if re.search(param, cmdline))
        
        if matches >= 2 and re.search(r'-serial.*pty|-monitor.*stdio', cmdline):
            return True
                
        return False
    
    def extract_vm_name(self, cmdline: str) -> str:
        """Extract VM name from QEMU command line"""
        # Try -name parameter
        name_match = re.search(r'-name\s+([^\s]+)', cmdline)
        if name_match:
            return name_match.group(1)
        
        # Try disk image filename
        disk_match = re.search(r'([^\s/]+\.(?:qcow2|img))', cmdline)
        if disk_match:
            return Path(disk_match.group(1)).stem
        
        return "nexus-unknown"
    
    def get_process_stats(self, pid: int) -> Dict:
        """Get CPU, memory, and uptime for a process"""
        stats = {"cpu_percent": 0.0, "memory_mb": 0, "uptime": "0m"}
        
        # Get CPU and memory
        success, stdout, _ = self.run_command(["ps", "-p", str(pid), "-o", "%cpu,rss", "--no-headers"])
        if success and stdout:
            try:
                cpu_str, rss_str = stdout.split()
                stats["cpu_percent"] = float(cpu_str)
                stats["memory_mb"] = int(rss_str) // 1024  # KB to MB
            except (ValueError, IndexError):
                pass
        
        # Get uptime
        success, stdout, _ = self.run_command(["ps", "-p", str(pid), "-o", "lstart", "--no-headers"])
        if success and stdout:
            try:
                start_time = datetime.strptime(stdout.strip(), "%a %b %d %H:%M:%S %Y")
                uptime_delta = datetime.now() - start_time
                total_seconds = int(uptime_delta.total_seconds())
                
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                minutes = (total_seconds % 3600) // 60
                
                if days > 0:
                    stats["uptime"] = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    stats["uptime"] = f"{hours}h {minutes}m"
                else:
                    stats["uptime"] = f"{minutes}m"
            except Exception:
                pass
        
        return stats
    
    def get_network_info(self, pid: int) -> str:
        """Get network interface info for a process"""
        success, stdout, _ = self.run_command(["lsof", "-p", str(pid)])
        if success:
            tap_devices = re.findall(r'tap\d+', stdout)
            if tap_devices:
                return ','.join(sorted(set(tap_devices)))
        return "default"
    
    def scan_nexus_vms(self) -> Dict:
        """Main function to scan for Nexus 9000v VMs"""
        self.logger.info("Scanning for Nexus 9000v VMs...")
        
        qemu_processes = self.get_qemu_processes()
        nexus_vms = []
        
        for process in qemu_processes:
            if self.is_nexus9000v(process["cmdline"]):
                try:
                    pid = process["pid"]
                    vm_name = self.extract_vm_name(process["cmdline"])
                    stats = self.get_process_stats(pid)
                    network = self.get_network_info(pid)
                    
                    vm_info = {
                        "name": vm_name,
                        "pid": pid,
                        "status": "running",
                        "cpu_percent": stats["cpu_percent"],
                        "memory_mb": stats["memory_mb"],
                        "uptime": stats["uptime"],
                        "network_interfaces": network,
                        "type": "nexus9000v",
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                    
                    nexus_vms.append(vm_info)
                    self.logger.info(f"Found VM: {vm_name} (PID: {pid})")
                    
                except Exception as e:
                    self.logger.error(f"Error processing PID {process['pid']}: {e}")
        
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vm_count": len(nexus_vms),
            "vms": nexus_vms
        }
        
        # Write status file
        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump(result, f, indent=2)
            os.chmod(STATUS_FILE, 0o644)
        except Exception as e:
            self.logger.error(f"Failed to write status file: {e}")
        
        return result


def print_table(data: Dict):
    """Print VM data in table format"""
    vms = data.get('vms', [])
    
    if not vms:
        print("No Nexus 9000v VMs found")
        return
    
    print(f"{'VM NAME':<20} {'PID':<8} {'CPU%':<8} {'MEM(MB)':<10} {'UPTIME':<15} {'STATUS':<10}")
    print(f"{'--------':<20} {'---':<8} {'----':<8} {'-------':<10} {'-------':<15} {'------':<10}")
    
    for vm in vms:
        print(f"{vm['name']:<20} {vm['pid']:<8} {vm['cpu_percent']:<8.1f} "
              f"{vm['memory_mb']:<10} {vm['uptime']:<15} {vm['status']:<10}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Monitor Nexus 9000v VMs")
    parser.add_argument('--json', action='store_true', help='Output JSON')
    parser.add_argument('--table', action='store_true', help='Output table')
    
    args = parser.parse_args()
    
    # If outputting JSON, disable logging to stdout to avoid contaminating JSON
    if args.json:
        # Remove the stdout handler to prevent log messages in JSON output
        root_logger = logging.getLogger()
        root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, logging.StreamHandler)]
    
    monitor = NexusVMMonitor()
    
    try:
        data = monitor.scan_nexus_vms()
        
        if args.json:
            print(json.dumps(data, indent=2))
        elif args.table:
            print_table(data)
        else:
            print(f"Found {data['vm_count']} Nexus 9000v VMs")
            print(f"Status file: {STATUS_FILE}")
            
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        if not args.json:  # Only show error if not JSON mode
            logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

