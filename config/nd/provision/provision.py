#!/usr/bin/env python3
"""Idempotent, phased provisioning of one lab testbed into one Nexus Dashboard.

    provision.py --topology topology_nd431.yaml [--nd-ip 10.10.20.20] [--phase all] [--dry-run]

Phases (each safe to re-run; --phase all runs them in order):
  fabrics   create SITE1/SITE2/ISN if absent, then merge `settings` into each fabric object (GET/update/PUT)
  msd       create the MSD fabric group if absent, add members one at a time (ND rejects batches)
  switches  add switches per fabric by IP (discover+import), wait until they list, set roles, configDeploy
  isn       WAN loopback + router-id policy, ebgpVrfLite links, CDP policies, deploy ISN/SITE1/SITE2
  overlay   VRFs + networks in each fabric, attachments per switch, vrfActions/networkActions deploy
  deploy    configDeploy every fabric and print any non-empty pendingConfig
Credentials: ND_IP4/ND_USERNAME/ND_PASSWORD/ND_DOMAIN (controller), NXOS_PASSWORD / IOSXE_PASSWORD (switch discovery).
"""
from __future__ import annotations

import argparse
import copy
import json
import os  # noqa: F401  used by switch/isn/overlay phases added in Tasks 10-12
import time  # noqa: F401  used by switch/isn/overlay phases added in Tasks 10-12
from pathlib import Path
from typing import Any

from nd_client import NDClient, NDCredentials
from topology import Fabric, FabricGroup, Topology, load

PHASES = ["fabrics", "msd", "switches", "isn", "overlay", "deploy"]


def fabric_create_payload(fabric: Fabric) -> dict:
    return {
        "name": fabric.name,
        "category": "fabric",
        "licenseTier": "premier",
        "securityDomain": "all",
        "telemetryCollection": False,
        "management": {"type": fabric.type, "bgpAsn": fabric.asn},
    }


def fabric_group_create_payload(group: FabricGroup) -> dict:
    management = {"type": "vxlan"}
    management.update(group.settings.get("management", {}))
    return {"name": group.name, "category": "fabricGroup", "management": management}


def merge_settings(current: dict, settings: dict) -> dict:
    merged = copy.deepcopy(current)
    for key, value in settings.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


class Provisioner:
    def __init__(self, client: NDClient, topo: Topology, dry_run: bool = False) -> None:
        self.client = client
        self.topo = topo
        self.dry_run = dry_run

    # -- helpers -------------------------------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        print(("[dry-run] " if self.dry_run else "") + msg)

    def _post(self, path: str, body: Any) -> Any:
        self._log(f"POST {path} {json.dumps(body)[:300]}")
        return None if self.dry_run else self.client.post(path, json=body)

    def _put(self, path: str, body: Any) -> Any:
        self._log(f"PUT {path}")
        return None if self.dry_run else self.client.put(path, json=body)

    def existing_fabrics(self) -> dict[str, dict]:
        """Fabrics AND fabric groups by name. GET /fabrics lists only category=fabric; groups need ?category=fabricGroup."""
        found = {f["name"]: f for f in (self.client.get("/fabrics") or {}).get("fabrics", [])}
        found.update({g["name"]: g for g in (self.client.get("/fabrics", params={"category": "fabricGroup"}) or {}).get("fabrics", [])})
        return found

    # -- phase: fabrics ------------------------------------------------------------------------------------
    def phase_fabrics(self) -> None:
        existing = self.existing_fabrics()
        for fabric in self.topo.fabrics:
            if fabric.name not in existing:
                self._post("/fabrics", fabric_create_payload(fabric))
            if fabric.settings and not self.dry_run:
                current = self.client.get(f"/fabrics/{fabric.name}")
                merged = merge_settings(current, fabric.settings)
                if merged != current:
                    self._put(f"/fabrics/{fabric.name}", merged)
            elif fabric.settings:
                self._log(f"would merge settings into /fabrics/{fabric.name}: {json.dumps(fabric.settings)}")

    # -- phase: msd ----------------------------------------------------------------------------------------
    def phase_msd(self) -> None:
        existing = self.existing_fabrics()
        for group in self.topo.fabric_groups:
            if group.name not in existing:
                self._post("/fabrics", fabric_group_create_payload(group))
            members = {m["name"] for m in (self.client.get(f"/fabrics/{group.name}/members") or {}).get("fabrics", [])} if not self.dry_run else set()
            for member in group.members:
                if member not in members:
                    self._post(f"/fabrics/{group.name}/actions/addMembers", {"members": [{"name": member}]})

    def run(self, phases: list[str]) -> None:
        for phase in phases:
            print(f"=== phase {phase} ===")
            getattr(self, f"phase_{phase}")()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--nd-ip", help="override ND_IP4")
    parser.add_argument("--phase", default="all", choices=PHASES + ["all"])
    parser.add_argument("--dry-run", action="store_true", help="print every write instead of sending it")
    args = parser.parse_args()
    topo = load(args.topology)
    client = NDClient(NDCredentials.from_env(args.nd_ip))
    client.login()
    Provisioner(client, topo, dry_run=args.dry_run).run(PHASES if args.phase == "all" else [args.phase])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
