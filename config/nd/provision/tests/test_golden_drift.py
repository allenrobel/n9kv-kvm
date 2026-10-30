"""golden_drift link classes, run against the committed nd421/nd431 snapshots as the live state (and mutated copies of them)."""

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from golden_drift import (
    Adoption,
    Drift,
    Op,
    compute,
    default_body,
    drift_generated_links,
    drift_interfaces,
    drift_links,
    drift_overlay,
    drift_pairs,
    drift_settings,
    drift_switches,
    format_report,
    interface_body,
    numbered_link_body,
)
from golden_live import read_live_from_snapshot
from provision import vpc_pair_payload
from topology import FabricLink, GeneratedLink, InterfaceIntent, Topology, load

HERE = Path(__file__).resolve().parents[1]
GOLDEN = HERE / "golden"

SITE1_LINKS = [
    FabricLink("S1_SP1", "Ethernet1/1", "S1_BG1", "Ethernet1/2", "numbered", "10.14.0.1", "10.14.0.2"),
    FabricLink("S1_SP1", "Ethernet1/2", "S1_LE1", "Ethernet1/1", "numbered", "10.14.0.5", "10.14.0.6"),
    FabricLink("S1_SP1", "Ethernet1/3", "S1_LE2", "Ethernet1/1", "numbered", "10.14.0.9", "10.14.0.10"),
    FabricLink("S1_SP1", "Ethernet1/4", "S1_LE3", "Ethernet1/1", "numbered", "10.14.0.13", "10.14.0.14"),
    FabricLink("S1_SP1", "Ethernet1/5", "S1_LE4", "Ethernet1/1", "numbered", "10.14.0.17", "10.14.0.18"),
]
SITE2_LINKS = [
    FabricLink("S2_SP1", "Ethernet1/1", "S2_BG1", "Ethernet1/2", "numbered", "10.24.0.1", "10.24.0.2"),
    FabricLink("S2_SP1", "Ethernet1/2", "S2_LE1", "Ethernet1/1", "numbered", "10.24.0.5", "10.24.0.6"),
]
BG_UNDERLAY = GeneratedLink("S1_BG1", "Ethernet1/1", "S2_BG1", "Ethernet1/1", "multisiteUnderlay", "MSD")
BG_OVERLAY = GeneratedLink("S1_BG1", "Loopback0", "S2_BG1", "Loopback0", "multisiteOverlay", "MSD")


def _with(topo: Topology, site1_links=(), site2_links=(), generated=(), isn=None) -> Topology:
    fabrics = []
    for f in topo.fabrics:
        if f.name == "SITE1":
            f = replace(f, links=list(site1_links), generated_links=list(generated))
        elif f.name == "SITE2":
            f = replace(f, links=list(site2_links))
        fabrics.append(f)
    return replace(topo, fabrics=fabrics, isn=replace(topo.isn, links=topo.isn.links if isn is None else isn))


@pytest.fixture(params=["nd421", "nd431"])
def lab(request):
    version = request.param
    topo = load(HERE / f"topology_{version}.yaml")
    return topo, read_live_from_snapshot(GOLDEN / version, topo)


@pytest.fixture
def nd421():
    topo = load(HERE / "topology_nd421.yaml")
    return topo, read_live_from_snapshot(GOLDEN / "nd421", topo)


def _fabric(topo: Topology, name: str):
    return next(f for f in topo.fabrics if f.name == name)


def _link(live, fabric: str, link_id: str) -> dict:
    return next(o for o in live[fabric].links if o["linkId"] == link_id)


def _run(topo: Topology, live, names=("SITE1", "SITE2")) -> list[Drift]:
    seen: set = set()
    return [d for name in names for d in drift_links(topo, _fabric(topo, name), live, seen)]


def _site_topo(topo: Topology) -> Topology:
    """The golden lab as the snapshot has it, minus the known multisiteUnderlay-vs-ebgpVrfLite ISN discrepancy on WAN1 Gi2."""
    isn = [link for link in topo.isn.links if link.src_if != "GigabitEthernet2"]
    return _with(topo, SITE1_LINKS, SITE2_LINKS, [BG_UNDERLAY, BG_OVERLAY], isn)


def test_no_link_drift_on_the_golden_lab(nd421):
    topo, live = nd421
    assert _run(_site_topo(topo), live) == []


def test_isn_link_policy_mismatch_reports_different(nd421):
    topo, live = nd421
    drifts = _run(_with(topo, SITE1_LINKS, SITE2_LINKS, [BG_UNDERLAY, BG_OVERLAY]), live)  # the shipped isn.links, as golden has them
    assert [d.kind for d in drifts] == ["different"]
    drift = drifts[0]
    assert "ebgpVrfLite" in drift.golden and "multisiteUnderlay" in drift.live
    assert drift.fix is not None and drift.fix.action == "put_link" and drift.fix.method == "PUT"
    assert drift.fix.path == "/links/LINK-UUID-78520"
    assert drift.fix.body["configData"]["policyType"] == "ebgpVrfLite"
    assert drift.fix.body["srcSwitchId"] == "9S3F1H79UZU"


