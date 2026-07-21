#!/usr/bin/env python3
"""Populate NetBox on glide with the n9kv-kvm lab topology.

Parses this repo's authoritative YAML (switches, WAN1, host containers) plus two
static entries (ND node, glide) and upserts sites, roles, device types, devices,
interfaces, cables, prefixes, and IP addresses into NetBox. Idempotent: safe to
re-run after topology changes; never deletes.

Design spec: docs/superpowers/specs/2026-07-21-netbox-population-design.md

Usage:
    source ~/.config/netbox/netbox.env   # NETBOX_URL + NETBOX_TOKEN
    uv run config/netbox/populate_netbox.py
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

import pynetbox
import yaml

REPO = Path(__file__).resolve().parents[2]
SWITCH_DIR = REPO / "config" / "nexus9000v"
WAN1_YAML = REPO / "config" / "8000v" / "WAN1.yaml"
CONTAINERS_YAML = REPO / "config" / "containers" / "container_configs_access_mode.yaml"

# Multi-access segments: devices share these bridges, so they never become cables.
SHARED_BRIDGE_PREFIXES = ("BR_ND_DATA_",)
SHARED_BRIDGES = {"outside"}

SITE_GROUP_LAB = "n9kv-lab"
SITE_SHARED = "Lab-Shared"

ROLE_BY_YAML = {
    "Border Gateway": "border-gateway",
    "Spine Switch": "spine",
    "Leaf Switch": "leaf",
    "Top-of-Rack Switch": "tor",
    "WAN Router": "wan-router",
}

IFACE_TYPE = "1000base-t"  # e1000 emulation on the n9kv VMs

counts = {"created": 0, "updated": 0, "unchanged": 0}
warnings: list[str] = []


def ensure(endpoint, lookup: dict, desired: dict):
    """Get-or-create `lookup` on `endpoint`, then update any `desired` fields that differ."""
    record = endpoint.get(**lookup)
    if record is None:
        record = endpoint.create(**lookup, **desired)
        counts["created"] += 1
        return record
    changes = {}
    for key, want in desired.items():
        have = getattr(record, key, None)
        if have is not None and not isinstance(have, (str, int, bool, float)):
            # FK fields compare by id; choice fields ({value, label}) by value.
            have = getattr(have, "id", None) if hasattr(have, "id") else getattr(have, "value", have)
        if have != want:
            changes[key] = want
    if changes:
        record.update(changes)
        counts["updated"] += 1
    else:
        counts["unchanged"] += 1
    return record


def site_for(device_name: str) -> str:
    prefix = device_name.split("_", 1)[0]
    if prefix in {"S1", "S2", "S3", "S4"}:
        return f"SITE{prefix[1]}"
    return SITE_SHARED


def load_switches() -> list[dict]:
    switches = []
    for path in sorted(SWITCH_DIR.glob("S*_*.yaml")):
        if path.name.endswith(".netplan.yaml"):
            continue
        switches.append(yaml.safe_load(path.read_text()))
    return switches


def main() -> int:
    url = os.environ.get("NETBOX_URL")
    token = os.environ.get("NETBOX_TOKEN")
    if not url or not token:
        print("error: NETBOX_URL / NETBOX_TOKEN not set (source ~/.config/netbox/netbox.env)")
        return 1
    nb = pynetbox.api(url, token=token)

    # -- organizational objects -------------------------------------------------
    lab_group = ensure(nb.dcim.site_groups, {"slug": SITE_GROUP_LAB}, {"name": SITE_GROUP_LAB})
    for name in ("SITE1", "SITE2", "SITE3", "SITE4", SITE_SHARED):
        ensure(nb.dcim.sites, {"slug": name.lower()}, {"name": name, "group": lab_group.id})
    sites = {s.name: s for s in nb.dcim.sites.all()}

    for slug in set(ROLE_BY_YAML.values()) | {"host", "nd-node", "hypervisor"}:
        ensure(nb.dcim.device_roles, {"slug": slug}, {"name": slug})
    roles = {r.slug: r for r in nb.dcim.device_roles.all()}

    cisco = ensure(nb.dcim.manufacturers, {"slug": "cisco"}, {"name": "Cisco"})
    canonical = ensure(nb.dcim.manufacturers, {"slug": "canonical"}, {"name": "Canonical"})
    types = {}
    for slug, model, mfr in [
        ("nexus9300v", "Nexus9300v", cisco),
        ("nd-node", "Nexus Dashboard node", cisco),
        ("catalyst-8000v", "Catalyst 8000V", cisco),
        ("lxc-container", "LXC container", canonical),
        ("ubuntu-kvm-host", "Ubuntu KVM host", canonical),
    ]:
        types[slug] = ensure(nb.dcim.device_types, {"slug": slug}, {"model": model, "manufacturer": mfr.id, "u_height": 0})

    # -- collect desired devices/interfaces/IPs from repo YAML ------------------
    # devices: name -> (type_slug, role_slug, site_name, description)
    # ifaces:  (device, ifname) -> {bridge, mgmt_only, ip, mac}
    devices: dict[str, tuple[str, str, str, str]] = {}
    ifaces: dict[tuple[str, str], dict] = {}

    for sw in load_switches():
        name = sw["name"]
        devices[name] = ("nexus9300v", ROLE_BY_YAML[sw["role"]], site_for(name), sw["role"])
        ifaces[(name, "mgmt0")] = {"bridge": sw["mgmt_bridge"], "mgmt_only": True, "ip": sw["mgmt_ip"]}
        for i, bridge in enumerate(sw["isl_bridges"], 1):
            ifaces[(name, f"Ethernet1/{i}")] = {"bridge": bridge, "mgmt_only": False, "ip": None}

    wan = yaml.safe_load(WAN1_YAML.read_text())
    devices[wan["name"]] = ("catalyst-8000v", ROLE_BY_YAML[wan["role"]], SITE_SHARED, wan["role"])
    ifaces[(wan["name"], "GigabitEthernet1")] = {"bridge": wan["mgmt_bridge"], "mgmt_only": True, "ip": wan["mgmt_ip"]}
    for i, bridge in enumerate(wan["isl_bridges"], 2):
        ifaces[(wan["name"], f"GigabitEthernet{i}")] = {"bridge": bridge, "mgmt_only": False, "ip": None}

    for cname, c in yaml.safe_load(CONTAINERS_YAML.read_text())["containers"].items():
        devices[cname] = ("lxc-container", "host", site_for(cname), "LXC test host container")
        for key in ("management_interface", "test_interface"):
            spec = c[key]
            ifaces[(cname, spec["name"])] = {
                "bridge": spec["bridge"],
                "mgmt_only": key == "management_interface",
                "ip": f"{spec['ip_address']}/{spec['netmask']}",
                "mac": spec["mac_address"],
            }

    # Static entries: ND node (IPs live in the ND install wizard, not the repo) and glide.
    devices["nd1"] = ("nd-node", "nd-node", SITE_SHARED, "Nexus Dashboard (single-node cluster)")
    ifaces[("nd1", "mgmt")] = {"bridge": "outside", "mgmt_only": True, "ip": "192.168.7.7/24"}
    ifaces[("nd1", "data")] = {"bridge": "BR_ND_DATA_12", "mgmt_only": False, "ip": None}
    devices["glide"] = ("ubuntu-kvm-host", "hypervisor", SITE_SHARED, "KVM/OVS host running the whole lab (n9kv-kvm repo)")

    # -- prefixes ---------------------------------------------------------------
    for prefix, desc in [
        ("192.168.12.0/24", "S1/S2 + shared lab mgmt (BR_ND_DATA_12)"),
        ("192.168.14.0/24", "S3/S4 mgmt (BR_ND_DATA_14)"),
        ("192.0.1.0/24", "Container test network"),
    ]:
        ensure(nb.ipam.prefixes, {"prefix": prefix}, {"description": desc})

    # -- devices, interfaces, IPs -----------------------------------------------
    nb_devices = {}
    for name, (type_slug, role_slug, site_name, desc) in devices.items():
        nb_devices[name] = ensure(
            nb.dcim.devices,
            {"name": name},
            {
                "device_type": types[type_slug].id,
                "role": roles[role_slug].id,
                "site": sites[site_name].id,
                "description": desc,
            },
        )

    nb_ifaces = {}
    for (dev, ifname), spec in ifaces.items():
        desired = {
            "device": nb_devices[dev].id,  # create payload needs `device`; lookup filters use `device_id`
            "type": IFACE_TYPE,
            "mgmt_only": spec["mgmt_only"],
            "description": spec["bridge"],
        }
        iface = ensure(nb.dcim.interfaces, {"device_id": nb_devices[dev].id, "name": ifname}, desired)
        nb_ifaces[(dev, ifname)] = iface
        if spec.get("mac"):
            # NetBox >= 4.2 models MACs as standalone objects; writing interface.mac_address is a no-op.
            mac = ensure(
                nb.dcim.mac_addresses,
                {"mac_address": spec["mac"].upper()},
                {"assigned_object_type": "dcim.interface", "assigned_object_id": iface.id},
            )
            ensure(nb.dcim.interfaces, {"device_id": nb_devices[dev].id, "name": ifname}, {"primary_mac_address": mac.id})

    for (dev, ifname), spec in ifaces.items():
        if not spec["ip"]:
            continue
        iface = nb_ifaces[(dev, ifname)]
        try:
            ip = nb.ipam.ip_addresses.get(address=spec["ip"])
            if ip is None:
                ip = nb.ipam.ip_addresses.create(address=spec["ip"], assigned_object_type="dcim.interface", assigned_object_id=iface.id)
                counts["created"] += 1
            elif ip.assigned_object_id is None:
                ip.update({"assigned_object_type": "dcim.interface", "assigned_object_id": iface.id})
                counts["updated"] += 1
            elif ip.assigned_object_id != iface.id:
                # Never steal an IP from its current owner -- surface the conflict instead.
                owner = ip.assigned_object
                owner_desc = f"{owner.device.name}/{owner.name}" if owner else f"object id {ip.assigned_object_id}"
                warnings.append(f"IP conflict: {spec['ip']} wanted on {dev}/{ifname} but assigned to {owner_desc}")
                continue
            else:
                counts["unchanged"] += 1
        except (pynetbox.RequestError, ValueError) as err:
            warnings.append(f"IP {spec['ip']} on {dev}/{ifname}: {err}")
            continue
        if spec["mgmt_only"]:
            ensure(nb.dcim.devices, {"name": dev}, {"primary_ip4": ip.id})

    # -- cables: any non-shared bridge with exactly two endpoints ---------------
    endpoints: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for (dev, ifname), spec in ifaces.items():
        bridge = spec["bridge"]
        if bridge in SHARED_BRIDGES or bridge.startswith(SHARED_BRIDGE_PREFIXES):
            continue
        endpoints[bridge].append((dev, ifname))

    for bridge, ends in sorted(endpoints.items()):
        if len(ends) != 2:
            warnings.append(f"bridge {bridge}: {len(ends)} endpoint(s) {ends} -- no cable created")
            continue
        (dev_a, if_a), (dev_b, if_b) = ends
        a, b = nb_ifaces[(dev_a, if_a)], nb_ifaces[(dev_b, if_b)]
        a = nb.dcim.interfaces.get(a.id)  # refresh: cable state may predate this run
        if a.cable:
            peers = [(p.device.name, p.name) for p in (a.link_peers or [])]
            if (dev_b, if_b) in peers:
                counts["unchanged"] += 1
            else:
                warnings.append(f"bridge {bridge}: {dev_a}/{if_a} already cabled to {peers}, expected {dev_b}/{if_b}")
            continue
        nb.dcim.cables.create(
            a_terminations=[{"object_type": "dcim.interface", "object_id": a.id}],
            b_terminations=[{"object_type": "dcim.interface", "object_id": b.id}],
            label=bridge,
        )
        counts["created"] += 1

    # -- report -----------------------------------------------------------------
    print(f"created: {counts['created']}  updated: {counts['updated']}  unchanged: {counts['unchanged']}")
    for w in warnings:
        print(f"WARNING: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
