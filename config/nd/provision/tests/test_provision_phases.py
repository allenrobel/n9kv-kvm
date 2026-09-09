"""Tests for Provisioner.phase_fabrics / phase_msd against a stub NDClient."""

from pathlib import Path
from types import SimpleNamespace

import pytest

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


def _dry_run_lines(out: str, path: str) -> list[str]:
    prefix = f"[dry-run] POST {path} "
    return [line for line in out.splitlines() if line.startswith(prefix)]


def test_phase_switches_dry_run_posts_add_and_deploy_but_no_role_change(capsys):
    topo = _topo()
    responses = {("/fabrics/SITE2/switches", ()): {"switches": []}}
    client = StubClient(responses)

    Provisioner(client, topo, dry_run=True).phase_switches()

    assert _posts(client) == []  # dry-run never issues a real write
    out = capsys.readouterr().out

    add_lines = _dry_run_lines(out, "/fabrics/SITE2/switches")
    assert len(add_lines) == 1
    add_line = add_lines[0]
    assert '"platformType": "nx-os"' in add_line
    assert '"preserveConfig": false' in add_line
    for hostname, role in [("S2_BG1", "borderGateway"), ("S2_SP1", "spine"), ("S2_LE1", "leaf")]:
        assert f'"hostname": "{hostname}", "switchRole": "{role}"' in add_line

    deploy_lines = _dry_run_lines(out, "/fabrics/SITE2/actions/configDeploy")
    assert len(deploy_lines) == 1
    assert not any("switchActions" in line for line in out.splitlines() if "SITE2" in line)


def _already_present(fabric, role_overrides: dict | None = None) -> dict:
    """Build a /fabrics/<name>/switches response with every switch present, so nothing is missing
    and wait_for_switches is never invoked (which would otherwise really sleep, since the stub never
    grows a fabric's switch list after a POST)."""
    overrides = role_overrides or {}
    return {"switches": [{"hostname": s.hostname, "serialNumber": f"SN-{s.hostname}", "switchRole": overrides.get(s.hostname, s.role)} for s in fabric.switches]}


def test_phase_switches_changes_wrong_role_when_switches_already_present():
    topo = _topo()
    site1 = next(f for f in topo.fabrics if f.name == "SITE1")
    site2 = next(f for f in topo.fabrics if f.name == "SITE2")
    isn = next(f for f in topo.fabrics if f.name == "ISN")
    responses = {
        ("/fabrics/SITE1/switches", ()): _already_present(site1),
        ("/fabrics/SITE2/switches", ()): _already_present(site2, {"S2_BG1": "leaf"}),
        ("/fabrics/ISN/switches", ()): _already_present(isn),
    }
    client = StubClient(responses)

    Provisioner(client, topo).phase_switches()

    posts = _posts(client)
    assert [p[1] for p in posts if p[1] == "/fabrics/SITE2/switches"] == []
    role_posts = [p for p in posts if p[1] == "/fabrics/SITE2/switchActions/changeRoles"]
    assert len(role_posts) == 1
    assert role_posts[0][2] == {"switchRoles": [{"switchId": "SN-S2_BG1", "role": "borderGateway"}]}
    deploy_index = [p[1] for p in posts].index("/fabrics/SITE2/actions/configDeploy")
    role_index = [p[1] for p in posts].index("/fabrics/SITE2/switchActions/changeRoles")
    assert role_index < deploy_index


def test_switch_add_payload_for_isn_uses_iosxe_password(monkeypatch, capsys):
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-secret")
    topo = _topo()
    responses = {("/fabrics/ISN/switches", ()): {"switches": []}}
    client = StubClient(responses)

    Provisioner(client, topo, dry_run=True).phase_switches()

    assert _posts(client) == []  # dry-run never issues a real write
    out = capsys.readouterr().out
    add_lines = _dry_run_lines(out, "/fabrics/ISN/switches")
    assert len(add_lines) == 1
    assert '"platformType": "ios-xe"' in add_lines[0]
    assert '"password": "iosxe-secret"' in add_lines[0]


def test_pending_raises_when_stub_get_raises():
    topo = _topo()
    client = StubClient({})  # /fabrics/SITE2/switches/SN123/pendingConfig deliberately absent -> HTTP 404

    with pytest.raises(RuntimeError):
        Provisioner(client, topo).pending("SITE2", "SN123")


def test_pending_returns_list_when_stub_returns_one():
    topo = _topo()
    pending_diff = [{"switchId": "SN123", "diffType": "pendingConfig"}]
    responses = {("/fabrics/SITE2/switches/SN123/pendingConfig", ()): pending_diff}
    client = StubClient(responses)

    assert Provisioner(client, topo).pending("SITE2", "SN123") == pending_diff


def test_serial_dry_run_returns_placeholder_when_switch_absent():
    topo = _topo()
    client = StubClient({})  # /fabrics/SITE2/switches deliberately absent -> HTTP 404, treated as empty

    assert Provisioner(client, topo, dry_run=True).serial("S2_BG1") == "<S2_BG1-serial>"


def test_serial_live_raises_when_switch_absent():
    topo = _topo()
    client = StubClient({})  # /fabrics/SITE2/switches deliberately absent -> HTTP 404, treated as empty

    with pytest.raises(RuntimeError, match="S2_BG1"):
        Provisioner(client, topo).serial("S2_BG1")


def test_serial_live_returns_serial_number_when_switch_present():
    topo = _topo()
    responses = {("/fabrics/SITE2/switches", ()): {"switches": [{"hostname": "S2_BG1", "serialNumber": "SN-BG1", "switchRole": "borderGateway"}]}}
    client = StubClient(responses)

    assert Provisioner(client, topo).serial("S2_BG1") == "SN-BG1"