def test_missing_policy_yields_put_link_with_numbered_body(nd421):
    topo, live = nd421
    _link(live, "SITE1", "LINK-UUID-6000")["configData"] = None
    drifts = _run(_site_topo(topo), live)
    assert [d.kind for d in drifts] == ["missing"]
    fix = drifts[0].fix
    assert isinstance(fix, Op) and fix.action == "put_link" and fix.path == "/links/LINK-UUID-6000"
    inputs = fix.body["configData"]["templateInputs"]
    assert fix.body["configData"]["policyType"] == "numbered"
    assert inputs["srcIp"] == "10.14.0.5" and inputs["dstIp"] == "10.14.0.6"
    assert inputs["srcInterfaceDescription"] == "connected-to-S1_SP1-Ethernet1/2"
    assert inputs["dstInterfaceDescription"] == "connected-to-S1_LE1-Ethernet1/1"
    assert drifts[0].live == "none" and drifts[0].golden == "numbered 10.14.0.5/.6"


def test_different_ip_yields_different(nd421):
    topo, live = nd421
    _link(live, "SITE1", "LINK-UUID-6000")["configData"]["templateInputs"]["srcIp"] = "10.14.0.9"
    drifts = _run(_site_topo(topo), live)
    assert [d.kind for d in drifts] == ["different"]
    assert "10.14.0.5" in drifts[0].golden and "10.14.0.9" in drifts[0].live


def test_numbered_body_follows_live_orientation_and_inputs_override(nd421):
    topo, live = nd421
    obj = _link(live, "SITE1", "LINK-UUID-78870")  # live src is S1_LE3, golden lists the spine first
    golden = replace(SITE1_LINKS[3], inputs={"mtu": 1500})
    body = numbered_link_body(obj, golden)
    inputs = body["configData"]["templateInputs"]
    assert (inputs["srcIp"], inputs["dstIp"]) == ("10.14.0.14", "10.14.0.13")
    assert inputs["srcInterfaceDescription"] == "connected-to-S1_LE3-Ethernet1/1"
    assert inputs["dstInterfaceDescription"] == "connected-to-S1_SP1-Ethernet1/4"
    assert inputs["mtu"] == 1500 and inputs["fec"] == "auto" and inputs["bfdEchoOnSrcInterface"] is False
    assert set(body) == {
        "srcFabricName",
        "srcSwitchId",
        "srcInterfaceName",
        "srcSwitchName",
        "dstFabricName",
        "dstSwitchId",
        "dstInterfaceName",
        "dstSwitchName",
        "configData",
    }


def test_inputs_in_golden_are_compared(nd421):
    topo, live = nd421
    golden = [replace(SITE1_LINKS[1], inputs={"mtu": 1500})] + SITE1_LINKS[:1] + SITE1_LINKS[2:]
    drifts = _run(_with(topo, golden, SITE2_LINKS, [BG_UNDERLAY, BG_OVERLAY], _site_topo(topo).isn.links), live)
    assert [d.kind for d in drifts] == ["different"]


def test_extra_tool_link_offers_adopt_and_clear(nd421):
    topo, live = nd421
    obj = _link(live, "SITE1", "LINK-UUID-78870")
    obj["configData"] = {"policyType": "ebgpVrfLite", "templateInputs": {"srcIpAddressMask": "10.1.1.1/30", "dstIpAddress": "10.1.1.2"}}
    site = _site_topo(topo)
    site = _with(site, [fl for fl in SITE1_LINKS if fl.dst != "S1_LE3"], SITE2_LINKS, [BG_UNDERLAY, BG_OVERLAY], site.isn.links)
    drifts = _run(site, live)
    assert [d.kind for d in drifts] == ["extra"]
    drift = drifts[0]
    assert drift.delete is not None and drift.delete.action == "clear_link" and drift.delete.path == "/links/LINK-UUID-78870"
    assert drift.delete.body["configData"] is None and drift.delete.body["srcSwitchName"] == "S1_LE3"
    assert drift.adopt == Adoption(
        ("fabrics", "SITE1", "links"),
        {"src": "S1_LE3", "src_if": "Ethernet1/1", "dst": "S1_SP1", "dst_if": "Ethernet1/4", "policy": "ebgpVrfLite", "src_ip": "10.1.1.1/30", "dst_ip": "10.1.1.2"},
    )
    assert drift.fix is None


def test_cross_fabric_link_is_reported_once(nd421):
    topo, live = nd421
    obj = copy.deepcopy(_link(live, "SITE1", "LINK-UUID-13140"))  # a discovered S1_LE2 <-> S1_LE1 link, now carrying a policy
    obj["configData"] = {"policyType": "ebgpVrfLite", "templateInputs": {}}
    live["SITE1"].links = [o for o in live["SITE1"].links if o["linkId"] != "LINK-UUID-13140"] + [obj]
    live["SITE2"].links.append(copy.deepcopy(obj))
    drifts = _run(_site_topo(topo), live)
    assert [d.kind for d in drifts] == ["extra"]
    assert drifts[0].fabric == "SITE1"


def test_generated_link_missing_policy_fixes_via_owner_deploy(nd421):
    topo, live = nd421
    for fabric in ("SITE1", "SITE2"):
        _link(live, fabric, "LINK-UUID-99850")["configData"] = None
    site = _site_topo(topo)
    drifts = drift_generated_links(site, _fabric(site, "SITE1"), live)
    assert [d.kind for d in drifts] == ["missing"]
    assert drifts[0].fix == Op("deploy_owner", "MSD", "", "", None)
    assert drifts[0].delete is None and drifts[0].adopt is None


