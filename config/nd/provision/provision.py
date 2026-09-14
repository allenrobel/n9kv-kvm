#!/usr/bin/env python3
"""Idempotent, phased provisioning of one lab testbed into one Nexus Dashboard.

    provision.py --topology topology_nd431.yaml [--nd-ip 10.10.20.20] [--phase all] [--dry-run]

Phases (each safe to re-run; --phase all runs them in order):
  fabrics   create SITE1/SITE2/ISN/CAMPUS1 if absent, then merge `settings` into each fabric object (GET/update/PUT)
  msd       create the MSD fabric group if absent, add members one at a time (ND rejects batches)
  switches  shallowDiscovery per fabric (serial/model), add the manageable ones, wait until they list, set roles, recalculate + deploy
  vpc       pair the vPC leaf pairs (ND's default template generates the peer-link port-channel), then recalculate + deploy
  tor       ToR pairing: associate each ToR with its leaf vPC pair using ND's recommended port-channel ids, then recalculate + deploy
  isn       WAN loopback + router-id policy, ebgpVrfLite links, CDP policies, deploy ISN/SITE1/SITE2
  overlay   VRFs + networks in each fabric, attachments per switch, vrfActions/networkActions deploy
  deploy    recalculate + deploy every fabric, then every fabric group (MSD), and print any non-empty pendingConfig
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

PHASES = ["fabrics", "msd", "switches", "vpc", "tor", "isn", "overlay", "deploy"]

LOG_BODY_LIMIT = 2000
# configSave (Recalculate) and deploy are synchronous and take minutes on a 7-switch fabric.
FABRIC_ACTION_TIMEOUT = 900


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


DISCOVERY_PLACEHOLDER = "<from-discovery>"
# ND rejects shallowDiscovery without it ("snmpV3AuthProtocol must not be empty or missing") although the spec marks it
# optional with default md5; the GUI sends MD5. workaround: shallow-discovery-snmpv3-auth-required (ND vault)
SNMPV3_AUTH_PROTOCOL = "md5"
REDACTED_KEYS = {"password", "userPasswd", "secret"}


def _platform(fabric: Fabric) -> str:
    platforms = {s.platform for s in fabric.switches}
    if len(platforms) != 1:
        raise ValueError(f"{fabric.name}: one platformType per add call, got {platforms}")
    return platforms.pop()


def redact(body: Any) -> Any:
    """Copy of body with credential values replaced by *** (log lines must never carry switch/ND passwords)."""
    if isinstance(body, dict):
        return {k: ("***" if k in REDACTED_KEYS else redact(v)) for k, v in body.items()}
    if isinstance(body, list):
        return [redact(v) for v in body]
    return body


def discovery_payload(fabric: Fabric, password: str, username: str = "admin") -> dict:
    """Body for POST /fabrics/{f}/actions/shallowDiscovery: ND logs into each seed IP and reports serial, model,
    software version and a manageability status. Its output is what the add call requires."""
    return {
        "seedIpCollection": [s.ip for s in fabric.switches],
        "maxHop": 0,
        "platformType": _platform(fabric),
        "snmpV3AuthProtocol": SNMPV3_AUTH_PROTOCOL,
        "username": username,
        "password": password,
    }


def switch_add_payload(fabric: Fabric, discovered: dict[str, dict], password: str, username: str = "admin") -> dict:
    """Body for POST /fabrics/{f}/switches. `discovered` maps switch IP -> shallowDiscovery entry; ND rejects the add
    (HTTP 400, schema validation) unless every switch carries the discovered `serialNumber` and `model`.
    `preserveConfig` is false for VXLAN fabrics (ND owns the switch config; the GUI's "Preserve Config" is unchecked)
    and must be true for external fabrics: ND answers HTTP 400 "preserveConfig option should be true for External
    Fabric Type" otherwise (the WAN router keeps its own config; ND only layers policies on it)."""
    platform = _platform(fabric)
    entries = []
    for switch in fabric.switches:
        found = discovered.get(switch.ip)
        if not found:
            raise ValueError(f"{fabric.name}: {switch.hostname} ({switch.ip}) has no discovery result; run shallowDiscovery first")
        entry = {"ip": switch.ip, "hostname": switch.hostname, "switchRole": switch.role, "serialNumber": found["serialNumber"], "model": found["model"]}
        if found.get("softwareVersion"):
            entry["softwareVersion"] = found["softwareVersion"]
        entries.append(entry)
    return {
        "switches": entries,
        "platformType": platform,
        "snmpV3AuthProtocol": SNMPV3_AUTH_PROTOCOL,
        "preserveConfig": fabric.type == "externalConnectivity",
        "useCredentialForWrite": True,
        "username": username,
        "password": password,
    }


def _switch_password(fabric: Fabric) -> str:
    """IOSXE_PASSWORD when the fabric's switches are ios-xe (the WAN router in ISN, the Catalyst leaf in CAMPUS1);
    NXOS_PASSWORD otherwise. Keyed on the switch platform, not the fabric type: a vxlanCampus fabric holds Catalyst
    switches. Fail loud: an unset password must not silently fall back or add switches ND can never SSH into."""
    if fabric.switches and _platform(fabric) == "ios-xe":
        value = os.environ.get("IOSXE_PASSWORD")
        if not value:
            raise SystemExit(f"IOSXE_PASSWORD is not set; it is required to add IOS-XE switches to fabric {fabric.name}")
        return value
    value = os.environ.get("NXOS_PASSWORD")
    if not value:
        raise SystemExit(f"NXOS_PASSWORD is not set; it is required to add NX-OS switches to fabric {fabric.name}")
    return value


def vpc_pair_payload(serial: str, peer_serial: str) -> dict:
    """Body for PUT /fabrics/{f}/switches/{serial}/vpcPair with ND's default pairing template (no vpcPairDetails):
    ND picks the domain id, the keep-alive over mgmt0 and the peer-link port-channel from the discovered leaf link."""
    return {"vpcAction": "pair", "switchId": serial, "peerSwitchId": peer_serial, "useVirtualPeerLink": False}


def tor_associate_payload(tor_serial: str, leaf_serial: str, peer_serial: str, resources: dict) -> list[dict]:
    """Body for POST /fabrics/{f}/accessAssociationActions/associate (a list; one ToR to one leaf vPC pair).
    `resources` is the port-channel / vPC id block ND itself recommends in GET accessAssociations?includeCandidates=true
    for this ToR; passing it back verbatim keeps the ids clear of the peer-link port-channel500 and of anything
    already allocated on the leafs."""
    return [{"accessOrTorSwitchId": tor_serial, "aggregationOrLeafSwitchId": leaf_serial, "aggregationOrLeafPeerSwitchId": peer_serial, "resources": resources}]


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
                # `mode: managed` is the configData discriminator ND 4.3.1 validates (4.2.1 accepted the payload without it).
                "configData": {
                    "mode": "managed",
                    "networkOS": {
                        "networkOSType": "ios-xe",
                        "policy": {"policyType": "iosXeLoopback", "adminState": True, "ip": loopback["ip"], "description": loopback.get("description", "")},
                    },
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

    def _post(self, path: str, body: Any, timeout: int | None = None) -> Any:
        self._log(f"POST {path} {json.dumps(redact(body))[:LOG_BODY_LIMIT]}")
        return None if self.dry_run else self.client.post(path, json=body, timeout=timeout)

    def _put(self, path: str, body: Any) -> Any:
        self._log(f"PUT {path} {json.dumps(redact(body))[:LOG_BODY_LIMIT]}")
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

    def _query(self, path: str, key: str, body: Any) -> list:
        """POST to one of ND's `/query` endpoints (e.g. `/fabrics/{f}/vrfAttachments/query`). Despite the POST
        verb these are reads -- ND returns query results via POST because the request carries a `switchIds`
        body, not because it writes anything -- so unlike `_post` this always runs (even under --dry-run,
        since it never mutates state) and is not itself dry-run-logged. An HTTP error (e.g. no attachments
        exist yet) reads as empty, same as `_read`."""
        try:
            body_resp = self.client.post(path, json=body) or {}
        except RuntimeError as exc:
            self._log(f"read {path} failed ({str(exc)[:80]}); treating as empty")
            return []
        return body_resp.get(key, []) if isinstance(body_resp, dict) else body_resp

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

    def _pending_counts(self, fabric_name: str) -> dict[str, int]:
        """hostname -> pending line count for every switch in the fabric (404-tolerant; used for the redeploy check)."""
        counts = {}
        for hostname, entry in self.fabric_switches(fabric_name).items():
            counts[hostname] = len(self._read(f"/fabrics/{fabric_name}/switches/{entry['serialNumber']}/pendingConfig", "pendingConfigs"))
        return counts

    def _deploy_failures(self, fabric_name: str, since: str) -> list[str]:
        """First failed CLI command per switch from deploymentHistory records started at/after `since` (ISO-8601 UTC)."""
        failures = []
        for rec in self._read(f"/fabrics/{fabric_name}/deploymentHistory", "deploymentRecords"):
            if (rec.get("startTimestamp") or "") < since or rec.get("status") == "success":
                continue
            for cmd in rec.get("configCommandResponses", []):
                if cmd.get("status") == "failed":
                    failures.append(f"{rec.get('hostname')}: {cmd.get('command', '').strip()!r} -> {(cmd.get('cliResponse') or '')[:120]}")
                    break
        return failures

    def config_deploy(self, fabric_name: str) -> None:
        """The GUI's "Recalculate and Deploy": configSave (recalculate intent from the fabric settings + policies)
        followed by deploy (push pending config). Both are synchronous and can run for minutes. The older
        actions/configDeploy is deprecated on 4.3.1 and, as observed there, never generated the underlay intent.

        ND quirk (seen on 4.3.1 with API-added switches; the user has seen it on 4.2.1 with POAP/discovery adds,
        never with GUI-added switches): the first deploy after a Recalculate can run against the switch's stale
        expected config (the import-time defaults), emit `no vlan 1` and abort the whole switch; the next deploy
        uses the fresh intent and succeeds. So after deploying, if anything is still pending, report the failed
        commands and deploy once more."""
        self._post(f"/fabrics/{fabric_name}/actions/configSave", None, timeout=FABRIC_ACTION_TIMEOUT)
        started = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        self._post(f"/fabrics/{fabric_name}/actions/deploy", None, timeout=FABRIC_ACTION_TIMEOUT)
        if self.dry_run:
            return
        time.sleep(self.settle_seconds)
        left = {h: n for h, n in self._pending_counts(fabric_name).items() if n}
        if not left:
            return
        self._log(f"{fabric_name}: still pending after deploy {left}")
        for line in self._deploy_failures(fabric_name, started):
            self._log(f"{fabric_name}: deploy failure {line}")
        self._log(f"{fabric_name}: deploying once more (the first deploy after a Recalculate can use a stale expected config for API/POAP-added switches)")
        self._post(f"/fabrics/{fabric_name}/actions/deploy", None, timeout=FABRIC_ACTION_TIMEOUT)
        time.sleep(self.settle_seconds)
        left = {h: n for h, n in self._pending_counts(fabric_name).items() if n}
        if left:
            self._log(f"{fabric_name}: still pending after the second deploy {left} -- read /fabrics/{fabric_name}/deploymentHistory")

    def pending(self, fabric_name: str, serial: str) -> list:
        """Final convergence check: fails loud (does not swallow HTTP errors like `_read`) since a request
        error here must stop `deploy`/`isn`/`overlay` from reporting false convergence. The endpoint answers
        `{"pendingConfigs": [<cli line>, ...]}` (both 4.2.1 and 4.3.1 specs); an empty list means in sync."""
        body = self.client.get(f"/fabrics/{fabric_name}/switches/{serial}/pendingConfig") or {}
        return body.get("pendingConfigs", []) if isinstance(body, dict) else body

    def discover(self, fabric: Fabric, password: str) -> dict[str, dict]:
        """shallowDiscovery for fabric.switches: ND logs into each seed IP and returns serial/model/version plus a
        status. Nothing changes on ND, but the switches must be up, so a dry run only logs the call and returns
        placeholders. Returns ip -> entry for the switches ND reports as `manageable`; others are logged and skipped."""
        body = discovery_payload(fabric, password)
        self._log(f"POST /fabrics/{fabric.name}/actions/shallowDiscovery {json.dumps(redact(body))[:LOG_BODY_LIMIT]}")
        if self.dry_run:
            return {s.ip: {"serialNumber": DISCOVERY_PLACEHOLDER, "model": DISCOVERY_PLACEHOLDER} for s in fabric.switches}
        result = self.client.post(f"/fabrics/{fabric.name}/actions/shallowDiscovery", json=body) or {}
        found: dict[str, dict] = {}
        for entry in result.get("switches", []):
            status = entry.get("status")
            if status == "manageable":
                found[entry["ip"]] = entry
            else:
                self._log(f"discovery: {entry.get('ip')} ({entry.get('hostname') or '?'}) is {status}: {entry.get('statusReason', '')} -- not added")
        for switch in fabric.switches:
            if switch.ip not in found and switch.ip not in {e.get("ip") for e in result.get("switches", [])}:
                self._log(f"discovery: {switch.hostname} ({switch.ip}) missing from the shallowDiscovery response -- not added")
        return found

    def phase_switches(self) -> None:
        for fabric in self.topo.fabrics:
            present = self.fabric_switches(fabric.name)
            missing = [s for s in fabric.switches if s.hostname not in present]
            if missing:
                password = _switch_password(fabric)
                to_discover = Fabric(fabric.name, fabric.type, fabric.asn, {}, missing)
                discovered = self.discover(to_discover, password)
                to_add = [s for s in missing if s.ip in discovered]
                if to_add:
                    self._post(f"/fabrics/{fabric.name}/switches", switch_add_payload(Fabric(fabric.name, fabric.type, fabric.asn, {}, to_add), discovered, password))
                    if not self.dry_run:
                        self.wait_for_switches(fabric.name, [s.hostname for s in to_add])
                        present = self.fabric_switches(fabric.name)
            wrong = [
                {"switchId": present[s.hostname]["serialNumber"], "role": s.role}
                for s in fabric.switches
                if s.hostname in present and present[s.hostname].get("switchRole") != s.role
            ]
            if wrong:
                self._post(f"/fabrics/{fabric.name}/switchActions/changeRoles", {"switchRoles": wrong})
            self.config_deploy(fabric.name)

    # -- phase: vpc ------------------------------------------------------------------------------------------
    def phase_vpc(self) -> None:
        """Create the vPC pairs of the topology (skipping pairs ND already lists, in either switch order), then
        recalculate + deploy every fabric that gained a pair so ND generates the vpc domain and peer-link config."""
        touched: list[str] = []
        for fabric_name in sorted({pair.fabric for pair in self.topo.vpc_pairs}):
            existing = {frozenset((p.get("switchId"), p.get("peerSwitchId"))) for p in self._read(f"/fabrics/{fabric_name}/vpcPairs", "vpcPairs")}
            for pair in [p for p in self.topo.vpc_pairs if p.fabric == fabric_name]:
                serial, peer_serial = self.serial(pair.switch), self.serial(pair.peer)
                if frozenset((serial, peer_serial)) in existing:
                    self._log(f"{fabric_name}: {pair.switch} <-> {pair.peer} already paired")
                    continue
                self._put(f"/fabrics/{fabric_name}/switches/{serial}/vpcPair", vpc_pair_payload(serial, peer_serial))
                if fabric_name not in touched:
                    touched.append(fabric_name)
        for fabric_name in touched:
            self.config_deploy(fabric_name)

    # -- phase: tor ------------------------------------------------------------------------------------------
    TOR_RESOURCE_PLACEHOLDER = "<nd-recommended>"

    def _tor_associations(self, fabric: str, leaf: str, peer: str, candidates: bool = False) -> list[dict]:
        """GET accessAssociations for one leaf vPC pair. ND answers 400 without aggregationOrLeafSwitchId. Without
        includeCandidates the ToR still shows up as a recommendation record (isRecommended, empty `resources`);
        a real association is the record whose `resources` carries port-channel ids. With includeCandidates
        ND fills `resources` with the ids it would allocate and `remarks` with why it would not."""
        params = {"aggregationOrLeafSwitchId": leaf, "aggregationOrLeafPeerSwitchId": peer}
        if candidates:
            params["includeCandidates"] = "true"
        return self._read(f"/fabrics/{fabric}/accessAssociations", "associations", params=params)

    def phase_tor(self) -> None:
        """ND ToR pairing: associate each ToR under `tor_pairs:` with its leaf vPC pair (ND creates the uplink
        port-channel on the ToR and a ToR-owned vPC on both leafs), then recalculate + deploy every fabric that
        gained an association. Every Recalculate on a fabric with an unpaired ToR raises the
        "No leaf-tor pairing is found for the tor" anomaly on 4.2.1 (4.3.1 hides it)."""
        touched: list[str] = []
        for pair in self.topo.tor_pairs:
            label = f"{pair.tor} -> {pair.leaf}/{pair.peer}"
            tor, leaf, peer = self.serial(pair.tor), self.serial(pair.leaf), self.serial(pair.peer)
            existing = [a for a in self._tor_associations(pair.fabric, leaf, peer) if a.get("accessOrTorSwitchId") == tor and a.get("resources")]
            if existing:
                self._log(f"{pair.fabric}: {pair.tor} already paired with {pair.leaf}/{pair.peer} {json.dumps(existing[0].get('resources'))}")
                continue
            candidate = next((c for c in self._tor_associations(pair.fabric, leaf, peer, candidates=True) if c.get("accessOrTorSwitchId") == tor), {})
            resources = candidate.get("resources") or {}
            if not (resources.get("accessOrTorPortChannelId") and resources.get("aggregationOrLeafPortChannelId")):
                if not self.dry_run:
                    raise RuntimeError(
                        f"{pair.fabric}: {label}: ND recommends no port-channel ids (remarks: {candidate.get('remarks', '') or 'ToR not listed as a candidate'!r});"
                        " the ToR must be discovered and its uplinks cabled to both leafs before pairing"
                    )
                resources = {key: self.TOR_RESOURCE_PLACEHOLDER for key in ("accessOrTorPortChannelId", "aggregationOrLeafPortChannelId")}
            result = self._post(f"/fabrics/{pair.fabric}/accessAssociationActions/associate", tor_associate_payload(tor, leaf, peer, resources))
            for item in (result or {}).get("associations", []):
                if item.get("status") == "failed":
                    raise RuntimeError(f"{pair.fabric}: {label}: association failed: {item.get('message') or 'no message'}")
                self._log(f"{pair.fabric}: {label}: {item.get('message') or item.get('status')}")
            if pair.fabric not in touched:
                touched.append(pair.fabric)
        for fabric_name in touched:
            self.config_deploy(fabric_name)

    # -- phase: isn ------------------------------------------------------------------------------------------
    def _policies(self, fabric: str, serial: str) -> list[dict]:
        """Policies of one switch. ND 4.3.1 ignores the switchId query parameter (returns the whole fabric), so
        filter client-side as well; the parameter is kept for 4.2.1 where it works."""
        return [p for p in self._read_paged(f"/fabrics/{fabric}/policies", "policies", params={"switchId": serial}) if p.get("switchId", serial) == serial]

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
        dst_fabrics = sorted({item.dst_fabric for item in self.topo.isn.links} - ({wan.fabric} if wan else set()))
        for name in ([wan.fabric] if wan else []) + dst_fabrics:
            self.config_deploy(name)
        if wan and not self.dry_run:
            time.sleep(self.settle_seconds)
            assert wan_serial is not None
            left = self.pending(wan.fabric, wan_serial)
            print(f"{wan.hostname} pendingConfig after deploy: {len(left)} line(s)" + ("" if not left else " -- read /deploymentHistory"))

    def _ensure_access_port(self, fabric: str, serial: str, interface: str, description: str) -> None:
        """ND refuses an access-mode attachment on a port whose intent is trunk ("has mode 'trunk' on switch but
        payload specifies 'access'"), and every unused leaf port defaults to trunkHost. Put the port in access mode
        (accessHost policy) first; the attachment then supplies the access VLAN."""
        current = self._read_one(f"/fabrics/{fabric}/switches/{serial}/interfaces/{interface.replace('/', '%2F')}")
        if (current.get("configData") or {}).get("mode") == "access":
            return
        body = {
            "switchId": serial,
            "interfaceName": interface,
            "interfaceType": "ethernet",
            "configData": {
                "mode": "access",
                "networkOS": {
                    "networkOSType": "nx-os",
                    "policy": {
                        "policyType": "accessHost",
                        "adminState": True,
                        "mtu": "jumbo",
                        "speed": "auto",
                        "bpduGuard": "default",
                        "portTypeEdgeTrunk": True,
                        "description": description,
                    },
                },
            },
        }
        self._put(f"/fabrics/{fabric}/switches/{serial}/interfaces/{interface.replace('/', '%2F')}", body)

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
        vrf_fabrics = sorted({att["fabric"] for att in self.topo.overlay.vrf_attachments})
        vrf_attached: dict[str, set[tuple[str, str]]] = {}
        for fabric in vrf_fabrics:
            vrf_serials = sorted({self.serial(att["switch"]) for att in self.topo.overlay.vrf_attachments if att["fabric"] == fabric})
            vrf_query = self._query(f"/fabrics/{fabric}/vrfAttachments/query", "attachments", {"switchIds": vrf_serials})
            vrf_attached[fabric] = {(a["vrfName"], a["switchId"]) for a in vrf_query if a.get("attach")}

        net_fabrics = sorted({att["fabric"] for att in self.topo.overlay.network_attachments})
        net_attached: dict[str, set[tuple[str, str]]] = {}
        for fabric in net_fabrics:
            net_serials = sorted({self.serial(att["switch"]) for att in self.topo.overlay.network_attachments if att["fabric"] == fabric})
            net_query = self._query(f"/fabrics/{fabric}/networkAttachments/query", "attachments", {"switchIds": net_serials})
            net_attached[fabric] = {(a["networkName"], a["switchId"]) for a in net_query if a.get("attach")}

        touched_vrf: dict[str, set[str]] = {}
        for att in self.topo.overlay.vrf_attachments:
            serial = self.serial(att["switch"])
            if (att["vrf"], serial) in vrf_attached.get(att["fabric"], set()):
                continue
            self._post(f"/fabrics/{att['fabric']}/vrfAttachments", attachment_payload("vrf", att, serial))
            touched_vrf.setdefault(att["fabric"], set()).add(serial)

        touched_net: dict[str, set[str]] = {}
        for att in self.topo.overlay.network_attachments:
            serial = self.serial(att["switch"])
            if (att["network"], serial) in net_attached.get(att["fabric"], set()):
                continue
            for intf in att.get("interfaces", []):
                if intf.get("mode") == "access":
                    self._ensure_access_port(att["fabric"], serial, intf["interfaceRange"], f"{att['network']} host port")
            self._post(f"/fabrics/{att['fabric']}/networkAttachments", attachment_payload("network", att, serial))
            touched_net.setdefault(att["fabric"], set()).add(serial)

        for fabric, touched_serials in touched_vrf.items():
            names = sorted({att["vrf"] for att in self.topo.overlay.vrf_attachments if att["fabric"] == fabric})
            self._post(f"/fabrics/{fabric}/vrfActions/deploy", {"vrfNames": names, "switchIds": sorted(touched_serials)})
        for fabric, touched_serials in touched_net.items():
            names = sorted({att["network"] for att in self.topo.overlay.network_attachments if att["fabric"] == fabric})
            self._post(f"/fabrics/{fabric}/networkActions/deploy", {"networkNames": names, "switchIds": sorted(touched_serials)})

    # -- phase: deploy -----------------------------------------------------------------------------------------
    def phase_deploy(self) -> None:
        """Recalculate + deploy every fabric, then every fabric group (child fabrics before the MSD, as the docs
        require: the group deploy generates the multisite underlay/overlay links and BG policies)."""
        for fabric in self.topo.fabrics:
            self.config_deploy(fabric.name)
        for group in self.topo.fabric_groups:
            self.config_deploy(group.name)
        if self.dry_run:
            return
        time.sleep(self.settle_seconds)
        for fabric in self.topo.fabrics:
            for hostname, entry in self.fabric_switches(fabric.name).items():
                left = self.pending(fabric.name, entry["serialNumber"])
                print(f"{fabric.name}/{hostname}: pendingConfig {len(left)} line(s)")
                for line in left:
                    print(f"    {line}")

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
