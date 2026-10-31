"""Tests for the golden drift Applier against a stub NDClient."""

import pytest
import requests

import provision
from golden_apply import ApplyError, Applier
from golden_drift import Op
from provision import Provisioner
from tests.test_provision_phases import StubClient, _topo


@pytest.fixture(autouse=True)
def _no_settle_sleep(monkeypatch):
    monkeypatch.setattr(provision.time, "sleep", lambda _seconds: None)


class Stub(StubClient):
    """StubClient plus delete(), scripted per-call outcomes for POST/PUT, and a `writes` view (no reads)."""

    def __init__(self, responses=None, post_results=None, put_errors=None):
        super().__init__(responses)
        self.post_results = post_results or {}
        self.put_errors = list(put_errors or [])

    def post(self, path, json=None, timeout=None):
        self.calls.append(("POST", path, json))
        return self.post_results.get(path, self.responses.get(path))

    def put(self, path, json=None):
        self.calls.append(("PUT", path, json))
        if self.put_errors:
            raise self.put_errors.pop(0)
        return None

    def delete(self, path):
        self.calls.append(("DELETE", path, None))
        return None

    @property
    def writes(self):
        return [c for c in self.calls if c[0] in ("PUT", "DELETE") or (c[0] == "POST" and not c[1].endswith("/query"))]


def _applier(client, dry_run=False):
    return Applier(Provisioner(client, _topo(), dry_run=dry_run))


def test_apply_runs_ops_in_class_order_and_returns_touched():
    client = Stub()
    ops = [
        Op("pair_vpc", "SITE1", "PUT", "/fabrics/SITE1/switches/S1/vpcPair", {"a": 1}),
        Op("attach", "SITE1", "POST", "/fabrics/SITE1/networkAttachments", {"attachments": []}),
        Op("create_network", "SITE1", "POST", "/fabrics/SITE1/networks", {"networks": []}),
        Op("create_vrf", "SITE1", "POST", "/fabrics/SITE1/vrfs", {"vrfs": []}),
        Op("delete_network", "SITE2", "DELETE", "/fabrics/SITE2/networks/N", None),
        Op("detach", "SITE2", "POST", "/fabrics/SITE2/networkAttachments", {"attachments": []}),
        Op("put_interface", "SITE1", "PUT", "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5", {"i": 1}),
        Op("put_link", "SITE1", "PUT", "/links/1", {"l": 1}),
        Op("put_settings", "SITE1", "PUT", "/fabrics/SITE1", {"s": 1}),
        Op("deploy_owner", "MSD", "", "", None),
    ]
    touched = _applier(client).apply(ops)
    assert touched == {"SITE1", "SITE2", "MSD"}
    assert [(c[0], c[1]) for c in client.writes] == [
        ("PUT", "/fabrics/SITE1"),
        ("PUT", "/links/1"),
        ("PUT", "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5"),
        ("POST", "/fabrics/SITE2/networkAttachments"),
        ("DELETE", "/fabrics/SITE2/networks/N"),
        ("POST", "/fabrics/SITE1/vrfs"),
        ("POST", "/fabrics/SITE1/networks"),
        ("POST", "/fabrics/SITE1/networkAttachments"),
        ("PUT", "/fabrics/SITE1/switches/S1/vpcPair"),
    ]


def test_apply_stops_at_first_failure_with_apply_error():
    bad = {"results": [{"status": "success"}, {"status": "failed", "message": "vlan in use"}]}
    client = Stub(post_results={"/fabrics/SITE1/networkAttachments": bad})
    ops = [
        Op("attach", "SITE1", "POST", "/fabrics/SITE1/networkAttachments", {"attachments": []}),
        Op("pair_vpc", "SITE1", "PUT", "/fabrics/SITE1/switches/S1/vpcPair", {}),
    ]
    with pytest.raises(ApplyError, match="attach.*vlan in use"):
        _applier(client).apply(ops)
    assert [c[1] for c in client.writes] == ["/fabrics/SITE1/networkAttachments"]