def test_generated_link_wrong_policy_and_absent(nd421):
    topo, live = nd421
    site = _site_topo(topo)
    assert drift_generated_links(site, _fabric(site, "SITE1"), live) == []
    for fabric in ("SITE1", "SITE2"):
        _link(live, fabric, "LINK-UUID-99850")["configData"]["policyType"] = "numbered"
    (different,) = drift_generated_links(site, _fabric(site, "SITE1"), live)
    assert different.kind == "different" and different.live == "numbered"
    for fabric in ("SITE1", "SITE2"):
        live[fabric].links = [o for o in live[fabric].links if o["linkId"] != "LINK-UUID-99850"]
    (absent,) = drift_generated_links(site, _fabric(site, "SITE1"), live)
    assert absent.kind == "missing" and absent.live == "none"


def test_discovered_links_without_policy_are_not_extras(lab):
    topo, live = lab
    bare = [o for o in live["SITE1"].links if not o.get("configData")]
    assert bare
    reported = {d.subject for d in _run(topo, live) if d.kind == "extra"}
    for o in bare:
        assert _subject(o) not in reported
    assert reported  # the numbered links are extras only because the shipped topology lists none


def _subject(o: dict) -> str:
    return f"{o['srcSwitchName']} {o['srcInterfaceName']} <-> {o['dstSwitchName']} {o['dstInterfaceName']}"


def test_missing_link_object_is_reported_without_fix(nd421):
    topo, live = nd421
    live["SITE1"].links = [o for o in live["SITE1"].links if o["linkId"] != "LINK-UUID-6000"]
    drifts = _run(_site_topo(topo), live)
    assert [(d.kind, d.fix) for d in drifts] == [("missing", None)]


def test_format_report_lines_are_stable_and_hostname_based(nd421):
    topo, live = nd421
    _link(live, "SITE1", "LINK-UUID-6000")["configData"] = None
    drifts = _run(_site_topo(topo), live)
    assert format_report(drifts) == ("SITE1 links      MISSING policy  S1_SP1 Ethernet1/2 <-> S1_LE1 Ethernet1/1   golden=numbered 10.14.0.5/.6  live=none")
    assert format_report([]) == ""


def test_generated_link_satisfied_if_any_list_has_the_policy(nd421):
    topo, live = nd421
    _link(live, "SITE2", "LINK-UUID-99850")["configData"] = None
    site = _site_topo(topo)
    assert drift_generated_links(site, _fabric(site, "SITE1"), live) == []


def test_missing_isn_link_is_reported_once(nd421):
    topo, live = nd421
    for fabric in ("SITE1", "ISN"):
        live[fabric].links = [o for o in live[fabric].links if o["linkId"] != "LINK-UUID-78520"]
    seen: set = set()
    drifts = [d for name in ("SITE1", "ISN") for d in drift_links(topo, _fabric(topo, name), live, seen)]
    missing = [d for d in drifts if "GigabitEthernet2" in d.subject]
    assert [(d.kind, d.fix) for d in missing] == [("missing", None)]


def test_isn_fix_keeps_live_orientation(nd421):
    topo, live = nd421
    obj = _link(live, "SITE2", "LINK-UUID-122220")
    for key in ("FabricName", "SwitchId", "InterfaceName", "SwitchName"):
        obj["src" + key], obj["dst" + key] = obj["dst" + key], obj["src" + key]
    obj["configData"] = None
    drifts = _run(_site_topo(topo), live)
    (drift,) = [d for d in drifts if "GigabitEthernet3" in d.subject]
    body = drift.fix.body
    inputs = body["configData"]["templateInputs"]
    assert body["srcSwitchName"] == "S2_BG1" and body["dstSwitchName"] == "WAN1"
    assert inputs["srcIpAddressMask"] == "10.25.0.2/30" and inputs["dstIpAddress"] == "10.25.0.1"
    assert inputs["srcEbgpAsn"] == "65002" and inputs["dstEbgpAsn"] == "65535"
    assert inputs["srcInterfaceDescription"] == "connected-to-WAN1-GigabitEthernet3"


# ---------------------------------------------------------------- interfaces

ROLE_DEFAULTS = {
    "leaf": {"policyType": "trunkHost", "adminState": True, "allowedVlans": "none"},
    "tor": {"policyType": "trunkHost", "adminState": True, "allowedVlans": "none"},
    "spine": {"policyType": "routedHost", "adminState": True},
    "borderGateway": {"policyType": "routedHost", "adminState": True},
}
HOST_PORTS = {
    "SITE1": [InterfaceIntent("S1_TOR1", "Ethernet1/3", "accessHost", description="S1_H1 host port")],
    "SITE2": [InterfaceIntent("S2_LE1", "Ethernet1/2", "accessHost", description="LAB_NET1 host port")],
}


def _with_interfaces(topo: Topology, extra=()) -> Topology:
    """The golden lab with the captured role defaults and the two host ports; `extra` adds (fabric, InterfaceIntent) entries."""
    fabrics = []
    for f in topo.fabrics:
        if f.name in HOST_PORTS:
            f = replace(f, defaults=ROLE_DEFAULTS, interfaces=[*HOST_PORTS[f.name], *(i for n, i in extra if n == f.name)])
        fabrics.append(f)
    return replace(topo, fabrics=fabrics)


def _all_links(live) -> list[dict]:
    return [link for fab in live.values() for link in fab.links]


def _run_interfaces(topo: Topology, live, names=("SITE1", "SITE2", "CAMPUS1", "ISN")) -> list[Drift]:
    links = _all_links(live)
    return [d for name in names for d in drift_interfaces(topo, _fabric(topo, name), live, links)]


