"""Read one Nexus Dashboard controller (or a snapshot.py dump of one) into per-fabric structures for golden drift/restore.

`read_live` issues the reads `snapshot.dump` does, but any HTTP error raises `LiveReadError` instead of being skipped: a drift
report built from a half-read controller would be wrong. `read_live_from_snapshot` maps the dump's file names to the same shape.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from nd_client import NDClient
from topology import Topology


class LiveReadError(RuntimeError):
    """A live read failed or a golden fabric/group is absent."""


@dataclass
class LiveFabric:
    name: str
    category: str  # "fabric" | "fabricGroup"
    settings: dict = field(default_factory=dict)
    switches: dict[str, dict] = field(default_factory=dict)  # hostname -> switch object
    links: list[dict] = field(default_factory=list)
    interfaces: dict[str, list[dict]] = field(default_factory=dict)  # hostname -> interface objects
    vrfs: list[dict] = field(default_factory=list)
    networks: list[dict] = field(default_factory=list)
    vrf_attachments: list[dict] = field(default_factory=list)  # attach == True only
    network_attachments: list[dict] = field(default_factory=list)  # attach == True only
    vpc_pairs: list[dict] = field(default_factory=list)
    tor_associations: list[dict] = field(default_factory=list)


def _items(body: Any, key: str) -> list[dict]:
    """ND answers either a bare list or {key: [...], meta: ...}; null/missing means empty."""
    if not body:
        return []
    if isinstance(body, list):
        return body
    return body.get(key) or []


def _attached(body: Any) -> list[dict]:
    return [a for a in _items(body, "attachments") if a.get("attach") is True]


def _group_names(topo: Topology) -> list[str]:
    return [g.name for g in topo.fabric_groups]


def read_live(client: NDClient, topo: Topology) -> dict[str, LiveFabric]:
    def get(path: str, params: dict | None = None) -> Any:
        try:
            return client.get(path, params=params)
        except (RuntimeError, requests.RequestException, OSError) as exc:
            raise LiveReadError(f"GET {path}: {exc}") from exc

    def paged(path: str, key: str, params: dict | None = None) -> list[dict]:
        try:
            return client.paged(path, key, params=params)
        except (RuntimeError, requests.RequestException, OSError) as exc:
            raise LiveReadError(f"GET {path}: {exc}") from exc

    def query(kind: str, fabric: str, serials: list[str]) -> list[dict]:
        path = f"/fabrics/{fabric}/{kind}Attachments/query"
        try:
            return _attached(client.post(path, json={"switchIds": serials}))
        except (RuntimeError, requests.RequestException, OSError) as exc:
            raise LiveReadError(f"POST {path}: {exc}") from exc

    present = {f["name"] for f in _items(get("/fabrics"), "fabrics")}
    for fabric in topo.fabrics:
        if fabric.name not in present:
            raise LiveReadError(f"golden fabric {fabric.name} is not present on the controller")
    groups_present = {g["name"] for g in _items(get("/fabrics", params={"category": "fabricGroup"}), "fabrics")}
    for name in _group_names(topo):
        if name not in groups_present:
            raise LiveReadError(f"golden fabric group {name} is not present on the controller")

    result: dict[str, LiveFabric] = {}
    for group in _group_names(topo):
        live = LiveFabric(name=group, category="fabricGroup", settings=get(f"/fabrics/{group}") or {})
        live.links = paged("/links", "links", {"fabricName": group})
        live.vrfs = _items(get(f"/fabrics/{group}/vrfs"), "vrfs")
        live.networks = _items(get(f"/fabrics/{group}/networks"), "networks")
        result[group] = live
    for fabric in topo.fabrics:
        name = fabric.name
        live = LiveFabric(name=name, category="fabric", settings=get(f"/fabrics/{name}") or {})
        switch_list = _items(get(f"/fabrics/{name}/switches"), "switches")
        live.switches = {s["hostname"]: s for s in switch_list}
        live.links = paged("/links", "links", {"fabricName": name})
        live.vpc_pairs = _items(get(f"/fabrics/{name}/vpcPairs"), "vpcPairs")
        live.vrfs = _items(get(f"/fabrics/{name}/vrfs"), "vrfs")
        live.networks = _items(get(f"/fabrics/{name}/networks"), "networks")
        by_host = live.switches
        for pair in (p for p in topo.tor_pairs if p.fabric == name):
            if pair.leaf not in by_host or pair.peer not in by_host:
                continue
            params = {"aggregationOrLeafSwitchId": by_host[pair.leaf]["serialNumber"], "aggregationOrLeafPeerSwitchId": by_host[pair.peer]["serialNumber"]}
            try:
                live.tor_associations.extend(_items(client.get(f"/fabrics/{name}/accessAssociations", params=params), "associations"))
            except RuntimeError as exc:
                # A fabric with no pairings answers 400/404; anything else is a real failure.
                if not re.search(r"-> HTTP (400|404)\b", str(exc)):
                    raise LiveReadError(f"GET /fabrics/{name}/accessAssociations: {exc}") from exc
        serials = [s["serialNumber"] for s in switch_list]
        if serials:
            live.vrf_attachments = query("vrf", name, serials)
            live.network_attachments = query("network", name, serials)
        for switch in switch_list:
            body = get(f"/fabrics/{name}/switches/{switch['serialNumber']}/interfaces")
            live.interfaces[switch["hostname"]] = _items(body, "interfaces")
        result[name] = live
    return result


def read_live_from_snapshot(snapshot_dir: Path, topo: Topology) -> dict[str, LiveFabric]:
    def load(name: str) -> Any:
        path = snapshot_dir / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    result: dict[str, LiveFabric] = {}
    for group in _group_names(topo):
        settings = load(f"fabric_group_{group}")
        if not settings:
            raise LiveReadError(f"snapshot {snapshot_dir} has no fabric_group_{group}.json content")
        result[group] = LiveFabric(
            name=group,
            category="fabricGroup",
            settings=settings,
            links=_items(load(f"links_{group}"), "links"),
            vrfs=_items(load(f"vrfs_{group}"), "vrfs"),
            networks=_items(load(f"networks_{group}"), "networks"),
        )
    for fabric in topo.fabrics:
        name = fabric.name
        settings = load(f"fabric_{name}")
        if not settings:
            raise LiveReadError(f"snapshot {snapshot_dir} has no fabric_{name}.json content")
        switches = {s["hostname"]: s for s in _items(load(f"switches_{name}"), "switches")}
        result[name] = LiveFabric(
            name=name,
            category="fabric",
            settings=settings,
            switches=switches,
            links=_items(load(f"links_{name}"), "links"),
            interfaces={host: _items(load(f"interfaces_{name}_{host}"), "interfaces") for host in switches},
            vrfs=_items(load(f"vrfs_{name}"), "vrfs"),
            networks=_items(load(f"networks_{name}"), "networks"),
            vrf_attachments=_attached(load(f"vrf_attachments_{name}")),
            network_attachments=_attached(load(f"network_attachments_{name}")),
            vpc_pairs=_items(load(f"vpcPairs_{name}"), "vpcPairs"),
            tor_associations=_items(load(f"accessAssociations_{name}"), "associations"),
        )
    return result


def free_ports(live: LiveFabric, hostname: str, all_links: list[dict]) -> list[dict]:
    """Physical ethernet interfaces of `hostname` that no link uses and that are not port-channel members. Interface names are compared
    case-insensitively, as drift_interfaces does."""
    used: set[tuple[str, str]] = set()
    for link in all_links:
        used.add((link.get("srcSwitchName", ""), link.get("srcInterfaceName", "").lower()))
        used.add((link.get("dstSwitchName", ""), link.get("dstInterfaceName", "").lower()))
    return [
        i
        for i in live.interfaces.get(hostname, [])
        if i.get("interfaceType") == "ethernet"
        and not i.get("interfaceName", "").startswith("mgmt")
        and (hostname, i["interfaceName"].lower()) not in used
        and (i.get("operData") or {}).get("portChannelId") == -1
    ]


def interface_path(fabric: str, serial: str, interface: str) -> str:
    return f"/fabrics/{fabric}/switches/{serial}/interfaces/{quote(interface, safe='')}"
