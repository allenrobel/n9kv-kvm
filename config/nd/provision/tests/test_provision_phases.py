"""Tests for Provisioner.phase_fabrics / phase_msd against a stub NDClient."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import provision
from provision import Provisioner, merge_settings
from topology import Overlay, load

HERE = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_settle_sleep(monkeypatch):
    """config_deploy/phase_deploy/phase_isn sleep settle_seconds between deploy and the pending check; never in tests."""
    monkeypatch.setattr(provision.time, "sleep", lambda _seconds: None)


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

    def post(self, path: str, json=None, timeout=None):
        self.calls.append(("POST", path, json))
        return self.responses.get(path)

    def put(self, path: str, json=None):
        self.calls.append(("PUT", path, json))
        return None

    def paged(self, path: str, key: str, params: dict | None = None, page: int = 100):
        self.calls.append(("GET", path, params))
        lookup = self._key(path, params)
        if lookup not in self.responses:
            raise RuntimeError("HTTP 404")
        return self.responses[lookup]


class _StubClientFlakyRead(StubClient):
    """StubClient whose GET on `flaky_path` raises HTTP 404 the first time it is called, then answers
    `steady_value` on every call after that. Models an ND read-after-create race: the object briefly 404s
    right after the create POST before it is queryable."""

    def __init__(self, responses: dict, flaky_path: str, steady_value: dict) -> None:
        super().__init__(responses)
        self.flaky_path = flaky_path
        self.steady_value = steady_value
        self._flaky_reads = 0

    def get(self, path: str, params: dict | None = None):
        if path != self.flaky_path:
            return super().get(path, params)
        self.calls.append(("GET", path, params))
        self._flaky_reads += 1
        if self._flaky_reads == 1:
            raise RuntimeError("HTTP 404")
        return self.steady_value


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
    assert [p[2]["name"] for p in posts] == ["SITE1", "SITE2", "ISN", "CAMPUS1"]
    puts = _puts(client)
    assert [p[1] for p in puts] == ["/fabrics/SITE1", "/fabrics/SITE2", "/fabrics/ISN", "/fabrics/CAMPUS1"]
    by_path = {p[1]: p[2] for p in puts}
    assert by_path["/fabrics/SITE1"]["management"]["vrfLiteAutoConfig"] == "back2BackAndToExternal"
    assert by_path["/fabrics/ISN"]["management"]["monitoredMode"] is False
    assert by_path["/fabrics/CAMPUS1"]["management"]["bgpLoopbackIpRange"] == "10.41.0.0/22"


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


def test_phase_fabrics_dry_run_logs_already_applied_when_settings_match(capsys):
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

    Provisioner(client, topo, dry_run=True).phase_fabrics()

    assert _posts(client) == []
    assert _puts(client) == []
    out = capsys.readouterr().out
    for fabric in topo.fabrics:
        assert f"settings already applied on /fabrics/{fabric.name}" in out
    assert "would merge" not in out
    assert "PUT" not in out


def test_phase_fabrics_dry_run_logs_would_apply_when_fabrics_absent(capsys):
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": []},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
        # /fabrics/<name> deliberately absent -> StubClient.get raises HTTP 404, treated as empty
    }
    client = StubClient(responses)

    Provisioner(client, topo, dry_run=True).phase_fabrics()

    assert _posts(client) == []  # dry-run never issues a real write
    assert _puts(client) == []
    out = capsys.readouterr().out
    create_lines = [line for line in out.splitlines() if line.startswith("[dry-run] POST /fabrics ")]
    assert len(create_lines) == 4
    for fabric in topo.fabrics:
        assert f"would apply settings to new fabric /fabrics/{fabric.name}" in out


def test_phase_fabrics_live_puts_only_the_fabric_missing_a_setting(capsys):
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": f.name} for f in topo.fabrics]},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
    }
    for fabric in topo.fabrics:
        current = {"name": fabric.name, "management": {"type": fabric.type, "bgpAsn": fabric.asn}}
        current = merge_settings(current, fabric.settings) if fabric.settings else current
        if fabric.name == "SITE1":
            del current["management"]["vrfLiteAutoConfig"]
        responses[(f"/fabrics/{fabric.name}", ())] = current
    client = StubClient(responses)

    Provisioner(client, topo).phase_fabrics()

    assert _posts(client) == []
    puts = _puts(client)
    assert [p[1] for p in puts] == ["/fabrics/SITE1"]
    assert puts[0][2]["management"]["vrfLiteAutoConfig"] == "back2BackAndToExternal"


def test_phase_fabrics_live_re_reads_after_create_then_puts_merged_settings():
    """SITE1 does not exist yet: the create POST fires, the immediate read-back 404s (ND has not indexed
    it yet), and the guarded re-read picks up the freshly-created object so settings still get merged/PUT."""
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": "SITE2"}, {"name": "ISN"}, {"name": "CAMPUS1"}]},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
    }
    for fabric in topo.fabrics:
        if fabric.name == "SITE1":
            continue
        current = {"name": fabric.name, "management": {"type": fabric.type, "bgpAsn": fabric.asn}}
        current = merge_settings(current, fabric.settings) if fabric.settings else current
        responses[(f"/fabrics/{fabric.name}", ())] = current
    client = _StubClientFlakyRead(responses, "/fabrics/SITE1", {"name": "SITE1", "management": {"type": "vxlanIbgp", "bgpAsn": "65001"}})

    Provisioner(client, topo).phase_fabrics()

    posts = _posts(client)
    assert [p[1] for p in posts] == ["/fabrics"]
    assert posts[0][2]["name"] == "SITE1"
    puts = _puts(client)
    assert [p[1] for p in puts] == ["/fabrics/SITE1"]
    assert "vrfLiteAutoConfig" in puts[0][2]["management"]


def test_phase_fabrics_live_skips_settings_and_logs_when_read_never_succeeds(capsys):
    """SITE1 is present in /fabrics but GET /fabrics/SITE1 always 404s (a persistent, not transient,
    read failure): must not create (it already exists) or write settings based on a guess."""
    topo = _topo()
    responses = {
        ("/fabrics", ()): {"fabrics": [{"name": f.name} for f in topo.fabrics]},
        ("/fabrics", (("category", "fabricGroup"),)): {"fabrics": []},
        # /fabrics/SITE1 deliberately absent -> StubClient.get always raises HTTP 404
    }
    for fabric in topo.fabrics:
        if fabric.name == "SITE1":
            continue
        current = {"name": fabric.name, "management": {"type": fabric.type, "bgpAsn": fabric.asn}}
        current = merge_settings(current, fabric.settings) if fabric.settings else current
        responses[(f"/fabrics/{fabric.name}", ())] = current
    client = StubClient(responses)

    Provisioner(client, topo).phase_fabrics()

    assert _posts(client) == []
    assert _puts(client) == []
    out = capsys.readouterr().out
    assert "could not read /fabrics/SITE1 after create/re-read; skipping settings this run" in out
    assert "would apply settings" not in out


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


def test_phase_switches_dry_run_posts_add_and_deploy_but_no_role_change(monkeypatch, capsys):
    # SITE1/ISN switches also 404 as "not present" below, so every fabric's `missing` list is non-empty and
    # _switch_password() is called for all three -- both passwords must be set, not just SITE2/NX-OS's.
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-pw")  # ggignore: unit-test placeholder, not a credential
    topo = _topo()
    responses = {("/fabrics/SITE2/switches", ()): {"switches": []}}
    client = StubClient(responses)

    Provisioner(client, topo, dry_run=True).phase_switches()

    assert _posts(client) == []  # dry-run never issues a real write
    out = capsys.readouterr().out

    discovery_lines = _dry_run_lines(out, "/fabrics/SITE2/actions/shallowDiscovery")
    assert len(discovery_lines) == 1
    assert '"seedIpCollection": ["192.168.12.132", "192.168.12.142", "192.168.12.153"]' in discovery_lines[0]
    add_lines = _dry_run_lines(out, "/fabrics/SITE2/switches")
    assert len(add_lines) == 1
    add_line = add_lines[0]
    assert '"platformType": "nx-os"' in add_line
    assert '"preserveConfig": false' in add_line
    for hostname, role in [("S2_BG1", "borderGateway"), ("S2_SP1", "spine"), ("S2_LE1", "leaf")]:
        assert f'"hostname": "{hostname}", "switchRole": "{role}", "serialNumber": "<from-discovery>", "model": "<from-discovery>"' in add_line
    assert "nxos-pw" not in out and '"password": "***"' in add_line  # ggignore: unit-test placeholder, not a credential

    deploy_lines = _dry_run_lines(out, "/fabrics/SITE2/actions/deploy")
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
    deploy_index = [p[1] for p in posts].index("/fabrics/SITE2/actions/deploy")
    role_index = [p[1] for p in posts].index("/fabrics/SITE2/switchActions/changeRoles")
    assert role_index < deploy_index


def test_phase_switches_isn_dry_run_is_ios_xe_and_never_logs_the_password(monkeypatch, capsys):
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-secret")  # ggignore: unit-test placeholder, not a credential
    topo = _topo()
    responses = {("/fabrics/ISN/switches", ()): {"switches": []}}
    client = StubClient(responses)

    Provisioner(client, topo, dry_run=True).phase_switches()

    assert _posts(client) == []  # dry-run never issues a real write
    out = capsys.readouterr().out
    add_lines = _dry_run_lines(out, "/fabrics/ISN/switches")
    assert len(add_lines) == 1
    assert '"platformType": "ios-xe"' in add_lines[0]
    assert "iosxe-secret" not in out  # ggignore: unit-test placeholder, not a credential
    assert '"password": "***"' in add_lines[0]


class _StubClientListsAfterAdd(StubClient):
    """GET /fabrics/<f>/switches answers empty until POST /fabrics/<f>/switches has happened, then lists the
    switches that POST carried (with their serialNumber), modelling ND import. Keeps wait_for_switches from
    sleeping in tests."""

    def __init__(self, responses: dict, fabric: str) -> None:
        super().__init__(responses)
        self.fabric = fabric
        self.added: list[dict] = []

    def get(self, path: str, params: dict | None = None):
        if path == f"/fabrics/{self.fabric}/switches":
            self.calls.append(("GET", path, params))
            return {"switches": [dict(entry, switchRole=entry["switchRole"]) for entry in self.added]}
        return super().get(path, params)

    def post(self, path: str, json=None, timeout=None):
        if path == f"/fabrics/{self.fabric}/switches":
            self.added.extend(json["switches"])
        return super().post(path, json, timeout)


def test_phase_switches_live_discovers_then_adds_only_manageable_switches(monkeypatch):
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-pw")  # ggignore: unit-test placeholder, not a credential
    topo = _topo()
    site1, isn, campus = topo.fabrics[0], topo.fabrics[2], topo.fabrics[3]
    responses = {
        ("/fabrics/SITE1/switches", ()): _already_present(site1),
        ("/fabrics/ISN/switches", ()): _already_present(isn),
        ("/fabrics/CAMPUS1/switches", ()): _already_present(campus),
        "/fabrics/SITE2/actions/shallowDiscovery": {
            "switches": [
                {"ip": "192.168.12.132", "hostname": "S2_BG1", "serialNumber": "SN-BG1", "model": "N9K-C9300v", "softwareVersion": "10.6(2)", "status": "manageable"},
                {"ip": "192.168.12.142", "hostname": "S2_SP1", "serialNumber": "SN-SP1", "model": "N9K-C9300v", "softwareVersion": "10.6(2)", "status": "manageable"},
                {"ip": "192.168.12.153", "hostname": "S2_LE1", "status": "notReachable", "statusReason": "SSH timeout"},
            ]
        },
    }
    client = _StubClientListsAfterAdd(responses, "SITE2")

    Provisioner(client, topo).phase_switches()

    posts = _posts(client)
    assert [p[1] for p in posts] == [
        "/fabrics/SITE1/actions/configSave",  # SITE1 fully present: deploy only
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/shallowDiscovery",
        "/fabrics/SITE2/switches",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
        "/fabrics/ISN/actions/configSave",
        "/fabrics/ISN/actions/deploy",
        "/fabrics/CAMPUS1/actions/configSave",
        "/fabrics/CAMPUS1/actions/deploy",
    ]
    discovery = next(p[2] for p in posts if p[1].endswith("shallowDiscovery"))
    assert discovery["seedIpCollection"] == ["192.168.12.132", "192.168.12.142", "192.168.12.153"] and discovery["maxHop"] == 0
    add = next(p[2] for p in posts if p[1] == "/fabrics/SITE2/switches")
    assert [(e["hostname"], e["serialNumber"], e["model"]) for e in add["switches"]] == [("S2_BG1", "SN-BG1", "N9K-C9300v"), ("S2_SP1", "SN-SP1", "N9K-C9300v")]
    assert add["password"] == "nxos-pw"  # ggignore: unit-test placeholder, not a credential -- the real call still carries it


def test_pending_raises_when_stub_get_raises():
    topo = _topo()
    client = StubClient({})  # /fabrics/SITE2/switches/SN123/pendingConfig deliberately absent -> HTTP 404

    with pytest.raises(RuntimeError):
        Provisioner(client, topo).pending("SITE2", "SN123")


def test_pending_unwraps_the_pendingconfigs_envelope():
    topo = _topo()
    lines = ["interface Ethernet1/1", "  no shutdown"]
    responses = {("/fabrics/SITE2/switches/SN123/pendingConfig", ()): {"pendingConfigs": lines}}
    client = StubClient(responses)

    assert Provisioner(client, topo).pending("SITE2", "SN123") == lines


def test_pending_empty_envelope_means_in_sync():
    topo = _topo()
    responses = {("/fabrics/SITE2/switches/SN123/pendingConfig", ()): {"pendingConfigs": []}}
    client = StubClient(responses)

    assert Provisioner(client, topo).pending("SITE2", "SN123") == []


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


def test_phase_isn_dry_run_creates_everything_and_deploys(capsys):
    topo = _topo()
    client = StubClient({})  # nothing exists yet -> every GET/paged raises HTTP 404

    Provisioner(client, topo, dry_run=True, settle_seconds=0).phase_isn()

    assert _posts(client) == []
    assert _puts(client) == []
    out = capsys.readouterr().out

    loopback_lines = _dry_run_lines(out, "/fabrics/ISN/switches/<WAN1-serial>/interfaces")
    assert len(loopback_lines) == 1

    policy_lines = _dry_run_lines(out, "/fabrics/ISN/policies")
    assert len(policy_lines) == 4
    assert sum("ios_xe_bgp_router_id" in line for line in policy_lines) == 1
    assert sum("ios_xe_cdp_run" in line for line in policy_lines) == 1
    assert sum("ios_xe_cdp_enable_interface" in line for line in policy_lines) == 2

    link_lines = _dry_run_lines(out, "/links")
    assert len(link_lines) == 2
    assert any("10.15.0.1/30" in line for line in link_lines)
    assert any("10.25.0.1/30" in line for line in link_lines)

    deploy_paths = [line.split()[2] for line in out.splitlines() if "actions/configSave" in line or "actions/deploy" in line]
    assert deploy_paths == [
        "/fabrics/ISN/actions/configSave",
        "/fabrics/ISN/actions/deploy",
        "/fabrics/SITE1/actions/configSave",
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
    ]

    assert not any(line.startswith("[dry-run] PUT") for line in out.splitlines())


def test_phase_isn_deploys_wan_fabric_first_even_when_alphabetically_last(capsys):
    """The deploy order must be WAN fabric, then destination fabrics sorted -- not whatever `sorted()` of the
    union happens to produce. A WAN fabric name that sorts after the site fabrics proves the two are separate,
    explicit steps rather than an accident of alphabetical ordering."""
    topo = _topo()
    isn = replace(topo.isn, wan=replace(topo.isn.wan, fabric="ZZZ_WAN"))
    topo = replace(topo, isn=isn)
    client = StubClient({})  # nothing exists yet -> every GET/paged raises HTTP 404

    Provisioner(client, topo, dry_run=True, settle_seconds=0).phase_isn()

    out = capsys.readouterr().out
    deploy_paths = [line.split()[2] for line in out.splitlines() if "actions/configSave" in line or "actions/deploy" in line]
    assert deploy_paths == [
        "/fabrics/ZZZ_WAN/actions/configSave",
        "/fabrics/ZZZ_WAN/actions/deploy",
        "/fabrics/SITE1/actions/configSave",
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
    ]


def _isn_policies() -> list[dict]:
    return [
        {"templateName": "ios_xe_bgp_router_id", "entityType": "switch", "entityName": "SWITCH", "switchId": "SN-WAN1"},
        {"templateName": "ios_xe_cdp_run", "entityType": "switch", "entityName": "SWITCH", "switchId": "SN-WAN1"},
        {"templateName": "ios_xe_cdp_enable_interface", "entityType": "interface", "entityName": "GigabitEthernet2", "switchId": "SN-WAN1"},
        {"templateName": "ios_xe_cdp_enable_interface", "entityType": "interface", "entityName": "GigabitEthernet3", "switchId": "SN-WAN1"},
    ]


def _isn_links_present() -> list[dict]:
    return [
        {"srcSwitchName": "WAN1", "srcInterfaceName": "GigabitEthernet2"},
        {"srcSwitchName": "WAN1", "srcInterfaceName": "GigabitEthernet3"},
    ]


def _live_isn_responses(monitored_mode: bool) -> dict:
    return {
        ("/fabrics/ISN", ()): {"name": "ISN", "management": {"monitoredMode": monitored_mode}},
        ("/fabrics/ISN/switches", ()): {"switches": [{"hostname": "WAN1", "serialNumber": "SN-WAN1", "switchRole": "coreRouter"}]},
        ("/fabrics/ISN/switches/SN-WAN1/interfaces", ()): {"interfaces": [{"interfaceName": "Loopback0"}]},
        ("/fabrics/ISN/policies", (("switchId", "SN-WAN1"),)): _isn_policies(),
        ("/links", (("fabricName", "ISN"),)): _isn_links_present(),
        ("/fabrics/SITE1/switches", ()): {"switches": [{"hostname": "S1_BG1", "serialNumber": "SN-S1_BG1", "switchRole": "borderGateway"}]},
        ("/fabrics/SITE2/switches", ()): {"switches": [{"hostname": "S2_BG1", "serialNumber": "SN-S2_BG1", "switchRole": "borderGateway"}]},
        ("/fabrics/ISN/switches/SN-WAN1/pendingConfig", ()): {"pendingConfigs": []},
    }


def test_phase_isn_live_everything_present_only_deploys(capsys):
    topo = _topo()
    client = StubClient(_live_isn_responses(monitored_mode=False))

    Provisioner(client, topo, settle_seconds=0).phase_isn()

    assert _puts(client) == []
    posts = _posts(client)
    assert [p[1] for p in posts] == [
        "/fabrics/ISN/actions/configSave",
        "/fabrics/ISN/actions/deploy",
        "/fabrics/SITE1/actions/configSave",
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
    ]
    out = capsys.readouterr().out
    assert "WAN1 pendingConfig after deploy: 0 line(s)" in out


def test_phase_isn_live_clears_monitored_mode_when_true(capsys):
    topo = _topo()
    client = StubClient(_live_isn_responses(monitored_mode=True))

    Provisioner(client, topo, settle_seconds=0).phase_isn()

    puts = _puts(client)
    assert len(puts) == 1
    assert puts[0][1] == "/fabrics/ISN"
    assert puts[0][2]["management"]["monitoredMode"] is False
    posts = _posts(client)
    assert [p[1] for p in posts] == [
        "/fabrics/ISN/actions/configSave",
        "/fabrics/ISN/actions/deploy",
        "/fabrics/SITE1/actions/configSave",
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
    ]
    out = capsys.readouterr().out
    assert "WAN1 pendingConfig after deploy: 0 line(s)" in out


def _dry_run_post_paths(out: str) -> list[str]:
    return [line.split()[2] for line in out.splitlines() if line.startswith("[dry-run] POST ")]


def _populated_overlay_topo():
    topo = _topo()
    overlay = Overlay(
        vrfs=[{"fabrics": ["SITE1", "SITE2"], "object": {"vrfName": "V1", "vrfId": 50001, "vlanId": 2001}}],
        networks=[{"fabrics": ["SITE1", "SITE2"], "object": {"networkName": "N1", "networkId": 30001, "vlanId": 2, "vrfName": "V1"}}],
        vrf_attachments=[{"fabric": "SITE1", "vrf": "V1", "switch": "S1_TOR1"}],
        network_attachments=[{"fabric": "SITE1", "network": "N1", "switch": "S1_TOR1", "vlan": 2, "interfaces": [{"mode": "access", "interfaceRange": "Ethernet1/3"}]}],
    )
    return replace(topo, overlay=overlay)


def test_phase_overlay_with_an_empty_overlay_section_is_a_noop(capsys):
    topo = replace(_topo(), overlay=Overlay())  # the shipped files carry the LAB overlay; strip it for the no-op case
    client = StubClient({})

    Provisioner(client, topo).phase_overlay()

    assert _posts(client) == []
    assert _puts(client) == []
    out = capsys.readouterr().out
    assert "POST" not in out


def test_phase_overlay_dry_run_creates_everything_and_deploys(capsys):
    topo = _populated_overlay_topo()
    client = StubClient({})  # nothing exists yet -> every GET raises HTTP 404; query POSTs are unregistered -> None

    Provisioner(client, topo, dry_run=True).phase_overlay()

    # the two idempotency queries are reads and execute for real even under --dry-run (nothing is stubbed for
    # them, so StubClient.post() answers None -> treated as "nothing attached yet"); no other real POST/PUT fires.
    posts = _posts(client)
    assert [p[1] for p in posts] == ["/fabrics/SITE1/vrfAttachments/query", "/fabrics/SITE1/networkAttachments/query"]
    assert _puts(client) == []
    out = capsys.readouterr().out

    assert _dry_run_post_paths(out) == [
        "/fabrics/SITE1/vrfs",
        "/fabrics/SITE2/vrfs",
        "/fabrics/SITE1/networks",
        "/fabrics/SITE2/networks",
        "/fabrics/SITE1/vrfAttachments",
        "/fabrics/SITE1/networkAttachments",
        "/fabrics/SITE1/vrfActions/deploy",
        "/fabrics/SITE1/networkActions/deploy",
    ]
    lines = [line for line in out.splitlines() if line.startswith("[dry-run] POST ")]
    assert '"fabricName": "SITE1"' in lines[0]
    assert "<S1_TOR1-serial>" in lines[4]
    assert "<S1_TOR1-serial>" in lines[5]


def _overlay_query_stubs(vrf_attachments: list[dict], network_attachments: list[dict]) -> dict:
    return {
        "/fabrics/SITE1/vrfAttachments/query": {"attachments": vrf_attachments},
        "/fabrics/SITE1/networkAttachments/query": {"attachments": network_attachments},
    }


def test_phase_overlay_live_attaches_existing_vrf_and_network(capsys):
    topo = _populated_overlay_topo()
    responses = {
        ("/fabrics/SITE1/vrfs", ()): {"vrfs": [{"vrfName": "V1", "vrfId": 50001, "vlanId": 2001}]},
        ("/fabrics/SITE2/vrfs", ()): {"vrfs": [{"vrfName": "V1", "vrfId": 50001, "vlanId": 2001}]},
        ("/fabrics/SITE1/networks", ()): {"networks": [{"networkName": "N1", "networkId": 30001, "vlanId": 2, "vrfName": "V1"}]},
        ("/fabrics/SITE2/networks", ()): {"networks": [{"networkName": "N1", "networkId": 30001, "vlanId": 2, "vrfName": "V1"}]},
        ("/fabrics/SITE1/switches", ()): {"switches": [{"hostname": "S1_TOR1", "serialNumber": "SN-TOR1", "switchRole": "tor"}]},
        **_overlay_query_stubs([], []),  # neither attachment exists yet
    }
    client = StubClient(responses)

    Provisioner(client, topo).phase_overlay()

    posts = _posts(client)
    assert [p[1] for p in posts if p[1] in ("/fabrics/SITE1/vrfs", "/fabrics/SITE2/vrfs")] == []
    assert [p[1] for p in posts if p[1] in ("/fabrics/SITE1/networks", "/fabrics/SITE2/networks")] == []

    vrf_att = [p for p in posts if p[1] == "/fabrics/SITE1/vrfAttachments"]
    assert len(vrf_att) == 1
    assert vrf_att[0][2] == {"attachments": [{"vrfName": "V1", "switchId": "SN-TOR1", "attach": True}]}

    net_att = [p for p in posts if p[1] == "/fabrics/SITE1/networkAttachments"]
    assert len(net_att) == 1
    assert net_att[0][2] == {
        "attachments": [{"networkName": "N1", "switchId": "SN-TOR1", "vlanId": 2, "interfaces": [{"mode": "access", "interfaceRange": "Ethernet1/3"}], "attach": True}]
    }

    assert [p[1] for p in posts if "Actions/deploy" in p[1]] == ["/fabrics/SITE1/vrfActions/deploy", "/fabrics/SITE1/networkActions/deploy"]
    for p in posts:
        if "Actions/deploy" in p[1]:
            assert p[2]["switchIds"] == ["SN-TOR1"] and (p[2].get("vrfNames") == ["V1"] or p[2].get("networkNames") == ["N1"])


def test_phase_overlay_live_skips_existing_vrf_attachment_but_attaches_missing_network(capsys):
    """The vrf attachment already has attach: true on ND; the network attachment does not. Only the network
    side should POST/deploy -- proves vrf and network idempotency/deploy tracking are independent."""
    topo = _populated_overlay_topo()
    responses = {
        ("/fabrics/SITE1/vrfs", ()): {"vrfs": [{"vrfName": "V1", "vrfId": 50001, "vlanId": 2001}]},
        ("/fabrics/SITE2/vrfs", ()): {"vrfs": [{"vrfName": "V1", "vrfId": 50001, "vlanId": 2001}]},
        ("/fabrics/SITE1/networks", ()): {"networks": [{"networkName": "N1", "networkId": 30001, "vlanId": 2, "vrfName": "V1"}]},
        ("/fabrics/SITE2/networks", ()): {"networks": [{"networkName": "N1", "networkId": 30001, "vlanId": 2, "vrfName": "V1"}]},
        ("/fabrics/SITE1/switches", ()): {"switches": [{"hostname": "S1_TOR1", "serialNumber": "SN-TOR1", "switchRole": "tor"}]},
        **_overlay_query_stubs([{"vrfName": "V1", "switchId": "SN-TOR1", "attach": True}], []),
    }
    client = StubClient(responses)

    Provisioner(client, topo).phase_overlay()

    posts = _posts(client)
    assert [p[1] for p in posts if p[1] == "/fabrics/SITE1/vrfAttachments"] == []
    net_att = [p for p in posts if p[1] == "/fabrics/SITE1/networkAttachments"]
    assert len(net_att) == 1
    assert [p[1] for p in posts if "Actions/deploy" in p[1]] == ["/fabrics/SITE1/networkActions/deploy"]


def test_phase_deploy_dry_run_deploys_every_fabric_and_does_not_check_pending(capsys):
    topo = _topo()
    client = StubClient({})

    Provisioner(client, topo, dry_run=True).phase_deploy()

    assert _posts(client) == []
    assert not any(call[0] == "GET" and "pendingConfig" in call[1] for call in client.calls)
    out = capsys.readouterr().out
    deploy_lines = [line for line in out.splitlines() if "actions/configSave" in line or "actions/deploy" in line]
    assert [line.split()[2] for line in deploy_lines] == [
        "/fabrics/SITE1/actions/configSave",
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
        "/fabrics/ISN/actions/configSave",
        "/fabrics/ISN/actions/deploy",
        "/fabrics/CAMPUS1/actions/configSave",
        "/fabrics/CAMPUS1/actions/deploy",
        "/fabrics/MSD/actions/configSave",
        "/fabrics/MSD/actions/deploy",
    ]


def _all_switches_present_responses(topo) -> dict:
    responses = {}
    for fabric in topo.fabrics:
        responses[(f"/fabrics/{fabric.name}/switches", ())] = {
            "switches": [{"hostname": s.hostname, "serialNumber": f"SN-{s.hostname}", "switchRole": s.role} for s in fabric.switches]
        }
        for switch in fabric.switches:
            responses[(f"/fabrics/{fabric.name}/switches/SN-{switch.hostname}/pendingConfig", ())] = []
    return responses


def test_phase_deploy_live_prints_pending_config_for_every_switch(capsys):
    topo = _topo()
    client = StubClient(_all_switches_present_responses(topo))

    Provisioner(client, topo, settle_seconds=0).phase_deploy()

    posts = _posts(client)
    assert [p[1] for p in posts] == [
        "/fabrics/SITE1/actions/configSave",
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
        "/fabrics/ISN/actions/configSave",
        "/fabrics/ISN/actions/deploy",
        "/fabrics/CAMPUS1/actions/configSave",
        "/fabrics/CAMPUS1/actions/deploy",
        "/fabrics/MSD/actions/configSave",
        "/fabrics/MSD/actions/deploy",
    ]
    out = capsys.readouterr().out
    assert "SITE1/S1_BG1: pendingConfig 0 line(s)" in out
    assert "ISN/WAN1: pendingConfig 0 line(s)" in out
    assert "CAMPUS1/C1_LE1: pendingConfig 0 line(s)" in out


def test_phase_deploy_live_prints_the_pending_lines_themselves_when_nonempty(capsys):
    topo = _topo()
    responses = _all_switches_present_responses(topo)
    diff_line = {"switchId": "SN-S1_BG1", "diffType": "pendingConfig", "config": "interface Ethernet1/3\n  no shutdown"}
    responses[("/fabrics/SITE1/switches/SN-S1_BG1/pendingConfig", ())] = [diff_line]
    client = StubClient(responses)

    Provisioner(client, topo, settle_seconds=0).phase_deploy()

    out = capsys.readouterr().out
    assert "SITE1/S1_BG1: pendingConfig 1 line(s)" in out
    assert f"    {diff_line}" in out.splitlines()
    # a switch with nothing pending gets no extra indented lines
    assert "ISN/WAN1: pendingConfig 0 line(s)" in out


class _StubClientPendingSequence(StubClient):
    """GET on a pendingConfig path answers the next value from a per-path queue (last value repeats)."""

    def __init__(self, responses: dict, sequences: dict[str, list]) -> None:
        super().__init__(responses)
        self.sequences = {k: list(v) for k, v in sequences.items()}

    def get(self, path: str, params: dict | None = None):
        if path in self.sequences:
            self.calls.append(("GET", path, params))
            queue = self.sequences[path]
            return queue.pop(0) if len(queue) > 1 else queue[0]
        return super().get(path, params)


def test_config_deploy_recalculates_then_deploys_once_when_nothing_is_pending():
    topo = _topo()
    site2 = topo.fabrics[1]
    responses = {("/fabrics/SITE2/switches", ()): _already_present(site2)}
    responses.update({(f"/fabrics/SITE2/switches/SN-{s.hostname}/pendingConfig", ()): {"pendingConfigs": []} for s in site2.switches})
    client = StubClient(responses)

    Provisioner(client, topo, settle_seconds=0).config_deploy("SITE2")

    assert [p[1] for p in _posts(client)] == ["/fabrics/SITE2/actions/configSave", "/fabrics/SITE2/actions/deploy"]


def test_config_deploy_redeploys_once_when_the_first_deploy_leaves_pending_config(capsys):
    topo = _topo()
    site2 = topo.fabrics[1]
    responses = {
        ("/fabrics/SITE2/switches", ()): _already_present(site2),
        ("/fabrics/SITE2/deploymentHistory", ()): {
            "deploymentRecords": [
                {
                    "hostname": "S2_BG1",
                    "status": "notExecuted",
                    "startTimestamp": "2999-01-01T00:00:00.000Z",
                    "configCommandResponses": [{"command": "no vlan 1", "status": "failed", "cliResponse": "Deletion of VLAN 1 is not allowed!!"}],
                }
            ]
        },
    }
    responses.update({(f"/fabrics/SITE2/switches/SN-{s.hostname}/pendingConfig", ()): {"pendingConfigs": []} for s in site2.switches})
    sequences = {"/fabrics/SITE2/switches/SN-S2_BG1/pendingConfig": [{"pendingConfigs": ["no vlan 1", "cfs eth distribute"]}, {"pendingConfigs": []}]}
    client = _StubClientPendingSequence(responses, sequences)

    Provisioner(client, topo, settle_seconds=0).config_deploy("SITE2")

    assert [p[1] for p in _posts(client)] == ["/fabrics/SITE2/actions/configSave", "/fabrics/SITE2/actions/deploy", "/fabrics/SITE2/actions/deploy"]
    out = capsys.readouterr().out
    assert "still pending after deploy {'S2_BG1': 2}" in out
    assert "deploy failure S2_BG1: 'no vlan 1' -> Deletion of VLAN 1 is not allowed!!" in out
    assert "still pending after the second deploy" not in out


def test_config_deploy_dry_run_only_logs_recalculate_and_deploy(capsys):
    topo = _topo()
    client = StubClient({})

    Provisioner(client, topo, dry_run=True).config_deploy("SITE2")

    assert _posts(client) == []
    assert not any(call[0] == "GET" and "pendingConfig" in call[1] for call in client.calls)
    out = capsys.readouterr().out
    assert [line.split()[2] for line in out.splitlines() if line.startswith("[dry-run] POST")] == ["/fabrics/SITE2/actions/configSave", "/fabrics/SITE2/actions/deploy"]


def _site1_present(topo) -> dict:
    return _already_present(topo.fabrics[0])


def test_phase_vpc_dry_run_logs_one_put_per_pair_then_recalculate_and_deploy(capsys):
    topo = _topo()
    client = StubClient({("/fabrics/SITE1/switches", ()): _site1_present(topo)})

    Provisioner(client, topo, dry_run=True).phase_vpc()

    assert _posts(client) == [] and _puts(client) == []
    out = capsys.readouterr().out
    puts = [line.split()[2] for line in out.splitlines() if line.startswith("[dry-run] PUT")]
    assert puts == ["/fabrics/SITE1/switches/SN-S1_LE1/vpcPair", "/fabrics/SITE1/switches/SN-S1_LE3/vpcPair"]
    assert '"vpcAction": "pair", "switchId": "SN-S1_LE1", "peerSwitchId": "SN-S1_LE2"' in out
    posts = [line.split()[2] for line in out.splitlines() if line.startswith("[dry-run] POST")]
    assert posts == ["/fabrics/SITE1/actions/configSave", "/fabrics/SITE1/actions/deploy"]


def test_phase_vpc_live_skips_pairs_nd_already_lists_in_either_order(capsys):
    topo = _topo()
    responses = {
        ("/fabrics/SITE1/switches", ()): _site1_present(topo),
        ("/fabrics/SITE1/vpcPairs", ()): {"vpcPairs": [{"switchId": "SN-S1_LE2", "peerSwitchId": "SN-S1_LE1", "domainId": 1}]},
    }
    responses.update({(f"/fabrics/SITE1/switches/SN-{s.hostname}/pendingConfig", ()): {"pendingConfigs": []} for s in topo.fabrics[0].switches})
    client = StubClient(responses)

    Provisioner(client, topo, settle_seconds=0).phase_vpc()

    assert [p[1] for p in _puts(client)] == ["/fabrics/SITE1/switches/SN-S1_LE3/vpcPair"]
    assert [p[1] for p in _posts(client)] == ["/fabrics/SITE1/actions/configSave", "/fabrics/SITE1/actions/deploy"]
    assert "S1_LE1 <-> S1_LE2 already paired" in capsys.readouterr().out


def test_phase_vpc_live_is_a_no_op_when_every_pair_exists():
    topo = _topo()
    responses = {
        ("/fabrics/SITE1/switches", ()): _site1_present(topo),
        ("/fabrics/SITE1/vpcPairs", ()): {
            "vpcPairs": [
                {"switchId": "SN-S1_LE1", "peerSwitchId": "SN-S1_LE2", "domainId": 1},
                {"switchId": "SN-S1_LE3", "peerSwitchId": "SN-S1_LE4", "domainId": 2},
            ]
        },
    }
    client = StubClient(responses)

    Provisioner(client, topo, settle_seconds=0).phase_vpc()

    assert _puts(client) == [] and _posts(client) == []


def test_ensure_access_port_puts_access_host_policy_only_when_port_is_not_access(capsys):
    topo = _topo()
    responses = {
        ("/fabrics/SITE2/switches/SN-LE1/interfaces/Ethernet1%2F2", ()): {"configData": {"mode": "trunk"}},
        ("/fabrics/SITE2/switches/SN-LE1/interfaces/Ethernet1%2F3", ()): {"configData": {"mode": "access"}},
    }
    client = StubClient(responses)
    prov = Provisioner(client, topo)

    prov._ensure_access_port("SITE2", "SN-LE1", "Ethernet1/2", "S2_H1 eth1")
    prov._ensure_access_port("SITE2", "SN-LE1", "Ethernet1/3", "unused")

    puts = _puts(client)
    assert [p[1] for p in puts] == ["/fabrics/SITE2/switches/SN-LE1/interfaces/Ethernet1%2F2"]
    policy = puts[0][2]["configData"]["networkOS"]["policy"]
    assert puts[0][2]["configData"]["mode"] == "access" and policy["policyType"] == "accessHost" and policy["description"] == "S2_H1 eth1"


_TOR_QUERY = (("aggregationOrLeafPeerSwitchId", "SN-S1_LE2"), ("aggregationOrLeafSwitchId", "SN-S1_LE1"))
_TOR_CANDIDATE_QUERY = _TOR_QUERY + (("includeCandidates", "true"),)
_TOR_RESOURCES = {"accessOrTorPortChannelId": 1, "aggregationOrLeafPortChannelId": 1, "aggregationOrLeafPeerPortChannelId": 1, "aggregationOrLeafVpcId": 1}


def _tor_responses(topo, associations: list | None = None, candidates: list | None = None) -> dict:
    responses = {("/fabrics/SITE1/switches", ()): _site1_present(topo)}
    if associations is not None:
        responses[("/fabrics/SITE1/accessAssociations", _TOR_QUERY)] = {"associations": associations}
    if candidates is not None:
        responses[("/fabrics/SITE1/accessAssociations", _TOR_CANDIDATE_QUERY)] = {"associations": candidates}
    responses.update({(f"/fabrics/SITE1/switches/SN-{s.hostname}/pendingConfig", ()): {"pendingConfigs": []} for s in topo.fabrics[0].switches})
    return responses


def test_phase_tor_dry_run_logs_associate_with_the_topology_ids_then_recalculate_and_deploy(capsys):
    topo = _topo()
    client = StubClient({("/fabrics/SITE1/switches", ()): _site1_present(topo)})

    Provisioner(client, topo, dry_run=True).phase_tor()

    assert _posts(client) == [] and _puts(client) == []
    out = capsys.readouterr().out
    posts = [line.split()[2] for line in out.splitlines() if line.startswith("[dry-run] POST")]
    assert posts == ["/fabrics/SITE1/accessAssociationActions/associate", "/fabrics/SITE1/actions/configSave", "/fabrics/SITE1/actions/deploy"]
    assert '"accessOrTorSwitchId": "SN-S1_TOR1", "aggregationOrLeafSwitchId": "SN-S1_LE1", "aggregationOrLeafPeerSwitchId": "SN-S1_LE2"' in out
    assert (
        '"resources": {"accessOrTorPortChannelId": 1, "aggregationOrLeafPortChannelId": 1, "aggregationOrLeafPeerPortChannelId": 1, "aggregationOrLeafVpcId": 1}' in out
    )


def test_phase_tor_live_associates_with_nds_recommended_ids_then_recalculates_and_deploys(capsys):
    topo = _topo()
    candidate = {"accessOrTorSwitchId": "SN-S1_TOR1", "accessOrTorSwitchName": "S1_TOR1", "isRecommended": True, "remarks": "", "resources": _TOR_RESOURCES}
    responses = _tor_responses(topo, associations=[{"accessOrTorSwitchId": "SN-S1_TOR1", "isRecommended": True, "resources": {}}], candidates=[candidate])
    responses["/fabrics/SITE1/accessAssociationActions/associate"] = {
        "associations": [{"accessOrTorSwitchId": "SN-S1_TOR1", "aggregationOrLeafSwitchId": "SN-S1_LE1", "status": "success", "message": "Association successful"}]
    }
    client = StubClient(responses)

    Provisioner(client, topo, settle_seconds=0).phase_tor()

    posts = _posts(client)
    assert [p[1] for p in posts] == ["/fabrics/SITE1/accessAssociationActions/associate", "/fabrics/SITE1/actions/configSave", "/fabrics/SITE1/actions/deploy"]
    assert posts[0][2] == [
        {"accessOrTorSwitchId": "SN-S1_TOR1", "aggregationOrLeafSwitchId": "SN-S1_LE1", "aggregationOrLeafPeerSwitchId": "SN-S1_LE2", "resources": _TOR_RESOURCES}
    ]
    assert "S1_TOR1 -> S1_LE1/S1_LE2: Association successful" in capsys.readouterr().out


def test_phase_tor_live_skips_a_tor_nd_already_associates(capsys):
    topo = _topo()
    existing = {"accessOrTorSwitchId": "SN-S1_TOR1", "aggregationOrLeafSwitchId": "SN-S1_LE1", "aggregationOrLeafPeerSwitchId": "SN-S1_LE2", "resources": _TOR_RESOURCES}
    client = StubClient(_tor_responses(topo, associations=[existing]))

    Provisioner(client, topo, settle_seconds=0).phase_tor()

    assert _posts(client) == [] and _puts(client) == []
    assert "S1_TOR1 already paired with S1_LE1/S1_LE2" in capsys.readouterr().out


def test_phase_tor_live_raises_when_nd_recommends_no_port_channel_ids():
    topo = _topo()
    topo = replace(topo, tor_pairs=[replace(topo.tor_pairs[0], tor_po=None, leaf_po=None, vpc_id=None)])
    candidate = {"accessOrTorSwitchId": "SN-S1_TOR1", "isRecommended": False, "remarks": "Switch(es) are not connected", "resources": {}}
    client = StubClient(_tor_responses(topo, associations=[], candidates=[candidate]))

    with pytest.raises(RuntimeError, match=r"no port-channel ids: ND recommends none .*not connected.* and tor_pairs gives none"):
        Provisioner(client, topo, settle_seconds=0).phase_tor()
    assert _posts(client) == []


def test_phase_tor_live_raises_when_the_tor_is_not_a_candidate_at_all():
    topo = _topo()
    topo = replace(topo, tor_pairs=[replace(topo.tor_pairs[0], tor_po=None, leaf_po=None, vpc_id=None)])
    client = StubClient(_tor_responses(topo, associations=[], candidates=[]))

    with pytest.raises(RuntimeError, match="S1_TOR1 -> S1_LE1/S1_LE2: no port-channel ids: ND recommends none"):
        Provisioner(client, topo, settle_seconds=0).phase_tor()


def test_phase_tor_live_raises_on_a_failed_multi_status_item_and_does_not_deploy():
    topo = _topo()
    candidate = {"accessOrTorSwitchId": "SN-S1_TOR1", "isRecommended": True, "resources": _TOR_RESOURCES}
    responses = _tor_responses(topo, associations=[], candidates=[candidate])
    responses["/fabrics/SITE1/accessAssociationActions/associate"] = {
        "associations": [{"accessOrTorSwitchId": "SN-S1_TOR1", "aggregationOrLeafSwitchId": "SN-S1_LE1", "status": "failed", "message": "port-channel 1 in use"}]
    }
    client = StubClient(responses)

    with pytest.raises(RuntimeError, match="S1_TOR1 -> S1_LE1/S1_LE2: association failed: port-channel 1 in use"):
        Provisioner(client, topo, settle_seconds=0).phase_tor()
    assert [p[1] for p in _posts(client)] == ["/fabrics/SITE1/accessAssociationActions/associate"]


def test_phase_order_runs_tor_after_vpc_and_before_isn():
    assert provision.PHASES == ["fabrics", "msd", "switches", "vpc", "tor", "isn", "overlay", "deploy"]


def test_phase_tor_live_falls_back_to_the_topology_ids_when_nd_recommends_none(capsys):
    """ND 4.2.1 answers every accessAssociations query with `resources: {}` (lab, 2026-09-14): the ids come from the YAML."""
    topo = _topo()
    candidate = {"accessOrTorSwitchId": "SN-S1_TOR1", "isRecommended": True, "resources": {}}
    responses = _tor_responses(topo, associations=[candidate], candidates=[candidate])
    responses["/fabrics/SITE1/accessAssociationActions/associate"] = {"associations": [{"accessOrTorSwitchId": "SN-S1_TOR1", "status": "success"}]}
    client = StubClient(responses)

    Provisioner(client, topo, settle_seconds=0).phase_tor()

    posts = _posts(client)
    assert [p[1] for p in posts] == ["/fabrics/SITE1/accessAssociationActions/associate", "/fabrics/SITE1/actions/configSave", "/fabrics/SITE1/actions/deploy"]
    assert posts[0][2][0]["resources"] == topo.tor_pairs[0].resources() == _TOR_RESOURCES
    assert "S1_TOR1 -> S1_LE1/S1_LE2: using topology ids" in capsys.readouterr().out


def test_phase_tor_live_prefers_nds_recommended_ids_over_the_topology_ids():
    topo = _topo()
    recommended = {"accessOrTorPortChannelId": 5, "aggregationOrLeafPortChannelId": 6, "aggregationOrLeafPeerPortChannelId": 6, "aggregationOrLeafVpcId": 6}
    candidate = {"accessOrTorSwitchId": "SN-S1_TOR1", "isRecommended": True, "resources": recommended}
    responses = _tor_responses(topo, associations=[], candidates=[candidate])
    responses["/fabrics/SITE1/accessAssociationActions/associate"] = {"associations": [{"accessOrTorSwitchId": "SN-S1_TOR1", "status": "success"}]}
    client = StubClient(responses)

    Provisioner(client, topo, settle_seconds=0).phase_tor()

    assert _posts(client)[0][2][0]["resources"] == recommended


def test_phase_tor_live_raises_when_neither_nd_nor_the_topology_supplies_ids():
    topo = _topo()
    topo = replace(topo, tor_pairs=[replace(topo.tor_pairs[0], tor_po=None, leaf_po=None, vpc_id=None)])
    candidate = {"accessOrTorSwitchId": "SN-S1_TOR1", "isRecommended": False, "remarks": "Switch(es) are not connected", "resources": {}}
    client = StubClient(_tor_responses(topo, associations=[], candidates=[candidate]))

    with pytest.raises(RuntimeError, match=r"S1_TOR1 -> S1_LE1/S1_LE2: no port-channel ids: ND recommends none .*not connected.* and tor_pairs gives none"):
        Provisioner(client, topo, settle_seconds=0).phase_tor()
    assert _posts(client) == []
