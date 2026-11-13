"""golden.py convert: the plan read from the live state (every intermediate state a stopped run can leave) and the ordered controller calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import golden
import golden_convert
import provision
from golden_convert import describe, plan
from golden_live import LiveFabric, LiveReadError
from provision import Provisioner
from replication import MODE_POLICIES
from tests.test_golden_apply import Stub
from topology import load

HERE = Path(__file__).resolve().parents[1]
TOPO_PATH = HERE / "topology_nd421.yaml"
MODE_FABRICS = ["SITE1", "SITE2"]


def topo(mode: str):
    return load(TOPO_PATH, replication_mode=mode)


def serial(host: str) -> str:
    return f"SN-{host}"


def _link(link_id: str, src: str, src_if: str, dst: str, dst_if: str, policy: str | None = "ebgpVrfLite") -> dict:
    return {
        "linkId": link_id,
        "srcSwitchName": src,
        "srcInterfaceName": src_if,
        "dstSwitchName": dst,
        "dstInterfaceName": dst_if,
        "configData": {"policyType": policy} if policy else None,
    }


ISN_S1 = _link("LINK-S1", "WAN1", "GigabitEthernet2", "S1_BG1", "Ethernet1/3")
ISN_S2 = _link("LINK-S2", "S2_BG1", "Ethernet1/3", "WAN1", "GigabitEthernet3")  # listed the other way round: matched direction-free
DISCOVERED = _link("LINK-D", "S1_SP1", "Ethernet1/1", "S1_LE1", "Ethernet1/1", policy=None)


def _rows(fabric: str, network: bool) -> list[dict]:
    """The live attachment rows of `fabric` for every golden attachment (VRF LAB / network LAB_NET1)."""
    t = topo("multicast")
    rows = []
    for att in t.overlay.network_attachments if network else t.overlay.vrf_attachments:
        if att["fabric"] != fabric:
            continue
        row = {"switchId": serial(att["switch"]), "switchName": att["switch"], "attach": True}
        rows.append({**row, "networkName": att["network"], "vlanId": att["vlan"], "interfaces": att["interfaces"]} if network else {**row, "vrfName": att["vrf"]})
    return rows


def _testbed(
    mode: str, *, overlay: bool = True, attached: bool = True, members: bool = True, links: bool = True, policies=None, pending: int = 0
) -> dict[str, LiveFabric]:
    """A live testbed read by hand: SITE1/SITE2 saved in `mode`, holding `policies` (default: `mode`'s own), `pending` lines per switch;
    the golden MSD overlay (VRF LAB, network LAB_NET1, attached on every golden switch unless `attached` is false), membership and ISN
    links as asked."""
    t = topo("multicast")
    live: dict[str, LiveFabric] = {}
    for f in t.fabrics:
        fab = LiveFabric(f.name, "fabric", switches={s.hostname: {"hostname": s.hostname, "serialNumber": serial(s.hostname)} for s in f.switches})
        if f.name in MODE_FABRICS:
            fab.settings = {"management": {"replicationMode": mode}}
            fab.mode_policies = {h: set(MODE_POLICIES[mode] if policies is None else policies) for h in fab.switches}
            fab.pending = {h: pending for h in fab.switches}
        live[f.name] = fab
    live["MSD"] = LiveFabric("MSD", "fabricGroup", members=["SITE1", "SITE2", "ISN"] if members else ["ISN"])
    if overlay:
        live["MSD"].vrfs = [{"vrfName": "LAB"}]
        live["MSD"].networks = [{"networkName": "LAB_NET1"}]
        for fabric in MODE_FABRICS:
            live[fabric].vrfs = [{"vrfName": "LAB"}, {"vrfName": "default"}]
            live[fabric].networks = [{"networkName": "LAB_NET1"}]
            if attached:
                live[fabric].vrf_attachments = _rows(fabric, network=False)
                live[fabric].network_attachments = _rows(fabric, network=True)
    if links:
        live["SITE1"].links = [ISN_S1, DISCOVERED]
        live["SITE2"].links = [ISN_S2]
        live["ISN"].links = [ISN_S1, ISN_S2]
    return live


def _summary(ops) -> list[tuple[str, str, str]]:
    return [(o.action, o.method, o.path) for o in ops]


GOLDEN_TEARDOWN = [  # one detach per golden attachment (SITE1: 4 network, 3 VRF; SITE2: 2 and 2), one deploy per fabric
    *[("detach", "POST", "/fabrics/SITE1/networkAttachments")] * 4,
    ("deploy_overlay", "POST", "/fabrics/SITE1/networkActions/deploy"),
    *[("detach", "POST", "/fabrics/SITE2/networkAttachments")] * 2,
    ("deploy_overlay", "POST", "/fabrics/SITE2/networkActions/deploy"),
    *[("detach", "POST", "/fabrics/SITE1/vrfAttachments")] * 3,
    ("deploy_overlay", "POST", "/fabrics/SITE1/vrfActions/deploy"),
    *[("detach", "POST", "/fabrics/SITE2/vrfAttachments")] * 2,
    ("deploy_overlay", "POST", "/fabrics/SITE2/vrfActions/deploy"),
    ("delete_network", "DELETE", "/fabrics/MSD/networks/LAB_NET1"),
    ("delete_vrf", "DELETE", "/fabrics/MSD/vrfs/LAB"),
]
GOLDEN_LINKS = [("SITE1", "LINK-S1", "WAN1 GigabitEthernet2 <-> S1_BG1 Ethernet1/3"), ("SITE2", "LINK-S2", "S2_BG1 Ethernet1/3 <-> WAN1 GigabitEthernet3")]


# --- plan ---


def test_plan_from_an_intact_multicast_testbed():
    p = plan(topo("ingress"), _testbed("multicast"))
    assert p.target == "ingress" and p.states == {"SITE1": "multicast", "SITE2": "multicast"}
    assert p.intact_source and p.convert == ["SITE1", "SITE2"] and p.leave == [("MSD", "SITE1"), ("MSD", "SITE2")]
    assert [o.action for o in p.overlay_ops][-2:] == ["delete_network", "delete_vrf"] and len(p.link_ids) == 2
    assert _summary(p.overlay_ops) == GOLDEN_TEARDOWN
    detach = p.overlay_ops[0].body["attachments"][0]
    assert detach["attach"] is False and detach["switchId"] == "SN-S1_LE1" and detach["networkName"] == "LAB_NET1"
    assert p.link_ids == GOLDEN_LINKS  # the discovered (policy-less) link and the ISN fabric's own copies are not touched


def test_plan_from_an_intact_ingress_testbed_to_multicast():
    p = plan(topo("multicast"), _testbed("ingress"))
    assert p.target == "multicast" and p.states == {"SITE1": "ingress", "SITE2": "ingress"}
    assert p.intact_source and p.convert == ["SITE1", "SITE2"] and p.leave == [("MSD", "SITE1"), ("MSD", "SITE2")]
    assert _summary(p.overlay_ops) == GOLDEN_TEARDOWN and p.link_ids == GOLDEN_LINKS


def test_plan_includes_non_golden_overlay_and_links():
    live = _testbed("multicast")
    live["SITE1"].networks.append({"networkName": "TEST_NET"})
    live["SITE1"].network_attachments.append({"switchId": "SN-S1_LE2", "switchName": "S1_LE2", "networkName": "TEST_NET", "vlanId": 3000, "attach": True})
    live["MSD"].vrfs.append({"vrfName": "TEST_VRF"})  # a group-level residue VRF with no attachments
    extra_link = _link("LINK-X", "S1_BG1", "Ethernet1/4", "WAN1", "GigabitEthernet4")
    live["SITE1"].links.append(extra_link)
    p = plan(topo("ingress"), live)
    deletes = [(o.action, o.path) for o in p.overlay_ops if o.action.startswith("delete_")]
    assert deletes == [
        ("delete_network", "/fabrics/MSD/networks/LAB_NET1"),
        ("delete_network", "/fabrics/SITE1/networks/TEST_NET"),
        ("delete_vrf", "/fabrics/MSD/vrfs/LAB"),
        ("delete_vrf", "/fabrics/MSD/vrfs/TEST_VRF"),
    ]
    assert ("detach", "POST", "/fabrics/SITE1/networkAttachments") in _summary(p.overlay_ops)
    assert [o.body["attachments"][0]["switchId"] for o in p.overlay_ops if o.action == "detach" and o.fabric == "SITE1" and "network" in o.path] == [
        "SN-S1_LE1",
        "SN-S1_LE2",
        "SN-S1_BG1",
        "SN-S1_TOR1",
        "SN-S1_LE2",  # TEST_NET's
    ]
    assert p.link_ids == [*GOLDEN_LINKS[:1], ("SITE1", "LINK-X", "S1_BG1 Ethernet1/4 <-> WAN1 GigabitEthernet4 (not in golden)"), GOLDEN_LINKS[1]]
    assert p.intact_source  # residue does not make a testbed less intact


def test_plan_resumes_with_no_overlay():
    p = plan(topo("ingress"), _testbed("multicast", overlay=False))
    assert p.overlay_ops == [] and p.redeploy == []
    assert not p.intact_source  # the overlay is part of an intact testbed: a run that removed it is resumed, not refused
    assert p.convert == ["SITE1", "SITE2"] and p.leave == [("MSD", "SITE1"), ("MSD", "SITE2")] and p.link_ids == GOLDEN_LINKS


def test_plan_with_the_overlay_detached_but_not_deleted_is_not_intact():
    p = plan(topo("ingress"), _testbed("multicast", attached=False))
    assert not p.intact_source and p.convert == ["SITE1", "SITE2"]
    assert _summary(p.overlay_ops) == [("delete_network", "DELETE", "/fabrics/MSD/networks/LAB_NET1"), ("delete_vrf", "DELETE", "/fabrics/MSD/vrfs/LAB")]


def test_plan_with_one_golden_attachment_missing_is_not_intact():
    live = _testbed("multicast")
    live["SITE1"].network_attachments = [r for r in live["SITE1"].network_attachments if r["switchName"] != "S1_TOR1"]
    assert not plan(topo("ingress"), live).intact_source


def test_plan_redeploys_pending_mode_fabrics_before_the_deletes_of_a_resume():
    p = plan(topo("ingress"), _testbed("multicast", attached=False, pending=2))
    assert not p.intact_source and p.redeploy == ["SITE1", "SITE2"]
    assert "Recalculate and Deploy SITE1, SITE2 first" in describe(p)


def test_plan_does_not_redeploy_without_deletes_or_on_an_intact_testbed():
    assert plan(topo("ingress"), _testbed("multicast", overlay=False, pending=2)).redeploy == []  # nothing to delete
    assert plan(topo("ingress"), _testbed("multicast", pending=2)).redeploy == []  # intact: refused before any write
    assert plan(topo("ingress"), _testbed("multicast", attached=False)).redeploy == []  # nothing pending


def test_plan_resumes_out_of_group_with_links_deleted():
    p = plan(topo("ingress"), _testbed("multicast", overlay=False, members=False, links=False))
    assert p.leave == [] and p.link_ids == [] and p.overlay_ops == []
    assert p.convert == ["SITE1", "SITE2"] and not p.intact_source


def test_plan_resumes_with_links_left_but_out_of_group_is_not_intact():
    p = plan(topo("ingress"), _testbed("multicast", overlay=False, members=False))
    assert p.leave == [] and p.link_ids == GOLDEN_LINKS and not p.intact_source


def test_plan_treats_a_saved_but_undeployed_setting_as_not_converted():
    live = _testbed("ingress", policies={"base_multicast_11_1"}, overlay=False, members=False, links=False)
    p = plan(topo("ingress"), live)
    assert p.convert == ["SITE1", "SITE2"] and p.states == {"SITE1": "mid", "SITE2": "mid"} and not p.intact_source


def test_plan_treats_pending_config_alone_after_the_change_as_converted():
    p = plan(topo("ingress"), _testbed("ingress", overlay=False, members=False, links=False, pending=4))
    assert p.convert == [] and not p.intact_source and p.states == {"SITE1": "ingress", "SITE2": "ingress"}
    assert p.overlay_ops == [] and p.leave == [] and p.link_ids == []


def test_plan_with_pending_config_alone_and_a_live_overlay_tears_nothing_down():
    p = plan(topo("ingress"), _testbed("ingress", pending=4))  # a rebuild that stopped after recreating members, links and overlay
    assert p.convert == [] and p.overlay_ops == [] and p.leave == [] and p.link_ids == []


def test_plan_counts_an_intact_source_with_pending_config_as_intact():
    p = plan(topo("ingress"), _testbed("multicast", pending=2))
    assert p.states == {"SITE1": "multicast", "SITE2": "multicast"} and p.intact_source and p.convert == ["SITE1", "SITE2"]


def test_plan_for_a_converted_but_unrebuilt_testbed_has_nothing_to_convert():
    p = plan(topo("ingress"), _testbed("ingress", overlay=False, members=False, links=False))
    assert p.convert == [] and not p.intact_source and p.states == {"SITE1": "ingress", "SITE2": "ingress"}
    assert p.overlay_ops == [] and p.leave == [] and p.link_ids == []


def test_plan_for_a_finished_testbed_is_empty():
    p = plan(topo("ingress"), _testbed("ingress"))
    assert p.convert == [] and not p.intact_source
    assert p.overlay_ops == [] and p.leave == [] and p.link_ids == []  # nothing is torn down when no fabric needs converting


# --- run ---


@pytest.fixture(autouse=True)
def _no_settle_sleep(monkeypatch):
    monkeypatch.setattr(provision.time, "sleep", lambda _seconds: None)


class Client(Stub):
    """Stub NDClient: every write recorded; pendingConfig answers from `pending_lines` (path -> lines), GET /fabrics/<mode fabric> from
    `fabrics` (default: the multicast source setting), every other GET is HTTP 404."""

    def __init__(self, post_results=None, pending_lines=None, fabrics=None):
        super().__init__(post_results=post_results)
        self.pending_lines = pending_lines or {}
        self.fabrics = {f"/fabrics/{f}": {"management": {"replicationMode": "multicast"}} for f in MODE_FABRICS} if fabrics is None else fabrics

    def get(self, path, params=None):
        if path.endswith("/pendingConfig"):
            self.calls.append(("GET", path, params))
            return {"pendingConfigs": self.pending_lines.get(path, [])}
        if path in self.fabrics:
            self.calls.append(("GET", path, params))
            return self.fabrics[path]
        return super().get(path, params)

    def ordered(self) -> list[tuple[str, str]]:
        return [(c[0], c[1]) for c in self.calls if c[0] not in ("GET",)]

    def body(self, method: str, path: str):
        return next(c[2] for c in self.calls if c[0] == method and c[1] == path)


class Harness:
    def __init__(self, monkeypatch, reads, final_drift=None, client=None):
        self.reads = list(reads)
        self.client = client or Client()
        self.restores: list = []
        self.lines: list[str] = []
        self.prompts: list[str] = []
        self.answer = "y"
        self.restore_code = 0

        def read(client, topo_):
            if not self.reads:
                pytest.fail("unexpected live read")
            item = self.reads.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        def restore(args, topo_, live, prov, ask, out):
            self.client.calls.append(("RESTORE", topo_.replication_mode))
            self.restores.append((args, topo_, live))
            return self.restore_code

        monkeypatch.setattr(golden_convert, "read_live", read)
        monkeypatch.setattr(golden_convert, "run_restore", restore)
        monkeypatch.setattr(golden_convert, "compute", lambda topo_, live: list(final_drift or []))

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer

    def run(self, target: str = "ingress", **kw) -> int:
        base = dict(topology=TOPO_PATH, nd_ip="192.0.2.1", replication_mode=target, yes=True, extras="skip", dry_run=False)
        base.update(kw)
        t = topo(target)
        return golden_convert.run(SimpleNamespace(**base), t, Provisioner(self.client, t), self.ask, self.lines.append)


def deploys(fabric: str) -> list[tuple[str, str]]:
    return [("POST", f"/fabrics/{fabric}/actions/configSave"), ("POST", f"/fabrics/{fabric}/actions/deploy")]


def test_run_converts_an_intact_multicast_testbed_in_order(monkeypatch):
    rebuild_live = _testbed("ingress", overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [_testbed("multicast"), _testbed("ingress", overlay=False, members=False, links=False), rebuild_live, _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered() == [
        *[(method, path) for _, method, path in GOLDEN_TEARDOWN],
        ("POST", "/fabrics/MSD/actions/removeMembers"),
        ("POST", "/fabrics/MSD/actions/removeMembers"),
        *deploys("SITE1"),
        *deploys("SITE2"),
        ("DELETE", "/links/LINK-S1"),
        ("DELETE", "/links/LINK-S2"),
        ("PUT", "/fabrics/SITE1"),
        *deploys("SITE1"),
        ("PUT", "/fabrics/SITE2"),
        *deploys("SITE2"),
        ("RESTORE", "ingress"),
    ]
    removes = [c[2] for c in h.client.calls if c[1] == "/fabrics/MSD/actions/removeMembers"]
    assert removes == [{"members": [{"name": "SITE1"}]}, {"members": [{"name": "SITE2"}]}]
    put = h.client.body("PUT", "/fabrics/SITE1")
    assert put["management"]["replicationMode"] == "ingress" and "anycastRendezvousPointIpRange" not in put["management"]
    assert put["management"]["bgpLoopbackIpRange"] == "10.11.0.0/22"  # the rest of the golden settings ride along
    (restore_args, restore_topo, restore_live) = h.restores[0]
    assert restore_live is rebuild_live and restore_topo.replication_mode == "ingress"
    assert restore_args.yes is True and restore_args.extras == "skip" and restore_args.no_deploy is False
    assert h.reads == [] and h.prompts == [] and "convert: done" in h.lines[-1]


def test_run_converts_an_intact_ingress_testbed_back_to_multicast(monkeypatch):
    h = Harness(monkeypatch, [_testbed("ingress"), _testbed("multicast", overlay=False, members=False, links=False), _testbed("multicast"), _testbed("multicast")])
    assert h.run("multicast") == 0
    put = h.client.body("PUT", "/fabrics/SITE2")
    assert put["management"]["replicationMode"] == "multicast" and put["management"]["anycastRendezvousPointIpRange"] == "10.23.0.0/24"
    assert h.client.ordered()[-1] == ("RESTORE", "multicast")


def test_run_refuses_an_intact_source_with_pending_config(monkeypatch):
    h = Harness(monkeypatch, [_testbed("multicast", pending=2)])
    assert h.run() == 2
    assert h.client.ordered() == [] and h.restores == []
    assert "pending" in h.lines[-1] and "SITE1" in h.lines[-1]


def test_run_resumes_with_the_overlay_gone_still_in_the_group_with_pending_config(monkeypatch):
    start = _testbed("multicast", overlay=False, pending=2)  # a run that stopped after removing the overlay
    h = Harness(monkeypatch, [start, _testbed("ingress", overlay=False, members=False, links=False), _testbed("ingress"), _testbed("ingress")])
    assert h.run() == 0
    assert not any("refused" in line for line in h.lines)
    assert h.client.ordered() == [
        ("POST", "/fabrics/MSD/actions/removeMembers"),
        ("POST", "/fabrics/MSD/actions/removeMembers"),
        *deploys("SITE1"),
        *deploys("SITE2"),
        ("DELETE", "/links/LINK-S1"),
        ("DELETE", "/links/LINK-S2"),
        ("PUT", "/fabrics/SITE1"),
        *deploys("SITE1"),
        ("PUT", "/fabrics/SITE2"),
        *deploys("SITE2"),
        ("RESTORE", "ingress"),
    ]


def test_run_resumes_a_detached_overlay_with_pending_config_by_redeploying_before_the_deletes(monkeypatch):
    start = _testbed("multicast", attached=False, pending=2)  # detached, the deletes never ran (or ND refused them)
    h = Harness(monkeypatch, [start, _testbed("ingress", overlay=False, members=False, links=False), _testbed("ingress"), _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered()[:6] == [
        *deploys("SITE1"),
        *deploys("SITE2"),
        ("DELETE", "/fabrics/MSD/networks/LAB_NET1"),
        ("DELETE", "/fabrics/MSD/vrfs/LAB"),
    ]
    assert h.client.ordered()[6:8] == [("POST", "/fabrics/MSD/actions/removeMembers")] * 2 and h.client.ordered()[-1] == ("RESTORE", "ingress")
    assert any("Recalculate and Deploy SITE1, SITE2 first" in line for line in h.lines)  # the plan says so
    assert [line for line in h.lines if line.endswith("before the deletes")] == [
        f"convert: {f} has pending config from an earlier run (a detach whose deploy may not have finished); Recalculate and Deploy it before the deletes"
        for f in ("SITE1", "SITE2")
    ]


class RefusesDeletes(Client):
    """DELETE of a path in `refusals` answers HTTP `status` that many times (ND still finishing the asynchronous detach)."""

    def __init__(self, refusals, status=400, **kw):
        super().__init__(**kw)
        self.refusals = dict(refusals)
        self.status = status

    def delete(self, path):
        self.calls.append(("DELETE", path, None))
        if self.refusals.get(path):
            self.refusals[path] -= 1
            raise RuntimeError(f"DELETE {path} -> HTTP {self.status}: network LAB_NET1 is attached to a switch")
        return None


def _sleeps(monkeypatch) -> list:
    """The retry waits (the `time` module is shared, so the deploy's settle sleeps are filtered out by their length)."""
    import golden_apply

    slept: list = []
    monkeypatch.setattr(golden_apply.time, "sleep", lambda seconds: slept.append(seconds) if seconds == golden_apply.TYPE_CHANGE_WAIT else None)
    return slept


def test_run_retries_an_overlay_delete_refused_while_the_detach_finishes(monkeypatch):
    slept = _sleeps(monkeypatch)
    client = RefusesDeletes({"/fabrics/MSD/networks/LAB_NET1": 2})
    start = _testbed("multicast", attached=False)
    h = Harness(monkeypatch, [start, _testbed("ingress", overlay=False, members=False, links=False), _testbed("ingress"), _testbed("ingress")], client=client)
    assert h.run() == 0
    assert h.client.ordered()[:4] == [("DELETE", "/fabrics/MSD/networks/LAB_NET1")] * 3 + [("DELETE", "/fabrics/MSD/vrfs/LAB")]
    assert len(slept) == 2


def test_run_overlay_delete_refused_past_the_budget_exits_4_naming_the_step(monkeypatch):
    import golden_apply

    slept = _sleeps(monkeypatch)
    client = RefusesDeletes({"/fabrics/MSD/networks/LAB_NET1": 50})
    h = Harness(monkeypatch, [_testbed("multicast", attached=False)], client=client)
    assert h.run() == 4
    assert h.client.ordered() == [("DELETE", "/fabrics/MSD/networks/LAB_NET1")] * golden_apply.TYPE_CHANGE_TRIES  # nothing after it
    assert len(slept) == golden_apply.TYPE_CHANGE_TRIES - 1 and h.restores == []
    assert "remove overlay failed" in h.lines[-1] and "HTTP 400" in h.lines[-1]


def test_run_overlay_delete_server_error_is_not_retried(monkeypatch):
    slept = _sleeps(monkeypatch)
    client = RefusesDeletes({"/fabrics/MSD/networks/LAB_NET1": 50}, status=500)
    h = Harness(monkeypatch, [_testbed("multicast", attached=False)], client=client)
    assert h.run() == 4
    assert h.client.ordered() == [("DELETE", "/fabrics/MSD/networks/LAB_NET1")] and slept == []
    assert "remove overlay failed" in h.lines[-1]


def test_run_resumes_a_broken_testbed_with_pending_config(monkeypatch):
    start = _testbed("multicast", overlay=False, members=False, pending=2)  # out of the group: pending config is expected
    h = Harness(monkeypatch, [start, _testbed("ingress", overlay=False, members=False, links=False), _testbed("ingress"), _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered() == [
        ("DELETE", "/links/LINK-S1"),
        ("DELETE", "/links/LINK-S2"),
        ("PUT", "/fabrics/SITE1"),
        *deploys("SITE1"),
        ("PUT", "/fabrics/SITE2"),
        *deploys("SITE2"),
        ("RESTORE", "ingress"),
    ]


def test_run_finishes_a_saved_but_undeployed_setting_before_rebuilding(monkeypatch):
    start = _testbed("ingress", policies={"base_multicast_11_1"}, overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [start, _testbed("ingress", overlay=False, members=False, links=False), _testbed("ingress"), _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered() == [("PUT", "/fabrics/SITE1"), *deploys("SITE1"), ("PUT", "/fabrics/SITE2"), *deploys("SITE2"), ("RESTORE", "ingress")]


def test_run_on_a_converted_but_unrebuilt_testbed_only_rebuilds(monkeypatch):
    bare = _testbed("ingress", overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [bare, bare, _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered() == [("RESTORE", "ingress")] and h.reads == []


def test_run_with_pending_config_alone_goes_straight_to_the_rebuild(monkeypatch):
    start = _testbed("ingress", overlay=False, members=False, links=False, pending=4)
    h = Harness(monkeypatch, [start, start, _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered() == [("RESTORE", "ingress")] and h.reads == []
    assert h.restores[0][2] is start


def test_run_proceeds_to_the_rebuild_when_pending_lines_survive_the_second_deploy(monkeypatch):
    start = _testbed("multicast", overlay=False, members=False, links=False)
    left = _testbed("ingress", overlay=False, members=False, links=False, pending=3)
    h = Harness(monkeypatch, [start, left, left, left, _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered() == [
        ("PUT", "/fabrics/SITE1"),
        *deploys("SITE1"),
        ("PUT", "/fabrics/SITE2"),
        *deploys("SITE2"),
        *deploys("SITE1"),
        *deploys("SITE2"),
        ("RESTORE", "ingress"),
    ]
    assert h.reads == []


def test_run_dry_run_prints_the_first_step_and_sends_nothing(monkeypatch):
    h = Harness(monkeypatch, [_testbed("multicast")])
    assert h.run(dry_run=True, yes=False, extras=None) == 0
    assert h.client.ordered() == [] and h.restores == [] and h.prompts == []
    text = "\n".join(h.lines)
    assert "SITE1=multicast" in text and "network LAB_NET1" in text and "LINK-S1" in text
    assert "POST /fabrics/SITE1/networkAttachments" in text and "DELETE /fabrics/MSD/vrfs/LAB" in text
    assert "POST /fabrics/MSD/actions/removeMembers" not in text  # only the first step with work is spelled out as calls


def test_run_dry_run_of_a_resume_lists_the_redeploy_before_the_deletes(monkeypatch):
    h = Harness(monkeypatch, [_testbed("multicast", attached=False, pending=2)])
    assert h.run(dry_run=True) == 0 and h.client.ordered() == []
    calls = h.lines[-1].splitlines()
    assert [c.split()[1] for c in calls[:5]] == [
        "/fabrics/SITE1/actions/configSave",
        "/fabrics/SITE1/actions/deploy",
        "/fabrics/SITE2/actions/configSave",
        "/fabrics/SITE2/actions/deploy",
        "/fabrics/MSD/networks/LAB_NET1",
    ]


def test_run_dry_run_of_a_later_step_prints_its_calls(monkeypatch):
    h = Harness(monkeypatch, [_testbed("ingress", policies={"base_multicast_11_1"}, overlay=False, members=False, links=False)])
    assert h.run(dry_run=True) == 0
    text = "\n".join(h.lines)
    assert "PUT /fabrics/SITE1 " in text and "POST /fabrics/SITE2/actions/deploy" in text and h.client.ordered() == []


def test_run_dry_run_of_the_rebuild_prints_the_drift_it_starts_from(monkeypatch):
    import golden_drift

    bare = _testbed("ingress", overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [bare])
    monkeypatch.setattr(golden_convert, "compute", golden_drift.compute)
    assert h.run(dry_run=True) == 0
    text = "\n".join(h.lines)
    assert "first step with work: rebuild" in text and "MSD members    MISSING policy  SITE1" in text and h.client.ordered() == []


def test_run_yes_without_extras_exits_2_before_any_write(monkeypatch):
    h = Harness(monkeypatch, [_testbed("multicast")])
    assert h.run(yes=True, extras=None) == 2
    assert h.client.ordered() == [] and "--extras" in h.lines[-1]


def test_run_without_yes_asks_and_a_no_cancels(monkeypatch):
    h = Harness(monkeypatch, [_testbed("multicast")])
    h.answer = "n"
    assert h.run(yes=False, extras=None) == 2
    assert len(h.prompts) == 1 and "192.0.2.1" in h.prompts[0] and h.client.ordered() == [] and h.lines[-1] == "convert: cancelled"


def test_run_stops_with_4_when_a_fabric_is_still_not_in_the_target_mode(monkeypatch):
    stuck = _testbed("ingress", policies={"base_multicast_11_1"}, overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [_testbed("multicast", overlay=False, members=False, links=False), stuck])
    assert h.run() == 4
    assert h.restores == [] and h.client.ordered() == [("PUT", "/fabrics/SITE1"), *deploys("SITE1"), ("PUT", "/fabrics/SITE2"), *deploys("SITE2")]
    assert "SITE1" in h.lines[-1] and "SITE2" in h.lines[-1] and "ingress" in h.lines[-1]


def test_run_deploys_once_more_when_only_pending_lines_are_left(monkeypatch):
    start = _testbed("multicast", overlay=False, members=False, links=False)
    left = _testbed("ingress", overlay=False, members=False, links=False)
    left["SITE2"].pending = {h: 3 for h in left["SITE2"].pending or {}}
    after = _testbed("ingress", overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [start, left, after, after, _testbed("ingress")])
    assert h.run() == 0
    assert h.client.ordered() == [
        ("PUT", "/fabrics/SITE1"),
        *deploys("SITE1"),
        ("PUT", "/fabrics/SITE2"),
        *deploys("SITE2"),
        *deploys("SITE2"),
        ("RESTORE", "ingress"),
    ]


def test_run_apply_error_in_the_teardown_exits_4_naming_the_step(monkeypatch):
    failed = {"/fabrics/SITE1/networkAttachments": {"results": [{"status": "failed", "message": "boom"}]}}
    h = Harness(monkeypatch, [_testbed("multicast")], client=Client(post_results=failed))
    assert h.run() == 4
    assert h.client.ordered() == [("POST", "/fabrics/SITE1/networkAttachments")] and h.restores == []
    assert "remove overlay" in h.lines[-1] and "boom" in h.lines[-1]


def test_run_mode_put_is_built_from_a_read_taken_after_the_teardown(monkeypatch):
    class LeaveChangesSettings(Client):
        def post(self, path, json=None, timeout=None):
            if path.endswith("/removeMembers"):  # ND rewrites an inherited field when a fabric leaves the group
                self.fabrics[f"/fabrics/{json['members'][0]['name']}"] = {"management": {"replicationMode": "multicast", "siteId": "after-leave"}}
            return super().post(path, json, timeout)

    client = LeaveChangesSettings()
    start = _testbed("multicast", overlay=False, links=False)
    for f in MODE_FABRICS:
        start[f].settings = {"management": {"replicationMode": "multicast", "siteId": "preflight"}}
    h = Harness(monkeypatch, [start, _testbed("ingress", overlay=False, members=False, links=False), _testbed("ingress"), _testbed("ingress")], client=client)
    assert h.run() == 0
    for f in MODE_FABRICS:
        put = client.body("PUT", f"/fabrics/{f}")
        assert put["management"]["siteId"] == "after-leave" and put["management"]["replicationMode"] == "ingress"
    reads = [c[1] for c in client.calls if c[0] in ("GET", "PUT") and c[1] in ("/fabrics/SITE1", "/fabrics/SITE2")]
    assert reads == ["/fabrics/SITE1", "/fabrics/SITE1", "/fabrics/SITE2", "/fabrics/SITE2"]  # GET then PUT, per fabric


def test_run_failed_settings_read_before_the_mode_put_exits_3_with_no_put(monkeypatch):
    client = Client(fabrics={})  # GET /fabrics/SITE1 answers HTTP 404
    h = Harness(monkeypatch, [_testbed("multicast", overlay=False, members=False, links=False)], client=client)
    assert h.run() == 3
    assert h.client.ordered() == [] and h.restores == []
    assert "change mode to ingress" in h.lines[-1] and "GET /fabrics/SITE1" in h.lines[-1]


@pytest.mark.parametrize("body", [{}, None, {"management": {}}, {"management": {"replicationMode": "bogus"}}])
def test_run_settings_read_without_a_valid_mode_exits_3_with_no_put(monkeypatch, body):
    client = Client(fabrics={"/fabrics/SITE1": body, "/fabrics/SITE2": {"management": {"replicationMode": "multicast"}}})
    h = Harness(monkeypatch, [_testbed("multicast", overlay=False, members=False, links=False)], client=client)
    assert h.run() == 3
    assert h.client.ordered() == [] and h.restores == []
    assert "change mode to ingress" in h.lines[-1] and "SITE1" in h.lines[-1] and "replicationMode" in h.lines[-1]


def test_run_rebuild_with_zero_drift_deploys_the_pending_lines_and_ends_0(monkeypatch):
    class DeployClears(Client):
        def post(self, path, json=None, timeout=None):
            if path == "/fabrics/SITE1/actions/deploy":
                self.pending_lines.clear()
            return super().post(path, json, timeout)

    pending_path = "/fabrics/SITE1/switches/SN-S1_LE1/pendingConfig"
    client = DeployClears(pending_lines={pending_path: ["interface Ethernet1/3"]})
    done = _testbed("ingress", pending=1)
    h = Harness(monkeypatch, [done, done, done], client=client)
    monkeypatch.setattr(golden_convert, "run_restore", golden.run_restore)  # the real restore: no drift, so it deploys what is pending
    monkeypatch.setattr(golden, "compute", lambda topo_, live: [])
    assert h.run() == 0
    assert h.client.ordered() == deploys("SITE1")
    assert "restore: no drift; deployed SITE1, which had pending config" in h.lines and "convert: done" in h.lines[-1]


def test_run_deploy_error_in_the_leave_step_exits_4_before_any_link_delete(monkeypatch):
    class DeployFails(Client):
        def post(self, path, json=None, timeout=None):
            if path == "/fabrics/SITE1/actions/deploy":
                self.calls.append(("POST", path, json))
                raise RuntimeError("POST /fabrics/SITE1/actions/deploy -> HTTP 500")
            return super().post(path, json, timeout)

    h = Harness(monkeypatch, [_testbed("multicast", overlay=False)], client=DeployFails())
    assert h.run() == 4
    assert h.client.ordered() == [
        ("POST", "/fabrics/MSD/actions/removeMembers"),
        ("POST", "/fabrics/MSD/actions/removeMembers"),
        *deploys("SITE1"),
    ]
    assert h.restores == [] and "leave fabric group failed" in h.lines[-1] and "HTTP 500" in h.lines[-1]


def test_run_verify_read_failure_exits_3_without_the_rebuild(monkeypatch):
    h = Harness(monkeypatch, [_testbed("multicast", overlay=False, members=False, links=False), LiveReadError("GET /fabrics/SITE1/policies: HTTP 500")])
    assert h.run() == 3
    assert h.restores == [] and "verify mode" in h.lines[-1] and "HTTP 500" in h.lines[-1]
    assert h.client.ordered() == [("PUT", "/fabrics/SITE1"), *deploys("SITE1"), ("PUT", "/fabrics/SITE2"), *deploys("SITE2")]


def test_run_initial_read_failure_exits_3(monkeypatch):
    h = Harness(monkeypatch, [LiveReadError("GET /fabrics: HTTP 500")])
    assert h.run() == 3
    assert h.client.ordered() == [] and "HTTP 500" in h.lines[-1]


def test_run_exits_4_when_drift_remains_after_the_rebuild(monkeypatch):
    bare = _testbed("ingress", overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [bare, bare, bare], final_drift=["one"])
    assert h.run() == 4
    assert "1 drift" in h.lines[-1]


def test_run_exits_4_when_pending_config_remains_after_the_rebuild(monkeypatch):
    bare = _testbed("ingress", overlay=False, members=False, links=False)
    client = Client(pending_lines={"/fabrics/CAMPUS1/switches/SN-C1_LE1/pendingConfig": ["line"]})
    h = Harness(monkeypatch, [bare, bare, bare], client=client)
    assert h.run() == 4
    assert "CAMPUS1" in h.lines[-1]


def test_run_passes_a_restore_failure_through(monkeypatch):
    bare = _testbed("ingress", overlay=False, members=False, links=False)
    h = Harness(monkeypatch, [bare, bare])
    h.restore_code = 4
    assert h.run() == 4 and h.reads == []


# --- golden.py main ---


def test_main_convert_loads_the_target_mode_without_detection(monkeypatch):
    seen: list = []

    class LoginOnly:
        def __init__(self, creds):
            self.creds = creds

        def login(self):
            pass

        def get(self, *a, **kw):
            pytest.fail("convert must not detect the mode")

    monkeypatch.setattr(golden, "NDCredentials", SimpleNamespace(from_env=lambda ip: SimpleNamespace(ip=ip)))
    monkeypatch.setattr(golden, "NDClient", LoginOnly)
    monkeypatch.setattr(golden_convert, "run", lambda args, t, prov, ask, out: seen.append((args, t)) or 0)
    argv = ["convert", "--topology", str(TOPO_PATH), "--nd-ip", "1.1.1.1", "--replication-mode", "ingress", "--yes", "--extras", "delete", "--dry-run"]
    assert golden.main(argv, out=lambda m: None) == 0
    args, t = seen[0]
    assert t.replication_mode == "ingress" and args.yes and args.extras == "delete" and args.dry_run


def test_main_convert_requires_the_target_mode():
    with pytest.raises(SystemExit) as exc:
        golden.main(["convert", "--topology", str(TOPO_PATH)], out=lambda m: None)
    assert exc.value.code == 2