def _iface(live, fabric: str, host: str, name: str) -> dict:
    return next(i for i in live[fabric].interfaces[host] if i["interfaceName"] == name)


def _adopted(topo: Topology, drifts: list[Drift]) -> Topology:
    """Apply every drift's adoption entry to the topology, as the bootstrap does."""
    extra = [(d.adopt.section[1], InterfaceIntent(**d.adopt.entry)) for d in drifts if d.adopt]
    return _with_interfaces(topo, extra)


def test_the_golden_lab_residue_is_what_the_dumps_hold(nd421):
    topo, live = nd421
    extras = [d for d in _run_interfaces(_with_interfaces(topo), live) if d.kind == "extra"]
    bg1 = [d for d in extras if d.subject.startswith("S1_BG1 ") and d.delete.action == "reset_interface"]
    assert len([d for d in bg1 if d.live.startswith("trunkHost")]) == 19
    po10 = next(d for d in extras if d.subject == "S1_TOR1 port-channel10")
    assert po10.delete.action == "delete_interface" and po10.adopt.entry == {
        "switch": "S1_TOR1",
        "interface": "port-channel10",
        "policy": "l3Po",
        "type": "portChannel",
        "description": "subinterface test parent",
    }


def test_no_interface_drift_on_the_golden_lab(lab):
    topo, live = lab
    golden = _with_interfaces(topo)
    drifts = _run_interfaces(golden, live)
    assert drifts  # the known residue (S1_BG1 trunk ports, S1_TOR1 port-channel10, ...)
    assert _run_interfaces(_adopted(topo, drifts), live) == []  # once the residue is adopted into golden, nothing is left


def test_explicit_port_different_reports_compared_inputs_only(nd421):
    topo, live = nd421
    golden = _with_interfaces(topo)
    policy = _iface(live, "SITE1", "S1_TOR1", "Ethernet1/3")["configData"]["networkOS"]["policy"]
    policy["ptp"] = True
    assert [d for d in _run_interfaces(golden, live) if d.subject == "S1_TOR1 Ethernet1/3"] == []
    live_if = _iface(live, "SITE1", "S1_TOR1", "Ethernet1/3")
    live_if["configData"]["mode"] = "trunk"
    policy.update({"policyType": "trunkHost", "allowedVlans": "none"})
    drift = next(d for d in _run_interfaces(golden, live) if d.subject == "S1_TOR1 Ethernet1/3")
    assert drift.kind == "different" and "accessHost" in drift.golden
    assert "trunkHost" in drift.live and "allowedVlans=none" in drift.live
    assert drift.fix is not None and drift.fix.action == "put_interface" and drift.fix.method == "PUT"
    assert drift.fix.path.endswith("/interfaces/Ethernet1%2F3")
    assert drift.fix.body["configData"]["networkOS"]["policy"]["policyType"] == "accessHost"
    assert drift.fix.body["configData"]["mode"] == "access"


def test_explicit_port_missing_live_offers_put(nd421):
    topo, live = nd421
    live["SITE1"].interfaces["S1_TOR1"] = [i for i in live["SITE1"].interfaces["S1_TOR1"] if i["interfaceName"] != "Ethernet1/3"]
    drift = next(d for d in _run_interfaces(_with_interfaces(topo), live) if d.subject == "S1_TOR1 Ethernet1/3")
    assert drift.kind == "missing" and drift.live == "none" and drift.fix is not None and drift.fix.action == "put_interface"


def test_accessvlan_compares_as_a_string(nd421):
    topo, live = nd421
    golden = _with_interfaces(topo, [("SITE1", InterfaceIntent("S1_TOR1", "Ethernet1/9", "trunkHost", inputs={"accessVlan": 1, "allowedVlans": "none"}))])
    for value in (1, "1"):
        _iface(live, "SITE1", "S1_TOR1", "Ethernet1/9")["configData"]["networkOS"]["policy"]["accessVlan"] = value
        assert [d for d in _run_interfaces(golden, live) if d.subject == "S1_TOR1 Ethernet1/9"] == []


def test_free_port_with_description_residue_is_extra_with_reset(nd421):
    topo, live = nd421
    _iface(live, "SITE1", "S1_BG1", "Ethernet1/5")["configData"]["networkOS"]["policy"]["description"] = "test"
    drift = next(d for d in _run_interfaces(_with_interfaces(topo), live) if d.subject == "S1_BG1 Ethernet1/5")
    assert drift.kind == "extra"
    assert drift.delete is not None and drift.delete.action == "reset_interface" and drift.delete.method == "PUT"
    assert drift.delete.body["configData"]["networkOS"]["policy"]["policyType"] == "routedHost"
    assert drift.delete.body["configData"]["mode"] == "routed"
    assert drift.adopt == Adoption(("fabrics", "SITE1", "interfaces"), {"switch": "S1_BG1", "interface": "Ethernet1/5", "policy": "routedHost", "description": "test"})


def test_role_without_defaults_is_not_checked(nd421):
    topo, live = nd421
    _iface(live, "SITE1", "S1_BG1", "Ethernet1/5")["configData"]["networkOS"]["policy"]["description"] = "test"
    fabrics = [replace(f, defaults={k: v for k, v in f.defaults.items() if k != "borderGateway"}) for f in _with_interfaces(topo).fabrics]
    drifts = _run_interfaces(replace(topo, fabrics=fabrics), live)
    assert not [d for d in drifts if d.subject.startswith("S1_BG1")]


