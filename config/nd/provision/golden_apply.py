#!/usr/bin/env python3
"""Golden drift: execute the chosen `Op` records against the controller, then recalculate and deploy what was touched."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import unquote

import requests

from golden_drift import Op
from provision import LOG_BODY_LIMIT, Provisioner, redact
from topology import Topology

# Execution rank per action. Within a rank the input order is kept (the sort is stable), so an ordered delete sequence stays in order.
# Teardown runs before creation within each class; an overlay object is detached (and the detach deployed) before it is deleted, and networks
# go before the VRFs they sit in; vPC is paired before a ToR is associated to it and ToRs are unpaired before their vPC pair.
RANK = {
    "put_settings": 0,
    "add_switch": 1,
    "set_role": 2,
    "add_member": 3,
    "clear_link": 4,
    "put_link": 5,
    "delete_interface": 6,
    "reset_interface": 7,
    "put_interface": 8,
    "detach": 9,
    "deploy_overlay": 9,
    "delete_network": 10,
    "delete_vrf": 11,
    "create_vrf": 12,
    "create_network": 13,
    "attach": 14,
    "put_network_ir": 14,
    "unpair_tor": 15,
    "unpair_vpc": 16,
    "pair_vpc": 17,
    "pair_tor": 18,
    "deploy_owner": 19,
}
OVERLAY_RANK = RANK["detach"]  # the first rank that touches overlay objects; a member add is deployed before it


# networkActions/deploy only starts the detach (HTTP 202); until ND has finished it, the port PUT is still refused with the same
# "Policy type change ... is not allowed" (lab, ND 4.2.1, 2026-11-13: refused right after the deploy call, accepted a few minutes later)
TYPE_CHANGE_TRIES = 12
TYPE_CHANGE_WAIT = 10


class ApplyError(RuntimeError):
    """An op failed (HTTP error or a failed item in a 207 response); nothing after it was sent."""


def _failed_items(resp: Any) -> list[dict]:
    """Entries of the top-level `results` / `items` / `associations` lists whose string `status` is not "success" (networkAttachments answer
    `results`, changeRoles `items`, accessAssociationActions associate/disassociate `associations`). A top-level `status` (a message string such
    as "No switches pending for deployment.") and an empty body are never failures."""
    if not isinstance(resp, dict):
        return []
    found: list[dict] = []
    for key in ("results", "items", "associations"):
        value = resp.get(key)
        if isinstance(value, list):
            found.extend(i for i in value if isinstance(i, dict) and isinstance(i.get("status"), str) and i["status"] != "success")
    return found


class Applier:
    def __init__(self, prov: Provisioner, topo: Topology) -> None:
        self.prov = prov
        self.topo = topo

    # -- transport -----------------------------------------------------------------------------------------
    def _delete(self, path: str) -> Any:
        self.prov._log(f"DELETE {path}")
        return None if self.prov.dry_run else self.prov.client.delete(path)

    def _check(self, op: Op, resp: Any) -> None:
        failed = _failed_items(resp)
        if failed:
            item = failed[0]
            message = item.get("message") or item.get("error") or json.dumps(redact(item))[:LOG_BODY_LIMIT]
            raise ApplyError(f"{op.action} {op.method} {op.path}: item status {item.get('status')!r}: {message}")

    def _send(self, op: Op) -> Any:
        if op.method == "PUT":
            resp = self.prov._put(op.path, op.body)
        elif op.method == "POST":
            resp = self.prov._post(op.path, op.body)
        elif op.method == "DELETE":
            resp = self._delete(op.path)
        else:
            raise ApplyError(f"{op.action}: unsupported method {op.method!r}")
        self._check(op, resp)
        return resp

    # -- apply ---------------------------------------------------------------------------------------------
    def apply(self, ops: list[Op]) -> set[str]:
        touched: set[str] = set()
        unknown = sorted({o.action for o in ops if o.action not in RANK})
        if unknown:
            raise ApplyError(f"unknown action(s) {unknown}; nothing was sent")
        ordered = sorted(ops, key=lambda o: RANK[o.action])
        switches_added = False
        groups_to_deploy = [o.fabric for o in ordered if o.action == "add_member"]
        for op in ordered:
            if groups_to_deploy and RANK[op.action] >= OVERLAY_RANK:
                self._deploy_membership(groups_to_deploy)
                groups_to_deploy = []
            touched.add(op.fabric)
            if op.action == "deploy_owner":
                continue
            if op.action == "add_switch":
                if not switches_added:
                    self._run(op, self._phase_switches)
                    switches_added = True
                continue
            if op.action in ("put_interface", "reset_interface"):  # both PUT a port policy; ND refuses a policy-type change under a network
                self._put_interface(op)
                continue
            self._run(op, lambda op=op: self._send(op))
        return touched

    def _deploy_membership(self, groups: list[str]) -> None:
        """ND refuses a network attachment on a border gateway until the group deploy has generated the multisite links: deploy the member
        fabrics that declare replication modes, then each group a member was added to, before any overlay op."""
        names = set(groups)
        members = {m for g in self.topo.fabric_groups if g.name in names for m in g.members}
        for fabric in (f for f in self.topo.mode_fabrics if f in members):
            self.prov.config_deploy(fabric)
        for group in dict.fromkeys(groups):
            self.prov.config_deploy(group)

    def _run(self, op: Op, call: Any) -> Any:
        try:
            return call()
        except ApplyError:
            raise
        except (RuntimeError, ValueError, TimeoutError, requests.RequestException, OSError) as exc:  # HTTP error, connection drop, read timeout
            raise ApplyError(f"{op.action} {op.method} {op.path}: {exc}") from exc

    def _phase_switches(self) -> None:
        """Provisioner.phase_switches exits (SystemExit) when NXOS_PASSWORD/IOSXE_PASSWORD is unset; report that as a failed op."""
        try:
            self.prov.phase_switches()
        except SystemExit as exc:
            raise ApplyError(f"add_switch: {exc}") from exc

    # -- interface policy-type change ----------------------------------------------------------------------
    def _put_interface(self, op: Op) -> None:
        try:
            self._run(op, lambda: self._send(op))
            return
        except ApplyError as exc:
            if "Policy type change" not in str(exc):
                raise
        rows = self._attached_on_port(op)
        serial, port = self._serial_and_port(op)
        if not rows:
            raise ApplyError(f"{op.action} {op.method} {op.path}: policy type change refused and no network is attached on {port}")
        names = sorted({r["networkName"] for r in rows})
        deploy = {"networkNames": names, "switchIds": [serial]}
        attach_path = f"/fabrics/{op.fabric}/networkAttachments"
        deploy_path = f"/fabrics/{op.fabric}/networkActions/deploy"
        self.prov._log(f"{port}: policy type change refused; detaching {names} from the port, retrying, then re-attaching")
        detach = [{"networkName": r["networkName"], "switchId": r["switchId"], "vlanId": r.get("vlanId"), "interfaces": [], "attach": False} for r in rows]
        reattach = [{**d, "interfaces": r.get("interfaces") or [], "attach": True} for d, r in zip(detach, rows)]
        self._run(op, lambda: self._check_post(op, attach_path, {"attachments": detach}))
        try:
            self._run(op, lambda: self._check_post(op, deploy_path, deploy))
            self._send_once_detached(op, port)
        except ApplyError as exc:
            try:
                self._run(op, lambda: self._check_post(op, attach_path, {"attachments": reattach}))
                self._run(op, lambda: self._check_post(op, deploy_path, deploy))
                outcome = "re-attached"
            except ApplyError as again:
                outcome = f"re-attach FAILED ({again})"
            raise ApplyError(f"{exc}; networks {names} were detached from {port} and {outcome}") from exc
        if op.action == "reset_interface":
            # a free port's golden state has no network on it; the attachment fix later in this apply sets the golden attachment
            self.prov._log(f"{port}: networks {names} stay detached; the port is being reset to its role default")
            return
        self._run(op, lambda: self._check_post(op, attach_path, {"attachments": reattach}))
        self._run(op, lambda: self._check_post(op, deploy_path, deploy))

    def _send_once_detached(self, op: Op, port: str) -> None:
        """Send the port PUT, waiting out ND's asynchronous detach: retry while the answer is still the policy-type-change refusal."""
        for attempt in range(1, TYPE_CHANGE_TRIES + 1):
            try:
                self._run(op, lambda: self._send(op))
                return
            except ApplyError as exc:
                if "Policy type change" not in str(exc) or attempt == TYPE_CHANGE_TRIES or self.prov.dry_run:
                    raise
            self.prov._log(f"{port}: still refused, the detach is not finished; retry {attempt}/{TYPE_CHANGE_TRIES - 1} in {TYPE_CHANGE_WAIT}s")
            time.sleep(TYPE_CHANGE_WAIT)

    def _check_post(self, op: Op, path: str, body: Any) -> None:
        self._check(Op(op.action, op.fabric, "POST", path, body), self.prov._post(path, body))

    @staticmethod
    def _serial_and_port(op: Op) -> tuple[str, str]:
        parts = op.path.split("/")  # "", fabrics, F, switches, SERIAL, interfaces, PORT
        return parts[4], unquote(parts[6])

    def _attached_on_port(self, op: Op) -> list[dict]:
        serial, port = self._serial_and_port(op)
        rows = self.prov._query(f"/fabrics/{op.fabric}/networkAttachments/query", "attachments", {"switchIds": [serial]})
        return [r for r in rows if r.get("switchId", serial) == serial and any(i.get("interfaceRange") == port for i in r.get("interfaces") or [])]

    # -- deploy --------------------------------------------------------------------------------------------
    def deploy(self, touched: set[str], topo: Topology) -> None:
        for fabric in topo.fabrics:
            if fabric.name in touched:
                self.prov.config_deploy(fabric.name)
        for group in topo.fabric_groups:
            if group.name in touched:
                self.prov.config_deploy(group.name)
