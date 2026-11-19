"""golden_live must read every golden fabric and group from a snapshot dump, and fail loud on a broken live controller."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from golden_live import LiveReadError, free_ports, interface_path, read_live, read_live_from_snapshot
from topology import load

HERE = Path(__file__).resolve().parents[1]
SNAPSHOTS = HERE / "tests" / "fixtures" / "snapshots"  # dumps frozen with the *_base.yaml topologies; golden/ holds the current reference dumps


class StubClient:
    def __init__(self, responses: dict | None = None, error: str | None = None, errors: dict | None = None) -> None:
        self.calls: list[tuple] = []
        self.errors = errors or {}
        self.creds = SimpleNamespace(ip="192.0.2.1")
        self.responses = responses or {}
        self.error = error

    def get(self, path: str, params: dict | None = None):
        self.calls.append((path, params))
        if path in self.errors:
            raise RuntimeError(self.errors[path])
        if self.error:
            raise RuntimeError(self.error)
        return self.responses.get(path, {})

    def post(self, path: str, json=None, timeout=None):
        return {}

    def paged(self, path: str, key: str, params: dict | None = None, page: int = 100):
        return []


MODE_BODIES = {f"/fabrics/{f}": {"management": {"replicationMode": "multicast"}} for f in ("SITE1", "SITE2")}  # the mode fabrics' settings


def _live():
    topo = load(HERE / "topology_nd421.yaml", replication_mode="multicast")
    return read_live_from_snapshot(SNAPSHOTS / "nd421", topo)


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
        read_live(client, load(HERE / "topology_nd421.yaml", replication_mode="multicast"))


def test_read_live_fails_loud_when_a_golden_fabric_is_missing():
    client = StubClient({"/fabrics": []})
    with pytest.raises(LiveReadError, match="SITE1"):
        read_live(client, load(HERE / "topology_nd421.yaml", replication_mode="multicast"))


def _tor_stub(**kwargs):
    topo = load(HERE / "topology_nd421.yaml", replication_mode="multicast")
    site1 = next(f for f in topo.fabrics if f.name == "SITE1")
    switches = [{"hostname": s.hostname, "serialNumber": f"SN_{s.hostname}"} for s in site1.switches]
    responses = {
        "/fabrics": [{"name": n} for n in [*(f.name for f in topo.fabrics), *(g.name for g in topo.fabric_groups)]],
        "/fabrics/SITE1/switches": {"switches": switches},
        **MODE_BODIES,
    }
    responses.update(kwargs.pop("responses", {}))
    return topo, StubClient(responses, **kwargs)


def test_read_live_reads_tor_associations_per_golden_pair():
    path = "/fabrics/SITE1/accessAssociations"
    topo, client = _tor_stub(responses={path: {"associations": [{"id": 1}]}})
    pair = next(p for p in topo.tor_pairs if p.fabric == "SITE1")
    live = read_live(client, topo)
    assert live["SITE1"].tor_associations == [{"id": 1}]
    assert (path, {"aggregationOrLeafSwitchId": f"SN_{pair.leaf}", "aggregationOrLeafPeerSwitchId": f"SN_{pair.peer}"}) in client.calls


def test_tor_association_400_reads_as_empty():
    path = "/fabrics/SITE1/accessAssociations"
    topo, client = _tor_stub(errors={path: f"GET {path} -> HTTP 400: aggregationOrLeafSwitchId is required"})
    assert read_live(client, topo)["SITE1"].tor_associations == []
    with pytest.raises(LiveReadError):
        read_live(StubClient(error="HTTP 500 boom"), topo)


def test_free_ports_match_link_endpoints_case_insensitively():
    live = _live()
    all_links = [
        {**link, "srcInterfaceName": link["srcInterfaceName"].lower(), "dstInterfaceName": link["dstInterfaceName"].upper()} for f in live.values() for link in f.links
    ]
    names = {p["interfaceName"] for p in free_ports(live["SITE1"], "S1_SP1", all_links)}
    assert "Ethernet1/1" not in names and "Ethernet1/6" in names


def test_tor_association_transport_error_is_a_live_read_error():
    """A dropped connection on the per-pair accessAssociations read maps to LiveReadError like every other live read."""
    import requests

    path = "/fabrics/SITE1/accessAssociations"
    topo, client = _tor_stub()
    original = client.get

    def get(p, params=None):
        if p == path:
            raise requests.ConnectionError("boom")
        return original(p, params)

    client.get = get
    with pytest.raises(LiveReadError, match="accessAssociations"):
        read_live(client, topo)


def _mode_stub(policy_rows):
    topo = load(HERE / "topology_nd421.yaml", replication_mode="multicast")
    site1 = next(f for f in topo.fabrics if f.name == "SITE1")
    switches = [{"hostname": s.hostname, "serialNumber": f"SN_{s.hostname}"} for s in site1.switches]
    first, second = switches[0], switches[1]
    responses = {
        "/fabrics": [{"name": n} for n in [*(f.name for f in topo.fabrics), *(g.name for g in topo.fabric_groups)]],
        "/fabrics/SITE1/switches": {"switches": switches},
        "/fabrics/MSD/members": {"fabrics": [{"name": "SITE1"}, {"name": "SITE2"}]},
        **MODE_BODIES,
        f"/fabrics/SITE1/switches/{first['serialNumber']}/pendingConfig": {"pendingConfigs": ["a", "b"]},
    }

    class Client(StubClient):
        def paged(self, path, key, params=None, page=100):
            self.calls.append((path, params))
            return policy_rows(first, second) if path == "/fabrics/SITE1/policies" else []

    return topo, Client(responses), first, second


def test_read_live_reads_group_members_mode_policies_and_pending():
    def rows(first, second):
        return [
            {"switchId": first["serialNumber"], "templateName": "base_multicast_11_1"},
            {"switchId": first["serialNumber"], "templateName": "some_other_template"},
            {"switchId": second["serialNumber"], "templateName": "ingress_rep_simulated"},
            {"switchId": "SN_UNKNOWN", "templateName": "base_pim_asm_v6"},
        ]

    topo, client, first, second = _mode_stub(rows)
    live = read_live(client, topo)
    assert live["MSD"].members == ["SITE1", "SITE2"]
    assert live["SITE1"].members == []
    assert live["SITE1"].mode_policies[first["hostname"]] == {"base_multicast_11_1"}
    assert live["SITE1"].mode_policies[second["hostname"]] == {"ingress_rep_simulated"}
    assert "SN_UNKNOWN" not in live["SITE1"].mode_policies
    assert live["SITE1"].pending[first["hostname"]] == 2 and live["SITE1"].pending[second["hostname"]] == 0
    assert live["ISN"].mode_policies is None and live["ISN"].pending is None
    assert not any(c[0] == "/fabrics/ISN/policies" for c in client.calls)


def test_read_live_groups_policies_by_switch_when_the_filter_is_ignored():
    """ND 4.3.1 returns every switch's rows whatever the filter says."""

    def rows(first, second):
        return [{"switchId": second["serialNumber"], "templateName": "base_pim_asm_v6"}]

    topo, client, first, second = _mode_stub(rows)
    policies = read_live(client, topo)["SITE1"].mode_policies
    assert policies[first["hostname"]] == set() and policies[second["hostname"]] == {"base_pim_asm_v6"}


