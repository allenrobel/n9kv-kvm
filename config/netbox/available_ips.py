#!/usr/bin/env python3
"""Query NetBox on glide for available IP addresses.

NetBox is the lab's IP address manager (populated from this repo's YAML by
populate_netbox.py). Use this before assigning a mgmt/test IP to a new device
so the address is known-free instead of eyeballed from the YAML files.

Usage:
    source ~/.config/netbox/netbox.env   # NETBOX_URL + NETBOX_TOKEN
    uv run config/netbox/available_ips.py                      # list prefixes + utilization
    uv run config/netbox/available_ips.py 192.168.12.0/24      # first 10 free IPs in prefix
    uv run config/netbox/available_ips.py 192.168.12.0/24 -n 5 # first 5
"""

from __future__ import annotations

import argparse
import os
import sys

import pynetbox


def main() -> int:
    parser = argparse.ArgumentParser(description="List available IPs in a NetBox prefix")
    parser.add_argument("prefix", nargs="?", help="Prefix to query, e.g. 192.168.12.0/24. Omit to list all prefixes.")
    parser.add_argument("-n", "--count", type=int, default=10, help="Number of available IPs to show (default: 10; 0 = all)")
    args = parser.parse_args()

    url = os.environ.get("NETBOX_URL")
    token = os.environ.get("NETBOX_TOKEN")
    if not url or not token:
        print("error: NETBOX_URL / NETBOX_TOKEN not set (source ~/.config/netbox/netbox.env)")
        return 1
    nb = pynetbox.api(url, token=token)

    if args.prefix is None:
        for p in nb.ipam.prefixes.all():
            free = len(p.available_ips.list(limit=0))
            print(f"{p.prefix:<20} {free:>4} free  {p.description}")
        return 0

    prefix = nb.ipam.prefixes.get(prefix=args.prefix)
    if prefix is None:
        print(f"error: prefix {args.prefix} not found in NetBox")
        return 1
    available = prefix.available_ips.list(limit=0)
    for ip in available[: args.count or None]:
        print(ip.address)
    print(f"({len(available)} available in {args.prefix} -- {prefix.description})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
