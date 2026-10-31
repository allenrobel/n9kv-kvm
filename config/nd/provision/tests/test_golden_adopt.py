"""golden_adopt: comment-preserving yaml writes of adoptions and the bootstrap adoption set, against the committed nd421 snapshot."""

import re
from dataclasses import replace
import shutil
from pathlib import Path

import pytest
import yaml

from golden_adopt import bootstrap_adoptions, bootstrap_conflicts, write_adoptions
from golden_drift import Adoption, compute
from golden_live import free_ports, read_live_from_snapshot
from topology import load

HERE = Path(__file__).resolve().parents[1]
GOLDEN = HERE / "golden"
BASE = Path(__file__).resolve().parent / "fixtures"  # pre-bootstrap copies of the shipped files (empty golden sections)

LINK = {"src": "S1_SP1", "src_if": "Ethernet1/9", "dst": "S1_LE1", "dst_if": "Ethernet1/9", "policy": "numbered", "src_ip": "10.14.1.1", "dst_ip": "10.14.1.2"}
IFACE = {"switch": "S1_LE1", "interface": "Ethernet1/20", "policy": "trunkHost", "description": "adopted", "inputs": {"allowedVlans": "2"}}


def comment_lines(text: str) -> set[str]:
    return {m.group(0).strip() for m in re.finditer(r"#.*$", text, re.MULTILINE)}


def site1(doc: dict) -> dict:
    return next(f for f in doc["fabrics"] if f["name"] == "SITE1")


def copy_topology(tmp_path: Path, name: str = "topology_nd421.yaml") -> Path:
    path = tmp_path / name
    shutil.copy(BASE / name.replace(".yaml", "_base.yaml"), path)
    return path


def test_write_adoptions_preserves_comments_and_appends_entries(tmp_path):
    path = copy_topology(tmp_path)
    before = path.read_text(encoding="utf-8")
    adoptions = [Adoption(("fabrics", "SITE1", "links"), dict(LINK)), Adoption(("fabrics", "SITE1", "interfaces"), dict(IFACE))]
    assert write_adoptions(path, adoptions) == 2
    after = path.read_text(encoding="utf-8")
    assert "# merged into the fabric object" in after
    assert comment_lines(before) <= comment_lines(after)
    doc = yaml.safe_load(after)
    assert LINK in site1(doc)["links"]
    assert IFACE in site1(doc)["interfaces"]
    assert yaml.safe_load(before)["fabric_groups"] == doc["fabric_groups"]
    assert load(path)  # still a valid topology
    assert write_adoptions(path, adoptions) == 0
    assert path.read_text(encoding="utf-8") == after


def test_write_adoptions_creates_missing_sections(tmp_path):
    path = tmp_path / "t.yaml"
    path.write_text("fabrics:\n  - name: F1  # first\n    type: vxlanIbgp\n    asn: '65001'\n    switches: []\n", encoding="utf-8")
    vrf = {"fabrics": ["F1"], "object": {"vrfName": "V1", "vlanId": 2001}}
    adoptions = [
        Adoption(("fabrics", "F1", "generated_links"), {"src": "A", "src_if": "e1", "dst": "B", "dst_if": "e1", "policy": "multisiteUnderlay", "owner": "MSD"}),
        Adoption(("overlay", "vrfs"), vrf),
        Adoption(("vpc_pairs",), {"fabric": "F1", "switch": "A", "peer": "B"}),
        Adoption(("tor_pairs",), {"fabric": "F1", "tor": "T", "leaf": "A", "peer": "B"}),
    ]
    assert write_adoptions(path, adoptions) == 4
    text = path.read_text(encoding="utf-8")
    assert "# first" in text
    doc = yaml.safe_load(text)
    assert doc["fabrics"][0]["generated_links"][0]["owner"] == "MSD"
    assert doc["overlay"]["vrfs"] == [vrf]
    assert doc["vpc_pairs"] == [{"fabric": "F1", "switch": "A", "peer": "B"}]
    assert doc["tor_pairs"][0]["tor"] == "T"
    assert write_adoptions(path, adoptions) == 0


def test_write_adoptions_merges_defaults_mapping(tmp_path):
    path = copy_topology(tmp_path)
    first = Adoption(("fabrics", "SITE1", "defaults"), {"spine": {"policyType": "routedHost", "mtu": "9216"}})
    assert write_adoptions(path, [first]) == 1
    second = Adoption(("fabrics", "SITE1", "defaults"), {"spine": {"policyType": "other"}, "leaf": {"policyType": "trunkHost"}})
    assert write_adoptions(path, [second]) == 1
    defaults = site1(yaml.safe_load(path.read_text(encoding="utf-8")))["defaults"]
    assert defaults == {"spine": {"policyType": "routedHost", "mtu": "9216"}, "leaf": {"policyType": "trunkHost"}}


