"""golden_live must read every golden fabric and group from a snapshot dump, and fail loud on a broken live controller."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from golden_live import LiveReadError, free_ports, interface_path, read_live, read_live_from_snapshot
from topology import load

HERE = Path(__file__).resolve().parents[1]
GOLDEN = HERE / "golden"


class StubClient:
    def __init__(self, responses: dict | None = None, error: str | None = None) -> None:
        self.creds = SimpleNamespace(ip="192.0.2.1")
        self.responses = responses or {}
        self.error = error

    def get(self, path: str, params: dict | None = None):
        if self.error:
            raise RuntimeError(self.error)
        return self.responses.get(path, {})

    def post(self, path: str, json=None, timeout=None):
        return {}

    def paged(self, path: str, key: str, params: dict | None = None, page: int = 100):
        return []


def _live():
    topo = load(HERE / "topology_nd421.yaml")
    return read_live_from_snapshot(GOLDEN / "nd421", topo)


def test_read_live_from_snapshot_loads_every_golden_fabric_and_group():
    live = _live()
    assert set(live) == {"SITE1", "SITE2", "ISN", "CAMPUS1", "MSD"} and live["MSD"].category == "fabricGroup"
    assert live["SITE1"].switches["S1_SP1"]["switchRole"] == "spine" and len(live["SITE1"].interfaces["S1_SP1"]) > 40
    assert all(a["attach"] for a in live["SITE1"].vrf_attachments) and live["SITE1"].vrf_attachments


def test_free_ports_exclude_link_endpoints_and_port_channel_members():
    live = _live()
    all_links = [link for fabric in live.values() for link in fabric.links]
    names = {p["interfaceName"] for p in free_ports(live["SITE1"], "S1_SP1", all_links)}
    assert "Ethernet1/1" not in names and "Ethernet1/6" in names
    assert not {"Ethernet1/1", "Ethernet1/2", "Ethernet1/3"} & {p["interfaceName"] for p in free_ports(live["SITE1"], "S1_LE1", all_links)}


def test_interface_paths_encode_the_slash():
    assert interface_path("SITE1", "SN1", "Ethernet1/3") == "/fabrics/SITE1/switches/SN1/interfaces/Ethernet1%2F3"


def test_read_live_fails_loud_when_fabric_controller_is_down():
    client = StubClient(error="HTTP 500 Error communicating with fabric controller")
    with pytest.raises(LiveReadError, match="fabric controller"):
        read_live(client, load(HERE / "topology_nd421.yaml"))


def test_read_live_fails_loud_when_a_golden_fabric_is_missing():
    client = StubClient({"/fabrics": []})
    with pytest.raises(LiveReadError, match="SITE1"):
        read_live(client, load(HERE / "topology_nd421.yaml"))
