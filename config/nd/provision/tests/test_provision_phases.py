"""Tests for Provisioner.phase_fabrics / phase_msd against a stub NDClient."""

from pathlib import Path
from types import SimpleNamespace

from provision import Provisioner, merge_settings
from topology import load

HERE = Path(__file__).resolve().parents[1]


class StubClient:
    """Records every call; get() answers from a dict keyed by (path, sorted params), or raises HTTP 404."""

    def __init__(self, responses: dict | None = None) -> None:
        self.creds = SimpleNamespace(ip="192.0.2.1")
        self.responses = responses or {}
        self.calls: list[tuple] = []

    @staticmethod
    def _key(path: str, params: dict | None) -> tuple:
        return (path, tuple(sorted((params or {}).items())))

    def get(self, path: str, params: dict | None = None):
        self.calls.append(("GET", path, params))
        key = self._key(path, params)
        if key not in self.responses:
            raise RuntimeError("HTTP 404")
        return self.responses[key]

    def post(self, path: str, json=None):
        self.calls.append(("POST", path, json))
        return None

    def put(self, path: str, json=None):
        self.calls.append(("PUT", path, json))
        return None


def _topo():
    return load(HERE / "topology_nd421.yaml")


def _posts(client: StubClient) -> list[tuple]:
    return [call for call in client.calls if call[0] == "POST"]


def _puts(client: StubClient) -> list[tuple]:
    return [call for call in client.calls if call[0] == "PUT"]


def test_phase_fabrics_creates_and_merges_settings_when_absent():
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": []},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
    }
    for fabric in topo.fabrics:
        responses[(f"/fabrics/{fabric.name}", ())] = {"name": fabric.name, "management": {"type": fabric.type, "bgpAsn": fabric.asn}}
    client = StubClient(responses)

    Provisioner(client, topo).phase_fabrics()

    posts = _posts(client)
    assert [p[2]["name"] for p in posts] == ["SITE1", "SITE2", "ISN"]
    puts = _puts(client)
    assert [p[1] for p in puts] == ["/fabrics/SITE1", "/fabrics/SITE2", "/fabrics/ISN"]
    by_path = {p[1]: p[2] for p in puts}
    assert by_path["/fabrics/SITE1"]["management"]["vrfLiteAutoConfig"] == "back2BackAndToExternal"
    assert by_path["/fabrics/ISN"]["management"]["monitoredMode"] is False


def test_phase_fabrics_no_writes_when_already_present_and_merged():
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": f.name} for f in topo.fabrics]},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
    }
    for fabric in topo.fabrics:
        current = {"name": fabric.name, "management": {"type": fabric.type, "bgpAsn": fabric.asn}}
        current = merge_settings(current, fabric.settings) if fabric.settings else current
        responses[(f"/fabrics/{fabric.name}", ())] = current
    client = StubClient(responses)

    Provisioner(client, topo).phase_fabrics()

    assert _posts(client) == []
    assert _puts(client) == []


def test_phase_msd_creates_group_and_adds_members_in_order_when_members_404():
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": f.name} for f in topo.fabrics]},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
        # /fabrics/MSD/members deliberately absent -> StubClient.get raises HTTP 404
    }
    client = StubClient(responses)

    Provisioner(client, topo).phase_msd()

    posts = _posts(client)
    assert posts[0][1] == "/fabrics"
    assert posts[0][2]["category"] == "fabricGroup"
    add_member_posts = [p for p in posts[1:]]
    assert [p[1] for p in add_member_posts] == ["/fabrics/MSD/actions/addMembers"] * 3
    assert [p[2]["members"][0]["name"] for p in add_member_posts] == ["SITE1", "SITE2", "ISN"]


def test_phase_msd_no_writes_when_group_and_members_already_present():
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": f.name} for f in topo.fabrics]},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": [{"name": "MSD"}]},
        ("/fabrics/MSD/members", ()): {"fabrics": [{"name": "SITE1"}, {"name": "SITE2"}, {"name": "ISN"}]},
    }
    client = StubClient(responses)

    Provisioner(client, topo).phase_msd()

    assert _posts(client) == []


def test_phase_msd_dry_run_reads_members_and_logs_no_add_members(capsys):
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": f.name} for f in topo.fabrics]},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": [{"name": "MSD"}]},
        ("/fabrics/MSD/members", ()): {"fabrics": [{"name": "SITE1"}, {"name": "SITE2"}, {"name": "ISN"}]},
    }
    client = StubClient(responses)

    Provisioner(client, topo, dry_run=True).phase_msd()

    assert _posts(client) == []
    out = capsys.readouterr().out
    assert "addMembers" not in out
