"""golden_adopt: comment-preserving yaml writes of adoptions and the bootstrap adoption set, against the committed nd421 snapshot."""

import re
from dataclasses import replace
import shutil
from pathlib import Path

import pytest
import yaml

from golden_adopt import bootstrap_adoptions, bootstrap_conflicts, write_adoptions
from golden_drift import Adoption, compute
from golden_live import read_live_from_snapshot
from topology import load

HERE = Path(__file__).resolve().parents[1]
GOLDEN = HERE / "golden"

LINK = {"src": "S1_SP1", "src_if": "Ethernet1/9", "dst": "S1_LE1", "dst_if": "Ethernet1/9", "policy": "numbered", "src_ip": "10.14.1.1", "dst_ip": "10.14.1.2"}
IFACE = {"switch": "S1_LE1", "interface": "Ethernet1/20", "policy": "trunkHost", "description": "adopted", "inputs": {"allowedVlans": "2"}}


def comment_lines(text: str) -> set[str]:
    return {m.group(0).strip() for m in re.finditer(r"#.*$", text, re.MULTILINE)}


def site1(doc: dict) -> dict:
    return next(f for f in doc["fabrics"] if f["name"] == "SITE1")


def copy_topology(tmp_path: Path, name: str = "topology_nd421.yaml") -> Path:
    path = tmp_path / name
    shutil.copy(HERE / name, path)
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
    topo = load(HERE / "topology_nd421.yaml")
    live = read_live_from_snapshot(GOLDEN / "nd421", topo)
    adoptions = bootstrap_adoptions(topo, live, compute(topo, live))
    generated = [a.entry | {"fabric": a.section[1]} for a in adoptions if a.section[-1] == "generated_links"]
    # The snapshot holds three ND-generated links the shipped yaml does not list: the BG underlay and overlay pair, and the campus link.
    assert len(generated) == 3
    underlay = next(e for e in generated if e["policy"] == "multisiteUnderlay")
    assert underlay["owner"] == "MSD"
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
    topo = load(HERE / "topology_nd421.yaml")
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
