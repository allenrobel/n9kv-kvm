#!/usr/bin/env python3
"""Golden drift: execute the chosen `Op` records against the controller, then recalculate and deploy what was touched."""

from __future__ import annotations

import json
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
    "clear_link": 3,
    "put_link": 4,
    "delete_interface": 5,
    "reset_interface": 6,
    "put_interface": 7,
    "detach": 8,
    "deploy_overlay": 8,
    "delete_network": 9,
    "delete_vrf": 10,
    "create_vrf": 11,
    "create_network": 12,
    "attach": 13,
    "unpair_tor": 14,
    "unpair_vpc": 15,
    "pair_vpc": 16,
    "pair_tor": 17,
    "deploy_owner": 18,
}


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
    def __init__(self, prov: Provisioner) -> None:
        self.prov = prov

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
        for op in ordered:
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
            self._run(op, lambda: self._send(op))
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