def test_write_adoptions_rejects_unknown_section(tmp_path):
    path = copy_topology(tmp_path)
    before = path.read_text(encoding="utf-8")
    for section in (("bogus",), ("fabrics", "SITE1", "nope"), ("fabrics", "NOPE", "links"), ("overlay", "nope")):
        with pytest.raises(ValueError):
            write_adoptions(path, [Adoption(section, {})])
    assert path.read_text(encoding="utf-8") == before


def test_bootstrap_adoptions_capture_generated_links_and_defaults():
    topo = load(BASE / "topology_nd421_base.yaml")
    live = read_live_from_snapshot(GOLDEN / "nd421", topo)
    adoptions = bootstrap_adoptions(topo, live, compute(topo, live))
    generated = [a.entry | {"fabric": a.section[1]} for a in adoptions if a.section[-1] == "generated_links"]
    # The snapshot holds three ND-generated links the shipped yaml does not list: the BG underlay and overlay pair, and the campus link.
    assert len(generated) == 3
    underlay = next(e for e in generated if e["policy"] == "multisiteUnderlay")
    assert underlay["owner"] == "MSD"
    assert (underlay["src"], underlay["src_if"], underlay["dst"], underlay["dst_if"]) == ("S1_BG1", "Ethernet1/1", "S2_BG1", "Ethernet1/1")
    assert {(underlay["src"], underlay["src_if"]), (underlay["dst"], underlay["dst_if"])} == {("S1_BG1", "Ethernet1/1"), ("S2_BG1", "Ethernet1/1")}
    assert next(e for e in generated if e["policy"] == "multisiteOverlay")["owner"] == "MSD"
    campus = next(e for e in generated if e["policy"] == "iosXeNumbered")
    assert (campus["owner"], campus["fabric"]) == ("CAMPUS1", "CAMPUS1")
    defaults = {a.section[1]: a.entry for a in adoptions if a.section[-1] == "defaults"}
    assert defaults["SITE1"]["spine"]["policyType"] == "routedHost"
    assert defaults["SITE1"]["leaf"]["policyType"] == "trunkHost"
    assert defaults["SITE1"]["borderGateway"]["policyType"] == "routedHost"
    assert "ISN" not in defaults
    conflicts = bootstrap_conflicts(topo, live)
    assert len(conflicts) == 1
    for text in ("WAN1", "GigabitEthernet2", "S1_BG1", "Ethernet1/3", "multisiteUnderlay", "ebgpVrfLite"):
        assert text in conflicts[0]


@pytest.mark.parametrize("name", ["topology_nd421.yaml", "topology_nd431.yaml"])
def test_round_trip_of_shipped_files_is_byte_identical_without_adoptions(tmp_path, name):
    path = copy_topology(tmp_path, name)
    before = path.read_bytes()
    assert write_adoptions(path, []) == 0
    assert path.read_bytes() == before
    first = load(path).fabrics[0].switches[0]
    existing = Adoption(("fabrics", "SITE1", "switches"), {"hostname": first.hostname, "ip": first.ip, "role": first.role})
    assert write_adoptions(path, [existing]) == 0
    assert path.read_bytes() == before


def test_defaults_use_the_majority_signature_not_the_first_port():
    topo = load(BASE / "topology_nd421_base.yaml")
    live = read_live_from_snapshot(GOLDEN / "nd421", topo)
    defaults = {a.section[1]: a.entry for a in bootstrap_adoptions(topo, live, []) if a.section[-1] == "defaults"}
    assert defaults["SITE1"]["tor"]["policyType"] == "trunkHost"
    assert "description" not in defaults["SITE1"]["tor"]
    assert defaults["SITE1"]["spine"]["policyType"] == "routedHost"
    assert defaults["SITE1"]["leaf"]["policyType"] == "trunkHost"

    def port(name: str, description: str) -> dict:
        policy = {"policyType": "trunkHost", "description": description}
        return {"interfaceName": name, "interfaceType": "ethernet", "operData": {"portChannelId": -1}, "configData": {"networkOS": {"policy": policy}}}

    fabric = next(f for f in topo.fabrics if f.name == "SITE1")
    leaf = next(s.hostname for s in fabric.switches if s.role == "leaf")
    synthetic = {
        "SITE1": replace(live["SITE1"], interfaces={leaf: [port("Ethernet1/40", "x"), port("Ethernet1/41", ""), port("Ethernet1/42", "x"), port("Ethernet1/43", "x")]})
    }
    topo_one = replace(topo, fabrics=[replace(fabric, switches=[s for s in fabric.switches if s.hostname == leaf])])
    result = bootstrap_adoptions(topo_one, synthetic, [])
    assert result[-1].entry["leaf"] == {"policyType": "trunkHost", "description": "x"}


