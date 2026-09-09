"""topology.load must reject dangling references and accept the two shipped files."""

from pathlib import Path

import pytest

from topology import load

HERE = Path(__file__).resolve().parents[1]


def test_shipped_topologies_load_and_mirror():
    t421 = load(HERE / "topology_nd421.yaml")
    t431 = load(HERE / "topology_nd431.yaml")
    assert [f.name for f in t421.fabrics] == [f.name for f in t431.fabrics] == ["SITE1", "SITE2", "ISN"]
    assert t421.fabric_groups[0].members == t431.fabric_groups[0].members == ["SITE1", "SITE2", "ISN"]
    assert t421.switch_fabric("S1_BG1") == "SITE1" and t431.switch_fabric("S3_BG1") == "SITE1"
    assert len(t421.isn.links) == len(t431.isn.links) == 2
    assert t421.overlay.networks == t431.overlay.networks  # identical overlay objects, only attachments name different switches


def test_dangling_switch_reference_is_rejected(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(
        "fabrics:\n  - name: SITE1\n    type: vxlanIbgp\n    asn: '65001'\n    switches: []\n"
        "fabric_groups: []\nisn:\n  links:\n    - {src_fabric: ISN, src: WAN9, src_if: Gi2, dst_fabric: SITE1, dst: S1_BG1, dst_if: Eth1/3,"
        " src_asn: '1', dst_asn: '2', src_ip: 10.0.0.1/30, dst_ip: 10.0.0.2, mtu: 9000}\n  wan: {hostname: WAN9, fabric: ISN}\noverlay: {}\n"
    )
    with pytest.raises(ValueError, match="WAN9"):
        load(bad)


def test_overlay_attachment_missing_switch_key_is_rejected(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(
        "fabrics:\n  - name: SITE1\n    type: vxlanIbgp\n    asn: '65001'\n"
        "    switches: [{hostname: S1_BG1, ip: 10.0.0.1, role: borderGateway}]\n"
        "fabric_groups: []\nisn: {}\noverlay: {vrf_attachments: [{fabric: SITE1, vrf: V1}]}\n"
    )
    with pytest.raises(ValueError, match="SITE1"):
        load(bad)


def test_switch_hostname_declared_in_two_fabrics_is_rejected(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(
        "fabrics:\n"
        "  - name: SITE1\n    type: vxlanIbgp\n    asn: '65001'\n"
        "    switches: [{hostname: S1_BG1, ip: 10.0.0.1, role: borderGateway}]\n"
        "  - name: SITE2\n    type: vxlanIbgp\n    asn: '65002'\n"
        "    switches: [{hostname: S1_BG1, ip: 10.0.0.2, role: borderGateway}]\n"
        "fabric_groups: []\nisn: {}\noverlay: {}\n"
    )
    with pytest.raises(ValueError, match="S1_BG1"):
        load(bad)


def test_shipped_topologies_declare_the_two_site1_vpc_pairs():
    t421 = load(HERE / "topology_nd421.yaml")
    t431 = load(HERE / "topology_nd431.yaml")
    assert [(p.fabric, p.switch, p.peer) for p in t421.vpc_pairs] == [("SITE1", "S1_LE1", "S1_LE2"), ("SITE1", "S1_LE3", "S1_LE4")]
    assert [(p.fabric, p.switch, p.peer) for p in t431.vpc_pairs] == [("SITE1", "S3_LE1", "S3_LE2"), ("SITE1", "S3_LE3", "S3_LE4")]


def test_vpc_pair_must_reference_switches_of_its_own_fabric(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(
        "fabrics:\n  - name: SITE1\n    type: vxlanIbgp\n    asn: '65001'\n    switches: [{hostname: A, ip: 10.0.0.1, role: leaf}]\n"
        "  - name: SITE2\n    type: vxlanIbgp\n    asn: '65002'\n    switches: [{hostname: B, ip: 10.0.0.2, role: leaf}]\n"
        "fabric_groups: []\nisn: {}\noverlay: {}\nvpc_pairs:\n  - {fabric: SITE1, switch: A, peer: B}\n"
    )
    with pytest.raises(ValueError, match="B is not in fabric SITE1"):
        load(bad)
