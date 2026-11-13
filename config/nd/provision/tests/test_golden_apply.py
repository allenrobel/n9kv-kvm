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
    return Applier(Provisioner(client, _topo(), dry_run=dry_run), _topo())


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


def test_reset_interface_detaches_retries_and_leaves_the_network_detached():
    """A free port carrying a network attachment (test residue) is reset to its role default through the detach / retry path; the
    networks are not re-attached, since a free port's golden state has none (the attachment fix op sets the golden attachment)."""
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
    ]
    detach = [c[2] for c in client.calls if c[0] == "POST"][1]
    assert detach == {"attachments": [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "interfaces": [], "attach": False}]}


def test_failed_reset_retry_reattaches_and_raises():
    port = "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5"
    rows = [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "attach": True, "interfaces": [{"interfaceRange": "Ethernet1/5", "mode": "access"}]}]
    client = Stub(
        post_results={"/fabrics/SITE1/networkAttachments/query": {"attachments": rows}},
        put_errors=[RuntimeError("HTTP 400 Policy type change x"), RuntimeError("HTTP 500 boom")],
    )
    with pytest.raises(ApplyError, match=r"boom.*N1.*Ethernet1/5.*re-attached"):
        _applier(client).apply([Op("reset_interface", "SITE1", "PUT", port, {"i": 1})])
    assert [(c[0], c[1]) for c in client.calls[-3:]] == [
        ("PUT", port),
        ("POST", "/fabrics/SITE1/networkAttachments"),
        ("POST", "/fabrics/SITE1/networkActions/deploy"),
    ]
    assert client.calls[-2][2]["attachments"][0] == {**{k: rows[0][k] for k in ("networkName", "switchId", "vlanId", "interfaces")}, "attach": True}


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


def test_port_put_is_retried_while_the_detach_is_still_in_progress():
    """networkActions/deploy answers 202 before the detach is done; ND keeps refusing the policy-type change until then."""
    port = "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5"
    rows = [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "attach": True, "interfaces": [{"interfaceRange": "Ethernet1/5", "mode": "access"}]}]
    refusal = "HTTP 400 Policy type change from trunkHost to accessHost is not allowed"
    client = Stub(post_results={"/fabrics/SITE1/networkAttachments/query": {"attachments": rows}}, put_errors=[RuntimeError(refusal)] * 3)
    _applier(client).apply([Op("put_interface", "SITE1", "PUT", port, {"i": 1})])
    assert [c[0] for c in client.calls] == ["PUT", "POST", "POST", "POST", "PUT", "PUT", "PUT", "POST", "POST"]


def test_port_put_gives_up_after_the_retry_budget_and_reattaches():
    port = "/fabrics/SITE1/switches/S1/interfaces/Ethernet1%2F5"
    rows = [{"networkName": "N1", "switchId": "S1", "vlanId": 10, "attach": True, "interfaces": [{"interfaceRange": "Ethernet1/5", "mode": "access"}]}]
    client = Stub(post_results={"/fabrics/SITE1/networkAttachments/query": {"attachments": rows}}, put_errors=[RuntimeError("HTTP 400 Policy type change x")] * 50)
    with pytest.raises(ApplyError, match="re-attached"):
        _applier(client).apply([Op("put_interface", "SITE1", "PUT", port, {"i": 1})])
    assert len([c for c in client.calls if c[0] == "PUT"]) == 13  # the first attempt plus TYPE_CHANGE_TRIES after the detach


def _membership_ops():
    return [
        Op("attach", "SITE1", "POST", "/fabrics/SITE1/networkAttachments", {"attachments": []}),
        Op("create_network", "MSD", "POST", "/fabrics/MSD/networks", {"networks": []}),
        Op("put_link", "SITE1", "PUT", "/links/1", {"l": 1}),
        Op("add_member", "MSD", "POST", "/fabrics/MSD/actions/addMembers", {"members": [{"name": "SITE1"}]}),
    ]


def test_apply_with_add_member_deploys_fabrics_then_group_before_any_overlay_op():
    client = Stub()
    topo = _topo()
    assert topo.mode_fabrics == ("SITE1", "SITE2")
    _applier(client).apply(_membership_ops())
    assert [(c[0], c[1]) for c in client.calls if c[0] in ("PUT", "POST") and not c[1].endswith("/query")] == [
        ("POST", "/fabrics/MSD/actions/addMembers"),
        ("PUT", "/links/1"),
        ("POST", "/fabrics/SITE1/actions/configSave"),
        ("POST", "/fabrics/SITE1/actions/deploy"),
        ("POST", "/fabrics/SITE2/actions/configSave"),
        ("POST", "/fabrics/SITE2/actions/deploy"),
        ("POST", "/fabrics/MSD/actions/configSave"),
        ("POST", "/fabrics/MSD/actions/deploy"),
        ("POST", "/fabrics/MSD/networks"),
        ("POST", "/fabrics/SITE1/networkAttachments"),
    ]


