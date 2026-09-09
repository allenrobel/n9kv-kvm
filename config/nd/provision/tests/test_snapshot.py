"""Tests for snapshot.normalize (hostname mapping, volatile-key stripping, stable list order) and snapshot.dump
(one broken read must not abort the rest of the dump)."""

import json

from snapshot import dump, normalize


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


class _StubClient:
    """Minimal NDClient stand-in for snapshot.dump: get()/post() answer from `responses` keyed by
    (path, sorted params) for GET/paged and by bare path for POST; any key listed in `fail_keys` raises
    RuntimeError("HTTP 404") instead, modeling one broken read among many working ones."""

    def __init__(self, responses: dict, fail_keys: set) -> None:
        self.responses = responses
        self.fail_keys = fail_keys

    @staticmethod
    def _key(path, params):
        return (path, tuple(sorted((params or {}).items())))

    def get(self, path, params=None):
        key = self._key(path, params)
        if key in self.fail_keys:
            raise RuntimeError("HTTP 404")
        return self.responses.get(key)

    def post(self, path, json=None):
        if path in self.fail_keys:
            raise RuntimeError("HTTP 404")
        return self.responses.get(path)

    def paged(self, path, key, params=None, page=100):
        pkey = self._key(path, params)
        if pkey in self.fail_keys:
            raise RuntimeError("HTTP 404")
        return self.responses.get(pkey, [])


def test_dump_writes_null_for_a_failing_read_and_still_writes_the_rest(tmp_path):
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": "SITE1"}]},
        ("/inventory/switches", ()): {"switches": []},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
        ("/fabrics/SITE1", ()): {"name": "SITE1"},
        ("/fabrics/SITE1/switches", ()): {"switches": []},
        ("/fabrics/SITE1/members", ()): {"fabrics": []},
        ("/fabrics/SITE1/networks", ()): {"networks": []},
    }
    fail_keys = {("/fabrics/SITE1/vrfs", ())}
    client = _StubClient(responses, fail_keys)

    dump(client, tmp_path)

    assert json.loads((tmp_path / "vrfs_SITE1.json").read_text()) is None
    assert json.loads((tmp_path / "networks_SITE1.json").read_text()) == {"networks": []}
    assert json.loads((tmp_path / "fabric_SITE1.json").read_text()) == {"name": "SITE1"}
    assert json.loads((tmp_path / "fabrics.json").read_text()) == {"fabrics": [{"name": "SITE1"}]}


def test_normalize_maps_hostnames_adjacent_to_underscores_but_not_longer_names():
    name_map = {"S1_BG1": "S3_BG1", "S1_LE1": "S3_LE1"}
    assert normalize("interfaces_SITE1_S1_BG1.json", name_map) == "interfaces_SITE1_S3_BG1.json"
    assert normalize("tap_S1_LE1 S1_BG1 S1_BG10", name_map) == "tap_S3_LE1 S3_BG1 S1_BG10"
