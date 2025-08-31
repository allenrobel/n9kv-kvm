#!/usr/bin/env python3

"""
Display bridge interfaces and their IPv4 addresses.
"""
import subprocess
import json
import sys


def get_bridge_ipv4_info():
    """
    Get bridge interfaces with their IPv4 addresses using ip command with JSON output.
    Returns a list of tuples (bridge_name, ipv4_address).
    """
    bridges_with_ipv4 = []

    try:
        # Get all bridge interfaces as JSON
        bridges_result = subprocess.run(
            ['ip', '-j', 'link', 'show', 'type', 'bridge'],
            capture_output=True, text=True, check=True
        )
        bridges = json.loads(bridges_result.stdout)

        # For each bridge, get its IP address information
        for bridge in bridges:
            bridge_name = bridge['ifname']

            # Get IP addresses for this specific bridge
            addr_result = subprocess.run(
                ['ip', '-j', 'addr', 'show', 'dev', bridge_name],
                capture_output=True, text=True, check=True
            )
            addr_info = json.loads(addr_result.stdout)

            # Extract IPv4 addresses
            if addr_info:
                for addr_entry in addr_info[0].get('addr_info', []):
                    if addr_entry.get('family') == 'inet':
                        ipv4_addr = f"{addr_entry['local']}/{addr_entry['prefixlen']}"
                        bridges_with_ipv4.append((bridge_name, ipv4_addr))
                        break  # Only take the first IPv4 address per bridge

    except subprocess.CalledProcessError as e:
        print(f"Error running ip command: {e}", file=sys.stderr)
        return []
    except FileNotFoundError:
        print("Error: 'ip' command not found. Make sure iproute2 is installed.", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output: {e}", file=sys.stderr)
        return []

    return bridges_with_ipv4


def display_bridges(bridges_info):
    """
    Display bridge information in aligned format.
    """
    if not bridges_info:
        print("No bridges with IPv4 addresses found.")
        return

    # Find the maximum length of bridge names for alignment
    max_name_length = max(len(name) for name, _ in bridges_info)

    # Display with proper alignment
    for bridge_name, ipv4_addr in bridges_info:
        print(f"{bridge_name:<{max_name_length}} {ipv4_addr}")


def main():
    """
    Main function to get and display bridge IPv4 information.
    """
    print("Bridges with IPv4 addresses:")
    print("-" * 40)

    bridges_info = get_bridge_ipv4_info()
    display_bridges(bridges_info)


if __name__ == "__main__":
    main()