def test_apply_without_add_member_keeps_todays_order():
    client = Stub()
    ops = _membership_ops()[:3]
    _applier(client).apply(ops)
    assert [(c[0], c[1]) for c in client.calls] == [("PUT", "/links/1"), ("POST", "/fabrics/MSD/networks"), ("POST", "/fabrics/SITE1/networkAttachments")]


def test_rank_orders_member_add_and_the_ir_put():
    from golden_apply import RANK

    assert RANK["set_role"] < RANK["add_member"] < RANK["clear_link"]
    assert RANK["put_network_ir"] == RANK["attach"] > RANK["create_network"]
    assert RANK["put_network_ir"] < RANK["deploy_network_ir"] < RANK["unpair_tor"]


def test_enable_ir_fix_from_the_drift_applies_the_put_before_the_deploy():
    from dataclasses import replace

    from golden_drift import drift_overlay
    from golden_live import read_live_from_snapshot
    from tests.test_golden_drift import BASE, GOLDEN
    from topology import load

    topo = replace(load(BASE / "topology_nd421_base.yaml"), replication_mode="ingress", mode_fabrics=("SITE1",))
    live = read_live_from_snapshot(GOLDEN / "nd421" / "multicast", topo)
    fix = next(d.fix for d in drift_overlay(topo, live) if d.cls == "networks")
    assert isinstance(fix, list)
    client = Stub()
    _applier(client).apply(list(reversed(fix)))
    assert [(c[0], c[1]) for c in client.calls] == [("PUT", "/fabrics/SITE1/networks/LAB_NET1"), ("POST", "/fabrics/SITE1/networkActions/deploy")]


class RefusingDelete(Stub):
    def __init__(self, refusals, message="DELETE /fabrics/MSD/networks/N -> HTTP 400: network is attached"):
        super().__init__()
        self.refusals = refusals
        self.message = message

    def delete(self, path):
        self.calls.append(("DELETE", path, None))
        if self.refusals:
            self.refusals -= 1
            raise RuntimeError(self.message)
        return None


def test_restore_applier_does_not_retry_a_refused_overlay_delete():
    client = RefusingDelete(1)
    ops = [Op("delete_network", "MSD", "DELETE", "/fabrics/MSD/networks/N", None), Op("delete_vrf", "MSD", "DELETE", "/fabrics/MSD/vrfs/V", None)]
    with pytest.raises(ApplyError, match="HTTP 400"):
        _applier(client).apply(ops)
    assert client.writes == [("DELETE", "/fabrics/MSD/networks/N", None)]


def test_waiting_applier_retries_a_refused_overlay_delete_with_the_detach_budget(monkeypatch):
    import golden_apply

    slept: list = []
    monkeypatch.setattr(golden_apply.time, "sleep", slept.append)
    client = RefusingDelete(2)
    applier = Applier(Provisioner(client, _topo()), _topo(), wait_overlay_deletes=True)
    applier.apply([Op("delete_vrf", "MSD", "DELETE", "/fabrics/MSD/vrfs/V", None)])
    assert [c[1] for c in client.writes] == ["/fabrics/MSD/vrfs/V"] * 3 and slept == [golden_apply.TYPE_CHANGE_WAIT] * 2


@pytest.mark.parametrize("message", ["DELETE /x -> HTTP 404: not found", "DELETE /x -> HTTP 500: boom", "connection aborted"])
def test_waiting_applier_does_not_retry_a_delete_error_that_is_not_a_refusal(monkeypatch, message):
    import golden_apply

    monkeypatch.setattr(golden_apply.time, "sleep", lambda s: pytest.fail("no wait expected"))
    client = RefusingDelete(5, message)
    with pytest.raises(ApplyError):
        Applier(Provisioner(client, _topo()), _topo(), wait_overlay_deletes=True).apply([Op("delete_network", "MSD", "DELETE", "/fabrics/MSD/networks/N", None)])
    assert len(client.writes) == 1