def test_link_endpoints_and_port_channel_members_are_never_extra(nd421):
    topo, live = nd421
    golden = _with_interfaces(topo)
    baseline = _run_interfaces(golden, live)
    for host, name in (("S1_SP1", "Ethernet1/2"), ("S1_LE1", "Ethernet1/2"), ("S1_LE1", "Ethernet1/1")):
        policy = _iface(live, "SITE1", host, name)["configData"]["networkOS"]["policy"]
        policy["description"] = "residue"
        policy["policyType"] = "something"
    assert _run_interfaces(golden, live) == baseline


def test_extra_vpc_offers_real_delete(nd421):
    topo, live = nd421
    live["SITE1"].interfaces["S1_LE1"].append({"interfaceName": "vpc200", "interfaceType": "vpc", "switchId": "9UDEG98YLEY", "configData": None})
    drift = next(d for d in _run_interfaces(_with_interfaces(topo), live) if d.subject == "S1_LE1 vpc200")
    assert drift.kind == "extra" and drift.delete is not None and drift.delete.action == "delete_interface"
    assert drift.delete.method == "DELETE" and drift.delete.path.endswith("/interfaces/vpc200") and drift.delete.body is None
    assert drift.adopt is not None and drift.adopt.entry["type"] == "vpc"


def test_generated_logical_interfaces_are_ignored(nd421):
    topo, live = nd421
    golden = _with_interfaces(topo)
    baseline = _run_interfaces(golden, live)
    live["SITE1"].interfaces["S1_LE1"].append({"interfaceName": "Ethernet1/1.2", "interfaceType": "subInterface", "switchId": "9UDEG98YLEY", "configData": None})
    live["SITE1"].interfaces["S1_LE1"].append({"interfaceName": "Vlan2", "interfaceType": "svi", "switchId": "9UDEG98YLEY", "configData": None})
    assert _run_interfaces(golden, live) == baseline
    subjects = {d.subject for d in baseline}
    assert not subjects & {"S1_LE1 port-channel500", "S1_LE1 port-channel1", "S1_LE1 vPC1", "S1_LE1 Vlan3600", "S1_LE1 Vlan1", "S1_LE1 Vlan2001"}


def test_unrelated_svi_and_orphan_subinterface_are_extra(nd421):
    topo, live = nd421
    live["SITE1"].interfaces["S1_LE1"] += [
        {"interfaceName": "Vlan777", "interfaceType": "svi", "switchId": "9UDEG98YLEY", "configData": None},
        {"interfaceName": "Ethernet1/20.5", "interfaceType": "subInterface", "switchId": "9UDEG98YLEY", "configData": None},
    ]
    subjects = {d.subject for d in _run_interfaces(_with_interfaces(topo), live) if d.kind == "extra"}
    assert {"S1_LE1 Vlan777", "S1_LE1 Ethernet1/20.5"} <= subjects


def test_core_router_switches_are_skipped(nd421):
    topo, live = nd421
    live["ISN"].interfaces["WAN1"].append({"interfaceName": "vpc9", "interfaceType": "vpc", "switchId": "X", "configData": None})
    fabrics = [replace(f, defaults={"coreRouter": {"policyType": "routedHost"}}) if f.name == "ISN" else f for f in topo.fabrics]
    assert _run_interfaces(replace(topo, fabrics=fabrics), live, names=("ISN",)) == []
    wan = next(f for f in topo.fabrics if f.name == "ISN")
    explicit = replace(wan, type="vxlanIbgp", interfaces=[InterfaceIntent("WAN1", "GigabitEthernet9", "routedHost")])
    assert drift_interfaces(topo, explicit, live, _all_links(live)) == []


def test_bodies_follow_the_access_port_shape():
    body = interface_body("SER", InterfaceIntent("S1", "Ethernet1/3", "accessHost", description="d", inputs={"mtu": 1500}), {})
    policy = body["configData"]["networkOS"]["policy"]
    assert body["switchId"] == "SER" and body["interfaceType"] == "ethernet" and body["configData"]["mode"] == "access"
    assert policy == {
        "policyType": "accessHost",
        "adminState": True,
        "mtu": 1500,
        "speed": "auto",
        "bpduGuard": "default",
        "portTypeEdgeTrunk": True,
        "description": "d",
    }
    reset = default_body("SER", "Ethernet1/4", {"policyType": "trunkHost", "allowedVlans": "none"})
    assert reset["configData"]["mode"] == "trunk" and reset["configData"]["networkOS"]["policy"] == {"policyType": "trunkHost", "allowedVlans": "none"}


# ---------------------------------------------------------------- overlay, pairs, switches, settings


def _with_tor_associations(topo: Topology, live) -> None:
    """The dumps carry no accessAssociations_*.json, so give the live fabric the association the golden ToR pair describes."""
    for pair in topo.tor_pairs:
        serials = {h: live[pair.fabric].switches[h]["serialNumber"] for h in (pair.tor, pair.leaf, pair.peer)}
        live[pair.fabric].tor_associations.append(
            {
                "accessOrTorSwitchId": serials[pair.tor],
                "aggregationOrLeafSwitchId": serials[pair.leaf],
                "aggregationOrLeafPeerSwitchId": serials[pair.peer],
                "resources": pair.resources(),
            }
        )


@pytest.fixture
def full_lab(lab):
    topo, live = lab
    _with_tor_associations(topo, live)
    return topo, live