def test_put_interface_retries_through_detach_on_policy_type_refusal():
    port = "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5"
    rows = [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "attach": True, "interfaces": [{"interfaceRange": "Ethernet1/5", "mode": "access"}]}]
    other = {"networkName": "N2", "switchId": "S1", "vlanId": 20, "attach": True, "interfaces": [{"interfaceRange": "Ethernet1/6", "mode": "access"}]}
    client = Stub(
        post_results={"/fabrics/SITE1/networkAttachments/query": {"attachments": rows + [other]}},
        put_errors=[RuntimeError("HTTP 400 Policy type change from a to b is not allowed")],
    )
    _applier(client).apply([Op("put_interface", "SITE1", "PUT", port, {"i": 1})])
    seq = [(c[0], c[1]) for c in client.calls]
    assert seq == [
        ("PUT", port),
        ("POST", "/fabrics/SITE1/networkAttachments/query"),
        ("POST", "/fabrics/SITE1/networkAttachments"),
        ("POST", "/fabrics/SITE1/networkActions/deploy"),
        ("PUT", port),
        ("POST", "/fabrics/SITE1/networkAttachments"),
        ("POST", "/fabrics/SITE1/networkActions/deploy"),
    ]
    posts = [c[2] for c in client.calls if c[0] == "POST"]
    assert posts[1] == {"attachments": [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "interfaces": [], "attach": False}]}
    assert posts[2] == {"networkNames": ["N1"], "switchIds": ["S1"]}
    assert posts[3] == {"attachments": [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "interfaces": rows[0]["interfaces"], "attach": True}]}


def test_deploy_orders_members_before_groups():
    client = Stub()
    topo = _topo()
    _applier(client).deploy({"MSD", "SITE1"}, topo)
    saves = [c[1] for c in client.calls if c[0] == "POST" and c[1].endswith("/configSave")]
    assert saves == ["/fabrics/SITE1/actions/configSave", "/fabrics/MSD/actions/configSave"]


def test_dry_run_writes_nothing():
    client = Stub()
    ops = [
        Op("put_settings", "SITE1", "PUT", "/fabrics/SITE1", {"s": 1}),
        Op("attach", "SITE1", "POST", "/fabrics/SITE1/networkAttachments", {"attachments": []}),
        Op("delete_network", "SITE1", "DELETE", "/fabrics/SITE1/networks/N", None),
    ]
    applier = _applier(client, dry_run=True)
    touched = applier.apply(ops)
    applier.deploy(touched, _topo())
    assert client.writes == []


def test_unknown_action_is_rejected_before_anything_is_sent():
    client = Stub()
    ops = [Op("put_settings", "SITE1", "PUT", "/fabrics/SITE1", {}), Op("bogus", "SITE1", "PUT", "/x", {})]
    with pytest.raises(ApplyError, match="bogus"):
        _applier(client).apply(ops)
    assert client.calls == []


def test_failed_retry_reattaches_and_names_the_networks():
    port = "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5"
    rows = [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "attach": True, "interfaces": [{"interfaceRange": "Ethernet1/5", "mode": "access"}]}]
    client = Stub(
        post_results={"/fabrics/SITE1/networkAttachments/query": {"attachments": rows}},
        put_errors=[RuntimeError("HTTP 400 Policy type change x"), RuntimeError("HTTP 500 boom")],
    )
    with pytest.raises(ApplyError, match=r"N1.*Ethernet1/5.*re-attached"):
        _applier(client).apply([Op("put_interface", "SITE1", "PUT", port, {"i": 1})])
    assert [(c[0], c[1]) for c in client.calls[-3:]] == [
        ("PUT", port),
        ("POST", "/fabrics/SITE1/networkAttachments"),
        ("POST", "/fabrics/SITE1/networkActions/deploy"),
    ]
    assert client.calls[-2][2]["attachments"][0]["attach"] is True


def test_put_207_failed_item_raises():
    class PutStub(Stub):
        def put(self, path, json=None):
            self.calls.append(("PUT", path, json))
            return {"results": [{"status": "failed", "message": "x"}]}

    client = PutStub()
    ops = [Op("put_settings", "SITE1", "PUT", "/fabrics/SITE1", {}), Op("pair_vpc", "SITE1", "PUT", "/fabrics/SITE1/switches/S1/vpcPair", {})]
    with pytest.raises(ApplyError, match="x"):
        _applier(client).apply(ops)
    assert [c[1] for c in client.writes] == ["/fabrics/SITE1"]