def test_defaults_policy_type_comes_from_the_table_not_the_vote():
    topo = load(BASE / "topology_nd431_base.yaml")
    live = read_live_from_snapshot(GOLDEN / "nd431", topo)
    spine = next(s.hostname for s in topo.fabrics[0].switches if s.role == "spine")
    all_links = [link for fab in live.values() for link in fab.links]
    ports = free_ports(live["SITE1"], spine, all_links)
    assert ports and {p["configData"]["networkOS"]["policy"]["policyType"] for p in ports} == {"trunkHost"}  # the residue the vote used to pick
    defaults = {a.section[1]: a.entry for a in bootstrap_adoptions(topo, live, []) if a.section[-1] == "defaults"}
    assert defaults["SITE1"]["spine"] == {"policyType": "routedHost", "adminState": "true", "mtu": "9216"}  # inputs from sibling SITE2
    assert defaults["SITE1"]["borderGateway"] == {"policyType": "routedHost", "adminState": "true", "mtu": "9216"}
    assert defaults["SITE1"]["leaf"] == {"policyType": "trunkHost", "adminState": "true", "allowedVlans": "none", "mtu": "jumbo"}
    assert defaults["SITE1"]["tor"]["policyType"] == "trunkHost"
    assert defaults["SITE2"]["spine"] == {"policyType": "routedHost", "adminState": "true", "mtu": "9216"}
    assert defaults["CAMPUS1"]["spine"]["policyType"] == "iosXeRoutedHost"
    assert defaults["CAMPUS1"]["leaf"]["policyType"] == "iosXeTrunkHost"


def test_bootstrap_adopts_interface_residue_in_the_same_run():
    topo = load(BASE / "topology_nd421_base.yaml")
    live = read_live_from_snapshot(GOLDEN / "nd421", topo)
    interfaces = [a.entry for a in bootstrap_adoptions(topo, live, compute(topo, live)) if a.section[-1] == "interfaces"]
    access = {(e["switch"], e["interface"]) for e in interfaces if e["policy"] == "accessHost"}
    assert {("S1_TOR1", "Ethernet1/3"), ("S2_LE1", "Ethernet1/2")} <= access
    assert sum(1 for e in interfaces if e["switch"] == "S1_BG1" and e["policy"] == "trunkHost") >= 19


def test_links_are_written_spine_first_and_sorted(tmp_path):
    path = tmp_path / "t.yaml"
    path.write_text(
        "fabrics:\n  - name: F1\n    type: vxlanIbgp\n    asn: '1'\n    switches:\n"
        "      - {hostname: SP1, ip: 1.1.1.1, role: spine}\n      - {hostname: LE1, ip: 1.1.1.2, role: leaf}\n      - {hostname: LE2, ip: 1.1.1.3, role: leaf}\n"
        "    links:\n      - {src: SP1, src_if: Ethernet1/9, dst: LE1, dst_if: Ethernet1/9, policy: numbered, src_ip: 9.9.9.1, dst_ip: 9.9.9.2}\n",
        encoding="utf-8",
    )
    adoptions = [
        Adoption(
            ("fabrics", "F1", "links"),
            {"src": "LE2", "src_if": "Ethernet1/1", "dst": "SP1", "dst_if": "Ethernet1/3", "policy": "numbered", "src_ip": "10.0.0.6", "dst_ip": "10.0.0.5"},
        ),
        Adoption(
            ("fabrics", "F1", "links"),
            {"src": "LE1", "src_if": "Ethernet1/1", "dst": "SP1", "dst_if": "Ethernet1/2", "policy": "numbered", "src_ip": "10.0.0.2", "dst_ip": "10.0.0.1"},
        ),
    ]
    assert write_adoptions(path, adoptions) == 2
    links = yaml.safe_load(path.read_text(encoding="utf-8"))["fabrics"][0]["links"]
    assert links[0]["src_if"] == "Ethernet1/9"  # hand-written entry first and untouched
    assert links[1:] == [
        {"src": "SP1", "src_if": "Ethernet1/2", "dst": "LE1", "dst_if": "Ethernet1/1", "policy": "numbered", "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2"},
        {"src": "SP1", "src_if": "Ethernet1/3", "dst": "LE2", "dst_if": "Ethernet1/1", "policy": "numbered", "src_ip": "10.0.0.5", "dst_ip": "10.0.0.6"},
    ]


def test_default_inputs_fall_back_to_a_sibling_fabric():
    topo = load(BASE / "topology_nd431_base.yaml")
    live = read_live_from_snapshot(GOLDEN / "nd431", topo)
    defaults = {a.section[1]: a.entry for a in bootstrap_adoptions(topo, live, []) if a.section[-1] == "defaults"}
    expected = {"policyType": "routedHost", "adminState": "true", "mtu": "9216"}
    assert defaults["SITE1"]["spine"] == expected == defaults["SITE2"]["spine"]
    assert defaults["SITE1"]["borderGateway"] == expected
