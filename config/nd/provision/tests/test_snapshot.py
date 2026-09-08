"""Tests for snapshot.normalize: hostname mapping, volatile-key stripping, stable list order."""

from snapshot import normalize


def test_normalize_maps_hostnames_and_drops_volatile_keys():
    src = {
        "switches": [
            {"hostname": "S2_BG1", "serialNumber": "9ABC", "fabricManagementIp": "192.168.12.132", "switchRole": "borderGateway"},
            {"hostname": "S1_BG1", "serialNumber": "9DEF", "fabricManagementIp": "192.168.12.131", "switchRole": "borderGateway"},
        ],
        "meta": {"counts": {"total": 2}},
    }
    out = normalize(src, {"S1_BG1": "S3_BG1", "S2_BG1": "S4_BG1"})
    assert out == {"switches": [{"hostname": "S3_BG1", "switchRole": "borderGateway"}, {"hostname": "S4_BG1", "switchRole": "borderGateway"}]}


def test_normalize_rewrites_names_embedded_in_strings():
    out = normalize({"description": "connected-to-S1_BG1-Ethernet1/3", "source": "LINK-UUID-7850"}, {"S1_BG1": "S3_BG1"})
    assert out == {"description": "connected-to-S3_BG1-Ethernet1/3"}
