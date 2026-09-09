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
import os
import time
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


def switch_add_payload(fabric: Fabric, password: str, username: str = "admin") -> dict:
    platforms = {s.platform for s in fabric.switches}
    if len(platforms) != 1:
        raise ValueError(f"{fabric.name}: one platformType per add call, got {platforms}")
    return {
        "switches": [{"ip": s.ip, "hostname": s.hostname, "switchRole": s.role} for s in fabric.switches],
        "platformType": platforms.pop(),
        "preserveConfig": False,
        "useCredentialForWrite": True,
        "username": username,
        "password": password,
    }


def _switch_password(fabric: Fabric) -> str:
    """IOSXE_PASSWORD for externalConnectivity fabrics (they hold the ios-xe WAN router), NXOS_PASSWORD otherwise;
    falls back to NXOS_PASSWORD if IOSXE_PASSWORD is unset."""
    env_var = "IOSXE_PASSWORD" if fabric.type == "externalConnectivity" else "NXOS_PASSWORD"
    value = os.environ.get(env_var)
    return value if value else os.environ.get("NXOS_PASSWORD", "")


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
        self._log(f"PUT {path} {json.dumps(body)[:300]}")
        return None if self.dry_run else self.client.put(path, json=body)

    def _read(self, path: str, key: str, params: dict | None = None) -> list:
        """GET a list endpoint; an HTTP error (e.g. 404 for a fabric that does not exist yet) reads as empty."""
        try:
            body = self.client.get(path, params=params) or {}
        except RuntimeError as exc:
            self._log(f"read {path} failed ({str(exc)[:80]}); treating as empty")
            return []
        return body.get(key, []) if isinstance(body, dict) else body

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
            members = {m["name"] for m in self._read(f"/fabrics/{group.name}/members", "fabrics")}
            for member in group.members:
                if member not in members:
                    self._post(f"/fabrics/{group.name}/actions/addMembers", {"members": [{"name": member}]})

    # -- phase: switches ------------------------------------------------------------------------------------
    def fabric_switches(self, fabric_name: str) -> dict[str, dict]:
        return {s["hostname"]: s for s in self._read(f"/fabrics/{fabric_name}/switches", "switches")}

    def serial(self, hostname: str) -> str:
        """Serial number by hostname, looked up live (serials change on every VM rebuild). Placeholder in dry runs."""
        fabric = self.topo.switch_fabric(hostname)
        entry = self.fabric_switches(fabric).get(hostname)
        if entry:
            return entry["serialNumber"]
        if self.dry_run:
            return f"<{hostname}-serial>"
        raise RuntimeError(f"{hostname} is not in fabric {fabric} on {self.client.creds.ip}; run --phase switches first")

    def wait_for_switches(self, fabric_name: str, hostnames: list[str], timeout: int = 900) -> None:
        deadline = time.time() + timeout
        present: dict[str, dict] = {}
        while time.time() < deadline:
            present = self.fabric_switches(fabric_name)
            if all(hostname in present for hostname in hostnames):
                return
            time.sleep(15)
        raise TimeoutError(f"{fabric_name}: switches never listed: {[h for h in hostnames if h not in present]}")

    def config_deploy(self, fabric_name: str) -> None:
        self._post(f"/fabrics/{fabric_name}/actions/configDeploy", None)

    def pending(self, fabric_name: str, serial: str) -> list:
        return self._read(f"/fabrics/{fabric_name}/switches/{serial}/pendingConfig", "pendingConfig")

    def phase_switches(self) -> None:
        for fabric in self.topo.fabrics:
            present = self.fabric_switches(fabric.name)
            missing = [s for s in fabric.switches if s.hostname not in present]
            if missing:
                password = _switch_password(fabric)
                self._post(f"/fabrics/{fabric.name}/switches", switch_add_payload(Fabric(fabric.name, fabric.type, fabric.asn, {}, missing), password))
                if not self.dry_run:
                    self.wait_for_switches(fabric.name, [s.hostname for s in missing])
                    present = self.fabric_switches(fabric.name)
            wrong = [
                {"switchId": present[s.hostname]["serialNumber"], "role": s.role}
                for s in fabric.switches
                if s.hostname in present and present[s.hostname].get("switchRole") != s.role
            ]
            if wrong:
                self._post(f"/fabrics/{fabric.name}/switchActions/changeRoles", {"switchRoles": wrong})
            self.config_deploy(fabric.name)

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