def test_read_live_modeless_topology_makes_no_per_mode_reads():
    topo, client, _, _ = _mode_stub(lambda a, b: [])
    modeless = load(HERE / "tests" / "fixtures" / "topology_nd421_base.yaml")
    assert modeless.mode_fabrics == ()
    live = read_live(client, modeless)
    assert all(f.mode_policies is None and f.pending is None for f in live.values())


def test_read_live_policies_failure_is_a_live_read_error():
    topo, client, _, _ = _mode_stub(lambda a, b: [])

    def paged(path, key, params=None, page=100):
        raise RuntimeError("GET policies -> HTTP 500")

    client.paged = paged
    with pytest.raises(LiveReadError, match="policies"):
        read_live(client, topo)


def test_read_live_pending_transport_error_is_a_live_read_error():
    import requests

    topo, client, first, _ = _mode_stub(lambda a, b: [])
    original = client.get
    path = f"/fabrics/SITE1/switches/{first['serialNumber']}/pendingConfig"

    def get(p, params=None):
        if p == path:
            raise requests.ConnectionError("boom")
        return original(p, params)

    client.get = get
    with pytest.raises(LiveReadError, match="pendingConfig"):
        read_live(client, topo)


def test_snapshot_read_fills_members_and_leaves_mode_fields_none():
    live = _live()
    assert live["MSD"].members == ["ISN", "SITE1", "SITE2"]
    assert live["SITE1"].members == []
    assert all(f.mode_policies is None and f.pending is None for f in live.values())


@pytest.mark.parametrize("body", [{}, {"management": {}}, {"management": {"replicationMode": "bogus"}}])
def test_read_live_mode_fabric_without_a_valid_mode_is_a_live_read_error(body):
    topo, client, _, _ = _mode_stub(lambda a, b: [])
    client.responses["/fabrics/SITE2"] = body
    with pytest.raises(LiveReadError, match=r"SITE2.*replicationMode"):
        read_live(client, topo)


def test_read_live_mode_check_skips_non_mode_fabrics_and_modeless_topologies():
    topo, client, _, _ = _mode_stub(lambda a, b: [])
    assert "/fabrics/ISN" not in client.responses and "ISN" not in topo.mode_fabrics
    read_live(client, topo)  # ISN's empty body is not checked
    for path in MODE_BODIES:
        client.responses.pop(path)
    read_live(client, load(HERE / "tests" / "fixtures" / "topology_nd421_base.yaml"))  # no mode fabrics: nothing is checked


def test_snapshot_read_does_not_check_the_mode(tmp_path):
    import shutil

    snap = tmp_path / "snap"
    shutil.copytree(SNAPSHOTS / "nd421", snap)
    (snap / "fabric_SITE1.json").write_text('{"name": "SITE1", "management": {}}', encoding="utf-8")
    live = read_live_from_snapshot(snap, load(HERE / "topology_nd421.yaml", replication_mode="multicast"))
    assert live["SITE1"].settings == {"name": "SITE1", "management": {}}
