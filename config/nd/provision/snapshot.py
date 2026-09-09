#!/usr/bin/env python3
"""Read-only dump of a Nexus Dashboard's fabric state, and a normalized diff of two dumps.

    snapshot.py dump <out_dir> [--nd-ip IP]
    snapshot.py diff <dir_a> <dir_b> [--map S1_BG1=S3_BG1 ...]

`dump` writes one JSON file per object type per fabric. `diff` rewrites hostnames per --map, strips
volatile fields (serials, IPs, UUIDs, timestamps, counters), sorts lists, then prints a unified diff.
An empty diff is the mechanical proof that two testbeds mirror each other.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any, Callable

from nd_client import NDClient, NDCredentials

VOLATILE_KEYS = {
    "serialNumber",
    "switchId",
    "srcSwitchId",
    "dstSwitchId",
    "switchIds",
    "fabricManagementIp",
    "ipAddress",
    "ip",
    "mgmtIp",
    "systemUpTime",
    "id",
    "uuid",
    "linkId",
    "policyId",
    "source",
    "meta",
    "createdOn",
    "modifiedOn",
    "lastModified",
    "timestamp",
    "additionalData",
    "anomalyLevel",
    "advisoryLevel",
    "networkStatus",
    "vrfStatus",
    "vpcData",
    "softwareVersion",
    "model",
    # per-object identity/time/operational fields that differ between two controllers by construction
    "policyId",
    "POLICY_ID",
    "createTimestamp",
    "updateTimestamp",
    "operData",
    "srcSwitchInfo",
    "dstSwitchInfo",
    "linkPresent",
    "linkDiscovered",
    "SERIAL_NUMBER",
    "PASSWORD_ENCRYPT",
    "switchName",
}


def normalize(obj: Any, name_map: dict[str, str]) -> Any:
    """Return obj with hostnames rewritten, volatile keys removed and lists of dicts sorted deterministically."""
    if isinstance(obj, dict):
        return {k: normalize(v, name_map) for k, v in sorted(obj.items()) if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        items = [normalize(v, name_map) for v in obj]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(obj, str):
        for old, new in name_map.items():
            # Hostnames contain underscores, which `\b` treats as word characters; use alphanumeric lookarounds so
            # "interfaces_SITE1_S1_BG1.json" and "tap_S1_BG1" map too, while "S1_BG10" does not.
            obj = re.sub(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])", new, obj)
        return obj
    return obj


def _write(out_dir: Path, name: str, data: Any) -> None:
    (out_dir / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fetch(name: str, fn: Callable[[], Any]) -> Any:
    """Run one GET/POST closure for `dump`; a broken read (e.g. HTTP 404/500 on an endpoint that isn't
    populated yet) must not abort the rest of the snapshot -- log it and let `_write` record `null`."""
    try:
        return fn()
    except RuntimeError as exc:
        print(f"skipped {name}: {exc}")
        return None


def dump(client: NDClient, out_dir: Path) -> None:
    def _attach_query(kind: str, fabric: str, serials: list[str]) -> Any:
        return client.post(f"/fabrics/{fabric}/{kind}Attachments/query", json={"switchIds": serials})

    out_dir.mkdir(parents=True, exist_ok=True)
    fabrics = _fetch("fabrics", lambda: client.get("/fabrics")) or {}
    _write(out_dir, "fabrics", fabrics)
    _write(out_dir, "inventory_switches", _fetch("inventory_switches", lambda: client.get("/inventory/switches")))
    fabric_groups = _fetch("fabric_groups", lambda: client.get("/fabrics", params={"category": "fabricGroup"})) or {}
    _write(out_dir, "fabric_groups", fabric_groups)
    for group in fabric_groups.get("fabrics", []):
        name = group["name"]
        _write(out_dir, f"fabric_group_{name}", _fetch(f"fabric_group_{name}", lambda: client.get(f"/fabrics/{name}")))
        _write(out_dir, f"members_{name}", _fetch(f"members_{name}", lambda: client.get(f"/fabrics/{name}/members")))
    for fabric in fabrics.get("fabrics", []):
        name = fabric["name"]
        _write(out_dir, f"fabric_{name}", _fetch(f"fabric_{name}", lambda: client.get(f"/fabrics/{name}")))
        switches = _fetch(f"switches_{name}", lambda: client.get(f"/fabrics/{name}/switches")) or {}
        _write(out_dir, f"switches_{name}", switches)
        _write(out_dir, f"members_{name}", _fetch(f"members_{name}", lambda: client.get(f"/fabrics/{name}/members")))
        _write(out_dir, f"links_{name}", _fetch(f"links_{name}", lambda: client.paged("/links", "links", params={"fabricName": name})))
        _write(out_dir, f"policies_{name}", _fetch(f"policies_{name}", lambda: client.paged(f"/fabrics/{name}/policies", "policies")))
        _write(out_dir, f"vrfs_{name}", _fetch(f"vrfs_{name}", lambda: client.get(f"/fabrics/{name}/vrfs")))
        _write(out_dir, f"networks_{name}", _fetch(f"networks_{name}", lambda: client.get(f"/fabrics/{name}/networks")))
        serials = [s["serialNumber"] for s in switches.get("switches", [])]
        if serials:
            _write(out_dir, f"vrf_attachments_{name}", _fetch(f"vrf_attachments_{name}", lambda: _attach_query("vrf", name, serials)))
            _write(out_dir, f"network_attachments_{name}", _fetch(f"network_attachments_{name}", lambda: _attach_query("network", name, serials)))
        for switch in switches.get("switches", []):
            serial_number = switch["serialNumber"]
            _write(
                out_dir,
                f"interfaces_{name}_{switch['hostname']}",
                _fetch(f"interfaces_{name}_{switch['hostname']}", lambda: client.get(f"/fabrics/{name}/switches/{serial_number}/interfaces")),
            )
    print(f"snapshot written to {out_dir}")


def diff(dir_a: Path, dir_b: Path, name_map: dict[str, str]) -> int:
    """Print a unified diff of normalized JSON for every file present in dir_a; return 1 if any differ."""
    rc = 0
    for file_a in sorted(dir_a.glob("*.json")):
        mapped_name = normalize(file_a.name, name_map)
        file_b = dir_b / mapped_name
        if not file_b.exists():
            print(f"--- only in {dir_a}: {file_a.name}")
            rc = 1
            continue
        text_a = json.dumps(normalize(json.loads(file_a.read_text()), name_map), indent=1, sort_keys=True).splitlines()
        text_b = json.dumps(normalize(json.loads(file_b.read_text()), {}), indent=1, sort_keys=True).splitlines()
        lines = list(difflib.unified_diff(text_a, text_b, fromfile=str(file_a), tofile=str(file_b), lineterm=""))
        if lines:
            rc = 1
            print("\n".join(lines))
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_dump = sub.add_parser("dump")
    p_dump.add_argument("out_dir", type=Path)
    p_dump.add_argument("--nd-ip", help="override ND_IP4")
    p_diff = sub.add_parser("diff")
    p_diff.add_argument("dir_a", type=Path)
    p_diff.add_argument("dir_b", type=Path)
    p_diff.add_argument("--map", action="append", default=[], help="OLD=NEW hostname mapping applied to dir_a (repeatable)")
    args = parser.parse_args()
    if args.cmd == "dump":
        client = NDClient(NDCredentials.from_env(args.nd_ip))
        client.login()
        dump(client, args.out_dir)
        return 0
    name_map = dict(item.split("=", 1) for item in args.map)
    return diff(args.dir_a, args.dir_b, name_map)


if __name__ == "__main__":
    raise SystemExit(main())
