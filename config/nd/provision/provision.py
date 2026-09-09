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
from topology import Fabric, FabricGroup, Link, Topology, load

PHASES = ["fabrics", "msd", "switches", "isn", "overlay", "deploy"]

LOG_BODY_LIMIT = 2000


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


def link_payload(link: Link, src_serial: str, dst_serial: str) -> dict:
    return {
        "links": [
            {
                "srcFabricName": link.src_fabric,
                "srcSwitchName": link.src,
                "srcSwitchId": src_serial,
                "srcInterfaceName": link.src_if,
                "dstFabricName": link.dst_fabric,
                "dstSwitchName": link.dst,
                "dstSwitchId": dst_serial,
                "dstInterfaceName": link.dst_if,
                "configData": {
                    "policyType": "ebgpVrfLite",
                    "templateInputs": {
                        "srcEbgpAsn": link.src_asn,
                        "dstEbgpAsn": link.dst_asn,
                        "srcIpAddressMask": link.src_ip,
                        "dstIpAddress": link.dst_ip,
                        "linkMtu": link.mtu,
                        "autoGenConfigPeer": True,
                        "inheritTtagFabricSetting": True,
                        "templateConfigGenPeer": "ios_xe_Ext_VRF_Lite_Jython",
                        "srcInterfaceDescription": f"connected-to-{link.dst}-{link.dst_if}",
                        "dstInterfaceDescription": f"connected-to-{link.src}-{link.src_if}",
                    },
                },
            }
        ]
    }


def attachment_payload(kind: str, att: dict, serial: str) -> dict:
    if kind == "vrf":
        return {"attachments": [{"vrfName": att["vrf"], "switchId": serial, "attach": True}]}
    return {"attachments": [{"networkName": att["network"], "switchId": serial, "vlanId": att["vlan"], "interfaces": att.get("interfaces", []), "attach": True}]}


def cdp_run_policy(serial: str) -> dict:
    return {"templateName": "ios_xe_cdp_run", "entityType": "switch", "entityName": "SWITCH", "switchId": serial, "templateInputs": {}}


def cdp_policy(serial: str, interface: str) -> dict:
    return {
        "templateName": "ios_xe_cdp_enable_interface",
        "entityType": "interface",
        "entityName": interface,
        "switchId": serial,
        "templateInputs": {"INTF_NAME": interface},
    }


def router_id_policy(serial: str, inputs: dict) -> dict:
    return {"templateName": "ios_xe_bgp_router_id", "entityType": "switch", "entityName": "SWITCH", "switchId": serial, "templateInputs": inputs}


def loopback_interface(serial: str, loopback: dict) -> dict:
    return {
        "interfaces": [
            {
                "switchId": serial,
                "interfaceType": "loopback",
                "interfaceName": f"Loopback{loopback.get('id', 0)}",
                "configData": {
                    "networkOS": {
                        "networkOSType": "ios-xe",
                        "policy": {"policyType": "iosXeLoopback", "adminState": True, "ip": loopback["ip"], "description": loopback.get("description", "")},
                    }
                },
            }
        ]
    }