def _non_link(topo: Topology, live) -> list[Drift]:
    return [*drift_settings(topo, live), *drift_switches(topo, live), *drift_overlay(topo, live), *drift_pairs(topo, live)]


def test_no_overlay_pair_switch_or_settings_drift_on_the_golden_lab(full_lab):
    topo, live = full_lab
    assert _non_link(topo, live) == []


def test_missing_tor_attachment_fixes_with_attach_payload_including_interfaces(nd421):
    topo, live = nd421
    live["SITE1"].network_attachments = [a for a in live["SITE1"].network_attachments if a["switchName"] != "S1_TOR1"]
    drifts = [d for d in drift_overlay(topo, live) if d.cls == "attachments"]
    assert [(d.kind, d.subject) for d in drifts] == [("missing", "LAB_NET1 S1_TOR1")]
    serial = live["SITE1"].switches["S1_TOR1"]["serialNumber"]
    body = {
        "attachments": [
            {"networkName": "LAB_NET1", "switchId": serial, "vlanId": 2, "interfaces": [{"interfaceRange": "Ethernet1/3", "mode": "access"}], "attach": True}
        ]
    }
    assert drifts[0].fix == Op("attach", "SITE1", "POST", "/fabrics/SITE1/networkAttachments", body)


def test_attachment_interfaces_compare_order_insensitively_and_difference_is_reported(nd421):
    topo, live = nd421
    row = next(a for a in live["SITE2"].network_attachments if a["switchName"] == "S2_LE1")
    row["interfaces"] = [{"mode": "access", "interfaceRange": "Ethernet1/2"}]
    assert drift_overlay(topo, live) == []  # same range and mode in another key order is no drift
    row["interfaces"] = [{"interfaceRange": "Ethernet1/9", "mode": "access"}]
    drifts = drift_overlay(topo, live)
    assert [(d.kind, d.fabric) for d in drifts] == [("different", "SITE2")]
    assert drifts[0].fix is not None and drifts[0].fix.action == "attach"


def test_extra_attachment_offers_adopt_or_detach(nd421):
    topo, live = nd421
    row = next(a for a in live["SITE1"].network_attachments if a["switchName"] == "S1_LE1")
    live["SITE1"].network_attachments.append({**row, "switchName": "S1_LE3", "switchId": live["SITE1"].switches["S1_LE3"]["serialNumber"]})
    drifts = drift_overlay(topo, live)
    assert [d.kind for d in drifts] == ["extra"]
    assert drifts[0].adopt == Adoption(("overlay", "network_attachments"), {"fabric": "SITE1", "network": "LAB_NET1", "switch": "S1_LE3", "vlan": 2, "interfaces": []})
    delete = drifts[0].delete
    assert isinstance(delete, Op) and delete.action == "detach" and delete.path == "/fabrics/SITE1/networkAttachments"
    assert delete.body["attachments"][0]["attach"] is False and delete.body["attachments"][0]["networkName"] == "LAB_NET1"


def test_extra_network_offers_adopt_or_delete_after_detach(nd421):
    topo, live = nd421
    live["SITE2"].networks.append({"networkName": "STRAY", "networkId": 30009, "vlanId": 9, "vrfName": "LAB", "l3Data": {"gatewayIpv4Address": "10.9.9.1/24"}})
    switch = live["SITE2"].switches["S2_LE1"]
    live["SITE2"].network_attachments.append(
        {"networkName": "STRAY", "switchName": "S2_LE1", "switchId": switch["serialNumber"], "attach": True, "vlanId": 9, "interfaces": []}
    )
    drifts = [d for d in drift_overlay(topo, live) if d.cls == "networks"]
    assert [(d.kind, d.subject) for d in drifts] == [("extra", "STRAY")]
    drift = drifts[0]
    obj = {"networkName": "STRAY", "networkId": 30009, "vlanId": 9, "vrfName": "LAB", "l3Data": {"gatewayIpv4Address": "10.9.9.1/24"}}
    assert drift.adopt == Adoption(("overlay", "networks"), {"fabrics": ["SITE2"], "object": obj})
    ops = drift.delete
    assert isinstance(ops, list)
    assert [o.action for o in ops] == ["detach", "deploy_overlay", "delete_network"]
    assert ops[0].path == "/fabrics/SITE2/networkAttachments" and ops[0].body["attachments"][0]["attach"] is False
    assert ops[1] == Op("deploy_overlay", "SITE2", "POST", "/fabrics/SITE2/networkActions/deploy", {"networkNames": ["STRAY"], "switchIds": [switch["serialNumber"]]})
    assert ops[2] == Op("delete_network", "SITE2", "DELETE", "/fabrics/SITE2/networks/STRAY", None)


def test_extra_vrf_without_attachments_deletes_directly(nd421):
    topo, live = nd421
    live["SITE1"].vrfs.append({"vrfName": "STRAY", "vrfId": 50009, "vlanId": 2009, "vrfType": "vxlanIbgp"})
    drifts = drift_overlay(topo, live)
    assert [(d.cls, d.kind, d.subject) for d in drifts] == [("vrfs", "extra", "STRAY")]
    assert drifts[0].delete == [Op("delete_vrf", "SITE1", "DELETE", "/fabrics/SITE1/vrfs/STRAY", None)]
    assert drifts[0].adopt is not None and drifts[0].adopt.section == ("overlay", "vrfs")


