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
