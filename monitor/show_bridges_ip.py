#!/usr/bin/env python3

"""
Display bridge interfaces and their IP addresses.
"""
import argparse
import ipaddress
import json
import subprocess
import sys


def _extract_ipv4_address(addr_entry):
    """Extract IPv4 address from address entry."""
    if addr_entry.get("family") != "inet":
        return None
    return f"{addr_entry['local']}/{addr_entry['prefixlen']}"


def _extract_ipv6_address(addr_entry):
    """Extract IPv6 address from address entry, excluding link-local."""
    if addr_entry.get("family") != "inet6":
        return None

    ipv6_addr = addr_entry["local"]
    try:
        addr_obj = ipaddress.IPv6Address(ipv6_addr)
        if addr_obj.is_link_local:
            return None
        return f"{ipv6_addr}/{addr_entry['prefixlen']}"
    except ipaddress.AddressValueError:
        return None


def _get_bridge_addresses(bridge_name, include_ipv6):
    """Get all IP addresses for a specific bridge."""
    addr_result = subprocess.run(["ip", "-j", "addr", "show", "dev", bridge_name], capture_output=True, text=True, check=True)
    addr_info = json.loads(addr_result.stdout)

    if not addr_info:
        return []

    addresses = []
    for addr_entry in addr_info[0].get("addr_info", []):
        ip_addr = _extract_ipv4_address(addr_entry)
        if not ip_addr and include_ipv6:
            ip_addr = _extract_ipv6_address(addr_entry)

        if ip_addr:
            addresses.append((bridge_name, ip_addr))

    return addresses


def get_bridge_ip_info(include_ipv6=False):
    """
    Get bridge interfaces with their IP addresses using ip command with JSON output.
    Returns a list of tuples (bridge_name, ip_address).
    """
    try:
        bridges_result = subprocess.run(["ip", "-j", "link", "show", "type", "bridge"], capture_output=True, text=True, check=True)
        bridges = json.loads(bridges_result.stdout)

        bridges_with_ip = []
        for bridge in bridges:
            bridge_name = bridge["ifname"]
            addresses = _get_bridge_addresses(bridge_name, include_ipv6)
            bridges_with_ip.extend(addresses)

        return bridges_with_ip

    except subprocess.CalledProcessError as e:
        print(f"Error running ip command: {e}", file=sys.stderr)
        return []
    except FileNotFoundError:
        print("Error: 'ip' command not found. Make sure iproute2 is installed.", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output: {e}", file=sys.stderr)
        return []


def display_bridges(bridges_info, ip_version="IPv4"):
    """
    Display bridge information in aligned format.
    """
    if not bridges_info:
        print(f"No bridges with {ip_version} addresses found.")
        return

    # Find the maximum length of bridge names for alignment
    max_name_length = max(len(name) for name, _ in bridges_info)

    # Display with proper alignment
    for bridge_name, ip_addr in bridges_info:
        print(f"{bridge_name:<{max_name_length}} {ip_addr}")


def main():
    """
    Main function to get and display bridge IP information.
    """
    parser = argparse.ArgumentParser(
        description="Display bridge interfaces with their IP addresses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Show bridges with IPv4 addresses
  %(prog)s --ipv6            # Show bridges with IPv6 addresses (non-link-local)
        """,
    )

    parser.add_argument("--ipv6", action="store_true", help="Display IPv6 addresses instead of IPv4 (excludes link-local addresses)")

    args = parser.parse_args()

    if args.ipv6:
        print("Bridges with IPv6 addresses (non-link-local):")
        ip_version = "IPv6"
    else:
        print("Bridges with IPv4 addresses:")
        ip_version = "IPv4"

    print("-" * 50)

    bridges_info = get_bridge_ip_info(include_ipv6=args.ipv6)
    display_bridges(bridges_info, ip_version)


if __name__ == "__main__":
    main()
