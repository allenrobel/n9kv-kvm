"""topology.load must reject dangling references and accept the two shipped files."""

from pathlib import Path

import pytest

from topology import load

HERE = Path(__file__).resolve().parents[1]


def test_shipped_topologies_load_and_mirror():
    t421 = load(HERE / "topology_nd421.yaml")
    t431 = load(HERE / "topology_nd431.yaml")
    assert [f.name for f in t421.fabrics] == [f.name for f in t431.fabrics] == ["SITE1", "SITE2", "ISN", "CAMPUS1"]
    assert t421.fabric_groups[0].members == t431.fabric_groups[0].members == ["SITE1", "SITE2", "ISN"]
    assert t421.switch_fabric("S1_BG1") == "SITE1" and t431.switch_fabric("S3_BG1") == "SITE1"
    assert t421.switch_fabric("C1_LE1") == "CAMPUS1" and t431.switch_fabric("C3_LE1") == "CAMPUS1"
    campus421, campus431 = t421.fabrics[3], t431.fabrics[3]
    assert campus421.type == campus431.type == "vxlanCampus" and campus421.asn == campus431.asn == "65003"
    assert campus421.settings == campus431.settings
    assert [(s.role, s.platform) for s in campus421.switches] == [(s.role, s.platform) for s in campus431.switches] == [("leaf", "ios-xe")]
    assert [s.ip for s in campus421.switches] == ["192.168.12.181"] and [s.ip for s in campus431.switches] == ["192.168.14.181"]
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


def test_shipped_topologies_declare_the_site1_tor_pair():
    t421 = load(HERE / "topology_nd421.yaml")
    t431 = load(HERE / "topology_nd431.yaml")
    assert [(p.fabric, p.tor, p.leaf, p.peer) for p in t421.tor_pairs] == [("SITE1", "S1_TOR1", "S1_LE1", "S1_LE2")]
    assert [(p.fabric, p.tor, p.leaf, p.peer) for p in t431.tor_pairs] == [("SITE1", "S3_TOR1", "S3_LE1", "S3_LE2")]
    # ND 4.2.1 recommends no ids (resources: {} in every query form, lab-verified 2026-09-14), so the files carry them.
    assert (
        t421.tor_pairs[0].resources()
        == t431.tor_pairs[0].resources()
        == {
            "accessOrTorPortChannelId": 1,
            "aggregationOrLeafPortChannelId": 1,
            "aggregationOrLeafPeerPortChannelId": 1,
            "aggregationOrLeafVpcId": 1,
        }
    )


def test_tor_pair_without_ids_has_no_resources(tmp_path):
    good = tmp_path / "t.yaml"
    good.write_text(_TOR_FABRIC + "vpc_pairs:\n  - {fabric: SITE1, switch: LE1, peer: LE2}\ntor_pairs:\n  - {fabric: SITE1, tor: TOR1, leaf: LE1, peer: LE2}\n")
    assert load(good).tor_pairs[0].resources() == {}


def test_tor_pair_peer_po_and_vpc_id_default_to_the_leaf_po(tmp_path):
    good = tmp_path / "t.yaml"
    good.write_text(
        _TOR_FABRIC
        + "vpc_pairs:\n  - {fabric: SITE1, switch: LE1, peer: LE2}\ntor_pairs:\n  - {fabric: SITE1, tor: TOR1, leaf: LE1, peer: LE2, tor_po: 7, leaf_po: 8}\n"
    )
    assert load(good).tor_pairs[0].resources() == {
        "accessOrTorPortChannelId": 7,
        "aggregationOrLeafPortChannelId": 8,
        "aggregationOrLeafPeerPortChannelId": 8,
        "aggregationOrLeafVpcId": 8,
    }


def test_tor_pair_rejects_only_one_of_the_two_required_ids(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(
        _TOR_FABRIC + "vpc_pairs:\n  - {fabric: SITE1, switch: LE1, peer: LE2}\ntor_pairs:\n  - {fabric: SITE1, tor: TOR1, leaf: LE1, peer: LE2, tor_po: 7}\n"
    )
    with pytest.raises(ValueError, match="tor_pairs: TOR1: tor_po and leaf_po must be given together"):
        load(bad)


_TOR_FABRIC = (
    "fabrics:\n  - name: SITE1\n    type: vxlanIbgp\n    asn: '65001'\n"
    "    switches: [{hostname: LE1, ip: 10.0.0.1, role: leaf}, {hostname: LE2, ip: 10.0.0.2, role: leaf}, {hostname: TOR1, ip: 10.0.0.3, role: tor}]\n"
    "  - name: SITE2\n    type: vxlanIbgp\n    asn: '65002'\n    switches: [{hostname: LE9, ip: 10.0.0.9, role: leaf}]\n"
    "fabric_groups: []\nisn: {}\noverlay: {}\n"
)


def test_tor_pair_unknown_switch_is_rejected(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(_TOR_FABRIC + "vpc_pairs:\n  - {fabric: SITE1, switch: LE1, peer: LE2}\ntor_pairs:\n  - {fabric: SITE1, tor: TOR9, leaf: LE1, peer: LE2}\n")
    with pytest.raises(ValueError, match="tor_pairs: unknown switch TOR9"):
        load(bad)


def test_tor_pair_must_reference_switches_of_its_own_fabric(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(_TOR_FABRIC + "vpc_pairs:\n  - {fabric: SITE1, switch: LE1, peer: LE2}\ntor_pairs:\n  - {fabric: SITE1, tor: TOR1, leaf: LE1, peer: LE9}\n")
    with pytest.raises(ValueError, match="tor_pairs: LE9 is not in fabric SITE1"):
        load(bad)


def test_tor_pair_leafs_must_be_a_declared_vpc_pair(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(_TOR_FABRIC + "vpc_pairs: []\ntor_pairs:\n  - {fabric: SITE1, tor: TOR1, leaf: LE1, peer: LE2}\n")
    with pytest.raises(ValueError, match="tor_pairs: LE1/LE2 is not declared under vpc_pairs"):
        load(bad)


def test_tor_pair_accepts_the_vpc_pair_in_either_order(tmp_path):
    good = tmp_path / "t.yaml"
    good.write_text(_TOR_FABRIC + "vpc_pairs:\n  - {fabric: SITE1, switch: LE2, peer: LE1}\ntor_pairs:\n  - {fabric: SITE1, tor: TOR1, leaf: LE1, peer: LE2}\n")
    assert load(good).tor_pairs[0].tor == "TOR1"


def test_shipped_topologies_attach_lab_net1_to_the_tor_host_port_in_access_mode():
    """S1_H1 / S3_H1 hang off the ToR's Ethernet1/3; the ToR is its own attachment row (no ToR-port field on the leaf row in ND 4.x)."""
    for fn, tor in (("topology_nd421.yaml", "S1_TOR1"), ("topology_nd431.yaml", "S3_TOR1")):
        topo = load(HERE / fn)
        rows = [a for a in topo.overlay.network_attachments if a["switch"] == tor]
        assert rows == [{"fabric": "SITE1", "network": "LAB_NET1", "switch": tor, "vlan": 2, "interfaces": [{"mode": "access", "interfaceRange": "Ethernet1/3"}]}]
        assert any(p.tor == tor for p in topo.tor_pairs), f"{tor} must be paired before its host port is attached"