def test_msd_propagated_network_in_site1_is_not_extra(nd421):
    topo, live = nd421
    assert any(n["networkName"] == "LAB_NET1" for n in live["SITE1"].networks)  # the propagated copy
    assert [d for d in drift_overlay(topo, live) if d.cls in ("vrfs", "networks")] == []


def test_msd_object_missing_everywhere_is_missing_with_the_overlay_post(nd421):
    topo, live = nd421
    for name in ("SITE1", "SITE2"):
        live[name].networks = []
    drifts = drift_overlay(topo, live)
    assert [(d.cls, d.kind, d.fabric) for d in drifts] == [("networks", "missing", "MSD")]
    fix = drifts[0].fix
    assert fix is not None and (fix.action, fix.method, fix.path) == ("create_network", "POST", "/fabrics/MSD/networks")
    assert fix.body["networks"][0]["networkName"] == "LAB_NET1" and fix.body["networks"][0]["fabricName"] == "MSD"


def test_overlay_object_key_difference_ignores_type_fields(nd421):
    topo, live = nd421
    live["SITE1"].networks[0]["l3Data"]["gatewayIpv4Address"] = "192.0.1.254/24"
    drifts = drift_overlay(topo, live)
    assert [d.kind for d in drifts] == ["different"] and "192.0.1.1/24" in drifts[0].golden and "192.0.1.254/24" in drifts[0].live


def test_vpc_pair_missing_and_extra(nd421):
    topo, live = nd421
    live["SITE1"].vpc_pairs = [p for p in live["SITE1"].vpc_pairs if p["switchName"] != "S1_LE3" and p["peerSwitchName"] != "S1_LE3"]
    drifts = [d for d in drift_pairs(topo, live) if d.subject.startswith("S1_LE")]
    assert [(d.kind, d.subject) for d in drifts] == [("missing", "S1_LE3 <-> S1_LE4")]
    serial, peer = live["SITE1"].switches["S1_LE3"]["serialNumber"], live["SITE1"].switches["S1_LE4"]["serialNumber"]
    assert drifts[0].fix == Op("pair_vpc", "SITE1", "PUT", f"/fabrics/SITE1/switches/{serial}/vpcPair", vpc_pair_payload(serial, peer))
    live["SITE1"].vpc_pairs.append({"switchName": "S1_LE2", "switchId": "X2", "peerSwitchName": "S1_BG1", "peerSwitchId": "X1", "type": "discoveredPairs"})
    extra = [d for d in drift_pairs(topo, live) if d.kind == "extra"]
    assert len(extra) == 1 and extra[0].adopt == Adoption(("vpc_pairs",), {"fabric": "SITE1", "switch": "S1_LE2", "peer": "S1_BG1"})
    assert extra[0].delete == Op("unpair_vpc", "SITE1", "PUT", "/fabrics/SITE1/switches/X2/vpcPair", {"vpcAction": "unPair"})


def test_tor_pair_missing_and_extra(full_lab):
    topo, live = full_lab
    stored = live["SITE1"].tor_associations
    live["SITE1"].tor_associations = []
    drifts = [d for d in drift_pairs(topo, live) if d.kind == "missing" and "TOR" in d.subject]
    assert len(drifts) == 1
    fix = drifts[0].fix
    assert fix is not None and fix.action == "pair_tor" and fix.path == "/fabrics/SITE1/accessAssociationActions/associate"
    assert fix.body == stored
    live["SITE1"].tor_associations = [{**stored[0], "accessOrTorSwitchId": "OTHER"}]
    result = [d for d in drift_pairs(topo, live) if "TOR" in d.subject or d.cls == "pairs" and d.adopt and d.adopt.section == ("tor_pairs",)]
    assert sorted(d.kind for d in result) == ["extra", "missing"]
    extra = next(d for d in result if d.kind == "extra")
    assert isinstance(extra.delete, Op) and extra.delete.action == "unpair_tor"
    assert extra.delete.path == "/fabrics/SITE1/accessAssociationActions/disassociate" and extra.adopt is not None and extra.adopt.section == ("tor_pairs",)


def test_wrong_switch_role_fixes_with_set_role(nd421):
    topo, live = nd421
    live["SITE1"].switches["S1_LE1"]["switchRole"] = "spine"
    drifts = drift_switches(topo, live)
    assert [(d.kind, d.subject) for d in drifts] == [("different", "S1_LE1")]
    serial = live["SITE1"].switches["S1_LE1"]["serialNumber"]
    assert drifts[0].fix == Op("set_role", "SITE1", "POST", "/fabrics/SITE1/switchActions/changeRoles", {"switchRoles": [{"switchId": serial, "role": "leaf"}]})
    assert drifts[0].golden == "leaf" and drifts[0].live == "spine"


def test_missing_switch_and_switch_in_another_fabric(nd421):
    topo, live = nd421
    del live["SITE1"].switches["S1_LE4"]
    drifts = {d.subject: d for d in drift_switches(topo, live)}
    assert drifts["S1_LE4"].kind == "missing" and drifts["S1_LE4"].fix == Op("add_switch", "SITE1", "POST", "/fabrics/SITE1/switches", None)
    live["SITE1"].switches["S2_BG1"] = live["SITE2"].switches.pop("S2_BG1")
    elsewhere = next(d for d in drift_switches(topo, live) if d.subject == "S2_BG1" and d.fabric == "SITE2")
    assert elsewhere.kind == "different" and elsewhere.fix is None and "SITE1" in elsewhere.live
    assert not [d for d in drift_switches(topo, live) if d.subject == "S2_BG1" and d.kind == "extra"]