def test_top_level_status_string_is_not_a_failure():
    client = Stub(post_results={"/fabrics/SITE1/networkActions/deploy": {"status": "No switches pending for deployment."}})
    ops = [Op("deploy_overlay", "SITE1", "POST", "/fabrics/SITE1/networkActions/deploy", {}), Op("put_settings", "SITE1", "PUT", "/fabrics/SITE1", {})]
    _applier(client).apply(ops)
    assert len(client.writes) == 2


@pytest.mark.parametrize("action,path", [("pair_tor", "associate"), ("unpair_tor", "disassociate")])
def test_failed_tor_association_item_stops_the_apply(action, path):
    url = f"/fabrics/SITE1/accessAssociationActions/{path}"
    bad = {"associations": [{"accessOrTorSwitchId": "T", "aggregationOrLeafSwitchId": "L", "aggregationOrLeafPeerSwitchId": "P", "status": "failed", "message": "x"}]}
    client = Stub(post_results={url: bad})
    ops = [Op(action, "SITE1", "POST", url, [{}]), Op(action, "SITE2", "POST", url.replace("SITE1", "SITE2"), [{}])]
    with pytest.raises(ApplyError, match=f"{action}.*'failed'.*x"):
        _applier(client).apply(ops)
    assert [c[1] for c in client.writes] == [url]


def test_reset_interface_retries_through_detach_on_policy_type_refusal():
    """A free port carrying a network attachment (test residue) is reset to its role default through the same detach / retry / re-attach path."""
    port = "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5"
    rows = [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "attach": True, "interfaces": [{"interfaceRange": "Ethernet1/5", "mode": "access"}]}]
    client = Stub(
        post_results={"/fabrics/SITE1/networkAttachments/query": {"attachments": rows}},
        put_errors=[RuntimeError("HTTP 400 Policy type change from accessHost to trunkHost is not allowed")],
    )
    _applier(client).apply([Op("reset_interface", "SITE1", "PUT", port, {"i": 1})])
    assert [(c[0], c[1]) for c in client.calls] == [
        ("PUT", port),
        ("POST", "/fabrics/SITE1/networkAttachments/query"),
        ("POST", "/fabrics/SITE1/networkAttachments"),
        ("POST", "/fabrics/SITE1/networkActions/deploy"),
        ("PUT", port),
        ("POST", "/fabrics/SITE1/networkAttachments"),
        ("POST", "/fabrics/SITE1/networkActions/deploy"),
    ]
    posts = [c[2] for c in client.calls if c[0] == "POST"]
    assert posts[1]["attachments"][0]["attach"] is False and posts[3]["attachments"][0]["attach"] is True


def test_transport_error_becomes_apply_error_and_stops_the_apply():
    client = Stub(put_errors=[requests.ConnectionError("connection aborted")])
    ops = [Op("put_settings", "SITE1", "PUT", "/fabrics/SITE1", {}), Op("put_link", "SITE1", "PUT", "/links/1", {})]
    with pytest.raises(ApplyError, match="put_settings PUT /fabrics/SITE1: connection aborted"):
        _applier(client).apply(ops)
    assert [c[1] for c in client.writes] == ["/fabrics/SITE1"]


def test_add_switch_missing_password_is_an_apply_error():
    client = Stub()
    applier = _applier(client)

    def phase_switches():
        raise SystemExit("NXOS_PASSWORD is not set; it is required to add NX-OS switches to fabric SITE1")

    applier.prov.phase_switches = phase_switches  # type: ignore[method-assign]
    ops = [Op("add_switch", "SITE1", "POST", "/fabrics/SITE1/switches", None), Op("put_link", "SITE1", "PUT", "/links/1", {})]
    with pytest.raises(ApplyError, match="add_switch: NXOS_PASSWORD is not set"):
        applier.apply(ops)
    assert client.writes == []
