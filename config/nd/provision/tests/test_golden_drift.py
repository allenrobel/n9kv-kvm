"""golden_drift link classes, run against the committed nd421/nd431 snapshots as the live state (and mutated copies of them)."""

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from golden_drift import Adoption, Drift, Op, default_body, drift_generated_links, drift_interfaces, drift_links, format_report, interface_body, numbered_link_body
from golden_live import read_live_from_snapshot
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