def test_extra_switch_is_reported_with_no_delete(nd421):
    topo, live = nd421
    live["SITE1"].switches["S1_NEW"] = {"hostname": "S1_NEW", "serialNumber": "SN9", "switchRole": "leaf", "fabricManagementIp": "192.168.12.99"}
    drifts = drift_switches(topo, live)
    assert [(d.kind, d.subject) for d in drifts] == [("extra", "S1_NEW")]
    assert drifts[0].delete is None and drifts[0].fix is None
    assert drifts[0].adopt == Adoption(("fabrics", "SITE1", "switches"), {"hostname": "S1_NEW", "ip": "192.168.12.99", "role": "leaf"})


def test_settings_difference_fixes_with_one_merged_put(nd421):
    topo, live = nd421
    live["SITE1"].settings["management"]["bgpLoopbackIpRange"] = "10.99.0.0/22"
    live["SITE1"].settings["management"]["nveLoopbackIpRange"] = "10.98.0.0/22"
    drifts = drift_settings(topo, live)
    assert [(d.fabric, d.kind, d.subject) for d in drifts] == [
        ("SITE1", "different", "management.bgpLoopbackIpRange"),
        ("SITE1", "different", "management.nveLoopbackIpRange"),
    ]
    assert drifts[0].fix is drifts[1].fix and drifts[0].fix is not None
    assert drifts[0].fix.action == "put_settings" and drifts[0].fix.path == "/fabrics/SITE1"
    body = drifts[0].fix.body
    assert body["management"]["bgpLoopbackIpRange"] == "10.11.0.0/22" and body["name"] == live["SITE1"].settings["name"]
    assert drifts[0].golden == "10.11.0.0/22" and drifts[0].live == "10.99.0.0/22"


def test_settings_key_outside_golden_is_not_drift(nd421):
    topo, live = nd421
    live["SITE1"].settings["management"]["someLiveOnlyKey"] = "x"
    live["SITE1"].settings["management"]["cdp"] = not live["SITE1"].settings["management"].get("cdp", False)
    assert drift_settings(topo, live) == []


def test_compute_orders_classes_stably(nd421):
    topo, live = nd421
    live["SITE1"].settings["management"]["bgpLoopbackIpRange"] = "10.99.0.0/22"
    live["SITE1"].switches["S1_NEW"] = {"hostname": "S1_NEW", "serialNumber": "SN9", "switchRole": "leaf", "fabricManagementIp": "1.1.1.1"}
    _link(live, "SITE1", "LINK-UUID-6000")["configData"] = None
    live["SITE1"].vrfs.append({"vrfName": "STRAY", "vrfId": 50009, "vlanId": 2009})
    live["SITE1"].networks.append({"networkName": "STRAY", "networkId": 30009, "vlanId": 9, "vrfName": "LAB"})
    live["SITE1"].network_attachments = [a for a in live["SITE1"].network_attachments if a["switchName"] != "S1_TOR1"]
    live["SITE1"].vpc_pairs = live["SITE1"].vpc_pairs[:1]
    _iface(live, "SITE1", "S1_BG1", "Ethernet1/5")["configData"]["networkOS"]["policy"]["description"] = "residue"
    topo = _with_interfaces(topo)
    drifts = compute(topo, live)
    order = ["settings", "switches", "links", "genlinks", "interfaces", "vrfs", "networks", "attachments", "pairs"]
    seen_cls = list(dict.fromkeys(d.cls for d in drifts))
    assert [c for c in order if c in seen_cls] == seen_cls
    assert {"settings", "switches", "links", "interfaces", "vrfs", "networks", "attachments", "pairs"} <= set(seen_cls)
    assert compute(topo, live) == drifts


def _stray_network(live, fabrics, attach_on="S1_LE1"):
    for name in fabrics:
        live[name].networks.append({"networkName": "TEST_NET", "networkId": 30777, "vlanId": 77, "vrfName": "LAB"})
    serial = live["SITE1"].switches[attach_on]["serialNumber"]
    live["SITE1"].network_attachments.append({"networkName": "TEST_NET", "switchName": attach_on, "switchId": serial, "attach": True, "vlanId": 77, "interfaces": []})
    return serial


def test_propagated_copy_of_an_extra_group_object_is_not_an_extra(nd421):
    topo, live = nd421
    serial = _stray_network(live, ["MSD", "SITE1", "SITE2"])
    drifts = drift_overlay(topo, live)
    assert [(d.cls, d.fabric, d.kind) for d in drifts] == [("networks", "MSD", "extra")]
    ops = drifts[0].delete
    assert isinstance(ops, list) and [o.action for o in ops] == ["detach", "deploy_overlay", "delete_network"]
    assert ops[0].fabric == "SITE1" and ops[0].body["attachments"][0]["switchId"] == serial and ops[0].body["attachments"][0]["attach"] is False
    assert ops[-1] == Op("delete_network", "MSD", "DELETE", "/fabrics/MSD/networks/TEST_NET", None)


def test_snapshot_group_extra_held_by_all_members_is_one_extra(nd421):
    topo, live = nd421
    _stray_network(live, ["SITE1", "SITE2"])
    drifts = drift_overlay(topo, live)
    assert [(d.cls, d.fabric, d.kind) for d in drifts] == [("networks", "MSD", "extra")]
    assert isinstance(drifts[0].delete, list) and drifts[0].delete[-1].path == "/fabrics/MSD/networks/TEST_NET"
