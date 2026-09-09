#!/usr/bin/env python3
"""Declarative testbed description consumed by provision.py (see topology_nd421.yaml for the schema by example)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Switch:
    hostname: str
    ip: str
    role: str
    platform: str = "nx-os"


@dataclass(frozen=True)
class Fabric:
    name: str
    type: str
    asn: str
    settings: dict = field(default_factory=dict)
    switches: list[Switch] = field(default_factory=list)


@dataclass(frozen=True)
class FabricGroup:
    name: str
    settings: dict = field(default_factory=dict)
    members: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Link:
    src_fabric: str
    src: str
    src_if: str
    dst_fabric: str
    dst: str
    dst_if: str
    src_asn: str
    dst_asn: str
    src_ip: str
    dst_ip: str
    mtu: int = 9000


@dataclass(frozen=True)
class Wan:
    hostname: str
    fabric: str
    cdp_interfaces: list[str] = field(default_factory=list)
    loopback: dict = field(default_factory=dict)
    bgp_router_id: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Isn:
    links: list[Link] = field(default_factory=list)
    wan: Wan | None = None


@dataclass(frozen=True)
class Overlay:
    vrfs: list[dict] = field(default_factory=list)
    networks: list[dict] = field(default_factory=list)
    vrf_attachments: list[dict] = field(default_factory=list)
    network_attachments: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Topology:
    fabrics: list[Fabric]
    fabric_groups: list[FabricGroup]
    isn: Isn
    overlay: Overlay

    def switches(self) -> dict[str, Switch]:
        return {s.hostname: s for f in self.fabrics for s in f.switches}

    def switch_fabric(self, hostname: str) -> str:
        for fabric in self.fabrics:
            if any(s.hostname == hostname for s in fabric.switches):
                return fabric.name
        raise ValueError(f"unknown switch {hostname}")


def _validate(topo: Topology) -> None:
    fabrics_by_hostname: dict[str, list[str]] = {}
    for fabric in topo.fabrics:
        for switch in fabric.switches:
            fabrics_by_hostname.setdefault(switch.hostname, []).append(fabric.name)
    for hostname, fabric_names in fabrics_by_hostname.items():
        if len(fabric_names) > 1:
            raise ValueError(f"switch {hostname} is declared in more than one fabric: {fabric_names}")
    names = set(fabrics_by_hostname)
    fabrics = {f.name for f in topo.fabrics}
    for group in topo.fabric_groups:
        for member in group.members:
            if member not in fabrics:
                raise ValueError(f"fabric group {group.name}: unknown member fabric {member}")
    for link in topo.isn.links:
        for host in (link.src, link.dst):
            if host not in names:
                raise ValueError(f"isn link references unknown switch {host}")
    if topo.isn.wan and topo.isn.wan.hostname not in names:
        raise ValueError(f"isn.wan references unknown switch {topo.isn.wan.hostname}")
    for att in topo.overlay.vrf_attachments + topo.overlay.network_attachments:
        switch_name = att.get("switch")
        if not switch_name:
            raise ValueError(f"overlay attachment is missing 'switch': {att}")
        if switch_name not in names:
            raise ValueError(f"overlay attachment references unknown switch {switch_name}")


def load(path: Path) -> Topology:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fabrics = [
        Fabric(name=f["name"], type=f["type"], asn=str(f["asn"]), settings=f.get("settings", {}), switches=[Switch(**s) for s in f.get("switches", [])])
        for f in raw.get("fabrics", [])
    ]
    groups = [FabricGroup(**g) for g in raw.get("fabric_groups", [])]
    isn_raw = raw.get("isn", {}) or {}
    isn = Isn(links=[Link(**item) for item in isn_raw.get("links", [])], wan=Wan(**isn_raw["wan"]) if isn_raw.get("wan") else None)
    overlay = Overlay(**(raw.get("overlay", {}) or {}))
    topo = Topology(fabrics=fabrics, fabric_groups=groups, isn=isn, overlay=overlay)
    _validate(topo)
    return topo