class Provisioner:
    def __init__(self, client: NDClient, topo: Topology, dry_run: bool = False, settle_seconds: int = 30) -> None:
        self.client = client
        self.topo = topo
        self.dry_run = dry_run
        self.settle_seconds = settle_seconds

    # -- helpers -------------------------------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        print(("[dry-run] " if self.dry_run else "") + msg)

    def _post(self, path: str, body: Any) -> Any:
        self._log(f"POST {path} {json.dumps(body)[:LOG_BODY_LIMIT]}")
        return None if self.dry_run else self.client.post(path, json=body)

    def _put(self, path: str, body: Any) -> Any:
        self._log(f"PUT {path} {json.dumps(body)[:LOG_BODY_LIMIT]}")
        return None if self.dry_run else self.client.put(path, json=body)

    def _read(self, path: str, key: str, params: dict | None = None) -> list:
        """GET a list endpoint; an HTTP error (e.g. 404 for a fabric that does not exist yet) reads as empty."""
        try:
            body = self.client.get(path, params=params) or {}
        except RuntimeError as exc:
            self._log(f"read {path} failed ({str(exc)[:80]}); treating as empty")
            return []
        return body.get(key, []) if isinstance(body, dict) else body

    def _read_one(self, path: str) -> dict:
        """GET a single object endpoint; an HTTP error (e.g. 404 for a fabric that does not exist yet) reads as empty."""
        try:
            return self.client.get(path) or {}
        except RuntimeError as exc:
            self._log(f"read {path} failed ({str(exc)[:80]}); treating as empty")
            return {}

    def _read_paged(self, path: str, key: str, params: dict | None = None) -> list:
        """Walk a paged list endpoint; an HTTP error (e.g. 404 for a fabric that does not exist yet) reads as empty."""
        try:
            return self.client.paged(path, key, params=params)
        except RuntimeError as exc:
            self._log(f"read {path} failed ({str(exc)[:80]}); treating as empty")
            return []

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
            if not fabric.settings:
                continue
            current = self._read_one(f"/fabrics/{fabric.name}")
            if not current and not self.dry_run:
                # any empty first read in a live run gets one re-read: either the fabric was just created
                # by the POST above (re-read now that it exists), or this is a transient read failure on a
                # fabric that already existed.
                current = self._read_one(f"/fabrics/{fabric.name}")
            if not current:
                if self.dry_run:
                    # dry-run before create: nothing to merge against yet.
                    self._log(f"would apply settings to new fabric /fabrics/{fabric.name}: {json.dumps(fabric.settings)[:LOG_BODY_LIMIT]}")
                else:
                    # live run, still empty after the re-read: a transient failure, not a missing fabric --
                    # do not create or write anything based on a guess.
                    self._log(f"could not read /fabrics/{fabric.name} after create/re-read; skipping settings this run")
                continue
            merged = merge_settings(current, fabric.settings)
            if merged != current:
                self._put(f"/fabrics/{fabric.name}", merged)
            else:
                self._log(f"settings already applied on /fabrics/{fabric.name}")

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
        """Final convergence check: fails loud (does not swallow HTTP errors like `_read`) since a request
        error here must stop `deploy`/`isn`/`overlay` from reporting false convergence."""
        return self.client.get(f"/fabrics/{fabric_name}/switches/{serial}/pendingConfig") or []

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

    # -- phase: isn ------------------------------------------------------------------------------------------
    def _policies(self, fabric: str, serial: str) -> list[dict]:
        return self._read_paged(f"/fabrics/{fabric}/policies", "policies", params={"switchId": serial})

    def _ensure_policy(self, fabric: str, serial: str, policy: dict) -> None:
        have = [p for p in self._policies(fabric, serial) if p.get("templateName") == policy["templateName"] and p.get("entityName") == policy["entityName"]]
        if not have:
            self._post(f"/fabrics/{fabric}/policies", {"policies": [policy]})

    def phase_isn(self) -> None:
        wan = self.topo.isn.wan
        wan_serial: str | None = None
        if wan:
            fabric_obj = self._read_one(f"/fabrics/{wan.fabric}")
            if fabric_obj and fabric_obj.get("management", {}).get("monitoredMode"):
                self._put(f"/fabrics/{wan.fabric}", merge_settings(fabric_obj, {"management": {"monitoredMode": False}}))
            wan_serial = self.serial(wan.hostname)
            loopbacks = self._read(f"/fabrics/{wan.fabric}/switches/{wan_serial}/interfaces", "interfaces")
            names = {i.get("interfaceName") for i in loopbacks}
            if wan.loopback and f"Loopback{wan.loopback.get('id', 0)}" not in names:
                self._post(f"/fabrics/{wan.fabric}/switches/{wan_serial}/interfaces", loopback_interface(wan_serial, wan.loopback))
            if wan.bgp_router_id:
                self._ensure_policy(wan.fabric, wan_serial, router_id_policy(wan_serial, wan.bgp_router_id))
            self._ensure_policy(wan.fabric, wan_serial, cdp_run_policy(wan_serial))
            for intf in wan.cdp_interfaces:
                self._ensure_policy(wan.fabric, wan_serial, cdp_policy(wan_serial, intf))
        for link in self.topo.isn.links:
            have = self._read_paged("/links", "links", params={"fabricName": link.src_fabric})
            if any(h.get("srcSwitchName") == link.src and h.get("srcInterfaceName") == link.src_if for h in have):
                continue
            self._post("/links", link_payload(link, self.serial(link.src), self.serial(link.dst)))
        for name in sorted({item.dst_fabric for item in self.topo.isn.links} | ({wan.fabric} if wan else set())):
            self.config_deploy(name)
        if wan and not self.dry_run:
            time.sleep(self.settle_seconds)
            assert wan_serial is not None
            left = self.pending(wan.fabric, wan_serial)
            print(f"{wan.hostname} pendingConfig after deploy: {len(left)} line(s)" + ("" if not left else " -- read /deploymentHistory"))

    # -- phase: overlay --------------------------------------------------------------------------------------
    def phase_overlay(self) -> None:
        for item in self.topo.overlay.vrfs:
            for fabric in item["fabrics"]:
                have = {v["vrfName"] for v in self._read(f"/fabrics/{fabric}/vrfs", "vrfs")}
                if item["object"]["vrfName"] not in have:
                    self._post(f"/fabrics/{fabric}/vrfs", {"vrfs": [dict(item["object"], fabricName=fabric)]})
        for item in self.topo.overlay.networks:
            for fabric in item["fabrics"]:
                have = {n["networkName"] for n in self._read(f"/fabrics/{fabric}/networks", "networks")}
                if item["object"]["networkName"] not in have:
                    self._post(f"/fabrics/{fabric}/networks", {"networks": [dict(item["object"], fabricName=fabric)]})
        touched: dict[str, set[str]] = {}
        for att in self.topo.overlay.vrf_attachments:
            serial = self.serial(att["switch"])
            self._post(f"/fabrics/{att['fabric']}/vrfAttachments", attachment_payload("vrf", att, serial))
            touched.setdefault(att["fabric"], set()).add(serial)
        for att in self.topo.overlay.network_attachments:
            serial = self.serial(att["switch"])
            self._post(f"/fabrics/{att['fabric']}/networkAttachments", attachment_payload("network", att, serial))
            touched.setdefault(att["fabric"], set()).add(serial)
        for fabric, serials in touched.items():
            self._post(f"/fabrics/{fabric}/vrfActions/deploy", {"switchIds": sorted(serials)})
            self._post(f"/fabrics/{fabric}/networkActions/deploy", {"switchIds": sorted(serials)})

    # -- phase: deploy -----------------------------------------------------------------------------------------
    def phase_deploy(self) -> None:
        for fabric in self.topo.fabrics:
            self.config_deploy(fabric.name)
        if self.dry_run:
            return
        time.sleep(self.settle_seconds)
        for fabric in self.topo.fabrics:
            for hostname, entry in self.fabric_switches(fabric.name).items():
                left = self.pending(fabric.name, entry["serialNumber"])
                print(f"{fabric.name}/{hostname}: pendingConfig {len(left)} line(s)")

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
