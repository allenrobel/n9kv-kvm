"""golden.py CLI: drift exit codes, extras prompting, restore ordering/confirmation, exit codes. I/O and the controller are injected or stubbed."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import golden
from golden_apply import ApplyError
from golden_drift import Adoption, Drift, Op
from golden_live import LiveFabric, LiveReadError, read_live_from_snapshot
from topology import load

HERE = Path(__file__).resolve().parents[1]
TOPO_PATH = HERE / "topology_nd421.yaml"
SNAP = HERE / "golden" / "nd421"


def op(action: str, fabric: str = "SITE1", method: str = "PUT", path: str = "/x") -> Op:
    return Op(action, fabric, method, path, {})


def drift(kind: str, subject: str, fix=None, delete=None, adopt=None, fabric: str = "SITE1") -> Drift:
    return Drift("links", fabric, kind, subject, "g", "l", fix, delete, adopt)  # type: ignore[arg-type]


ADOPT = Adoption(("fabrics", "SITE1", "links"), {"src": "A"})


class Recorder:
    """Shared call log for the stubbed Applier, write_adoptions and the Provisioner."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.apply_error: Exception | None = None
        self.deploy_error: Exception | None = None


@pytest.fixture
def rec(monkeypatch):
    r = Recorder()
    live = {"SITE1": LiveFabric("SITE1", "fabric", switches={"S1_SP1": {"serialNumber": "SER1"}})}

    class StubApplier:
        def __init__(self, prov):
            pass

        def apply(self, ops):
            r.calls.append(("apply", list(ops)))
            if r.apply_error:
                raise r.apply_error
            return {o.fabric for o in ops}

        def deploy(self, touched, topo):
            r.calls.append(("deploy", sorted(touched)))
            if r.deploy_error:
                raise r.deploy_error

    def write(path, adoptions):
        r.calls.append(("write", list(adoptions)))
        return len(adoptions)

    monkeypatch.setattr(golden, "Applier", StubApplier)
    monkeypatch.setattr(golden, "write_adoptions", write)
    monkeypatch.setattr(golden, "read_live", lambda client, topo: live)
    r.live = live  # type: ignore[attr-defined]
    return r


def prov_stub(rec=None):
    """pending lines appear only once something was deployed (so the pre-apply check finds nothing from an earlier run)."""
    deployed = lambda: rec is not None and any(c[0] == "deploy" for c in rec.calls)  # noqa: E731
    return SimpleNamespace(client=SimpleNamespace(creds=SimpleNamespace(ip="1.2.3.4")), pending=lambda fabric, serial: ["l1", "l2"] if deployed() else [])


def args(**kw):
    base = dict(topology=TOPO_PATH, nd_ip="1.2.3.4", yes=False, extras=None, no_deploy=False)
    base.update(kw)
    return SimpleNamespace(**base)


def answers(*given):
    it = iter(given)
    prompts: list[str] = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return next(it)

    ask.prompts = prompts  # type: ignore[attr-defined]
    return ask


def restore(monkeypatch, drifts, a, ask, rec):
    monkeypatch.setattr(golden, "compute", lambda topo, live: drifts if not rec.calls or rec.calls[0][0] != "apply" else [])
    lines: list[str] = []
    code = golden.run_restore(a, load(TOPO_PATH), rec.live, prov_stub(rec), ask, lines.append)
    return code, lines


def test_drift_exits_1_with_report_and_0_when_clean(monkeypatch):
    topo = load(TOPO_PATH)
    live = read_live_from_snapshot(SNAP, topo)
    lines: list[str] = []
    monkeypatch.setattr(golden, "compute", lambda t, lv: [drift("missing", "s", fix=op("put_link"))])
    assert golden.run_drift(topo, live, lines.append)
    assert "MISSING" in lines[0]
    monkeypatch.setattr(golden, "compute", lambda t, lv: [])
    lines.clear()
    assert golden.run_drift(topo, live, lines.append) == [] and lines == []
    # main() end to end with a snapshot: exit code follows the drift list
    monkeypatch.setattr(golden, "compute", lambda t, lv: [drift("missing", "s")])
    assert golden.main(["drift", "--topology", str(TOPO_PATH), "--snapshot", str(SNAP)], out=lambda m: None) == 1
    monkeypatch.setattr(golden, "compute", lambda t, lv: [])
    assert golden.main(["drift", "--topology", str(TOPO_PATH), "--snapshot", str(SNAP)], out=lambda m: None) == 0


def test_restore_no_drift(monkeypatch, rec):
    code, lines = restore(monkeypatch, [], args(), answers(), rec)
    assert code == 0 and lines == ["restore: no drift"] and rec.calls == []


def test_restore_without_yes_asks_and_applies_nothing_on_no(monkeypatch, rec):
    ask = answers("n")
    code, lines = restore(monkeypatch, [drift("missing", "s", fix=op("put_link"))], args(), ask, rec)
    assert code == 2 and lines[-1] == "restore: cancelled"
    assert ask.prompts == ["Apply 1 create/overwrite operation(s) and 0 delete operation(s) to 1.2.3.4? [y/N] "]
    assert rec.calls == []


def test_restore_prompts_per_extra_and_honours_answers(monkeypatch, rec):
    d_adopt = drift("extra", "e1", delete=op("clear_link", path="/d1"), adopt=ADOPT)
    d_del = drift("extra", "e2", delete=[op("detach", path="/d2a"), op("delete_vrf", path="/d2b")], adopt=ADOPT)
    d_skip = drift("extra", "e3", delete=op("clear_link", path="/d3"), adopt=ADOPT)
    fix = op("put_link", path="/fix")
    ask = answers("a", "d", "s", "y")
    code, lines = restore(monkeypatch, [drift("different", "m", fix=fix), drift("different", "m2", fix=fix), d_adopt, d_del, d_skip], args(), ask, rec)
    assert code == 0
    assert ask.prompts[0].endswith("[a]dopt / [d]elete / [s]kip / [A]ll adopt / [D]ll delete: ")
    assert ask.prompts[3] == "Apply 1 create/overwrite operation(s) and 2 delete operation(s) to 1.2.3.4? [y/N] "
    assert rec.calls[0] == ("write", [ADOPT])
    assert [o.path for o in rec.calls[1][1]] == ["/fix", "/d2a", "/d2b"]
    assert rec.calls[2] == ("deploy", ["SITE1"])
    assert lines[-1] == ("restore: 1 applied, 1 adopted, 2 deleted; deployed SITE1. Now run the restore-lab-topologies Step 4.6 fabric checks and container pings.")
    assert "SITE1: 2 pending config line(s) remain" in lines


def test_choose_extras_all_variants_and_reasks():
    ds = [drift("extra", f"e{i}", delete=op("clear_link", path=f"/{i}"), adopt=Adoption(("fabrics", "SITE1", "links"), {"i": i})) for i in range(3)]
    adopts, dels = golden.choose_extras(ds, None, answers("A"))
    assert len(adopts) == 3 and dels == []
    adopts, dels = golden.choose_extras(ds, None, answers("s", "D"))
    assert adopts == [] and [o.path for o in dels] == ["/1", "/2"]
    ask = answers("x", "y", "z")  # three bad answers -> skip, then the next extra is asked afresh
    adopts, dels = golden.choose_extras(ds[:1], None, ask)
    assert adopts == [] and dels == [] and len(ask.prompts) == 3
    assert golden.choose_extras(ds, "delete", answers())[0] == []


def test_choose_extras_restricts_options_when_unavailable():
    no_adopt = drift("extra", "n1", delete=op("clear_link", path="/n1"), adopt=None)
    no_del = drift("extra", "n2", delete=None, adopt=ADOPT)
    lines: list[str] = []
    adopts, dels = golden.choose_extras([no_adopt, no_del], None, answers("a", "d", "d", "a"), lines.append)
    assert adopts == [ADOPT] and [o.path for o in dels] == ["/n1"]
    assert any("cannot be adopted" in line for line in lines) and any("cannot be deleted" in line for line in lines)


def test_yes_without_extras_flag_refuses_when_extras_exist(monkeypatch, rec):
    ds = [drift("missing", "m", fix=op("put_link")), drift("extra", "e", delete=op("clear_link"), adopt=ADOPT)]
    code, lines = restore(monkeypatch, ds, args(yes=True), answers(), rec)
    assert code == 2 and rec.calls == []
    assert lines[-1] == "restore: 1 extra object(s) need a decision; pass --extras adopt|delete|skip"


def test_extras_delete_flag_takes_every_delete_op(monkeypatch, rec):
    ds = [
        drift("extra", "e1", delete=op("clear_link", path="/1"), adopt=ADOPT),
        drift("extra", "e2", delete=[op("detach", path="/2a"), op("delete_vrf", path="/2b")], adopt=None),
    ]
    code, lines = restore(monkeypatch, ds, args(yes=True, extras="delete"), answers(), rec)
    assert code == 0
    assert [c[0] for c in rec.calls] == ["apply", "deploy"]
    assert [o.path for o in rec.calls[0][1]] == ["/1", "/2a", "/2b"]
    assert "0 applied, 0 adopted, 3 deleted; deployed SITE1." in lines[-1]


def test_adoptions_are_written_before_any_push(monkeypatch, rec):
    ds = [drift("missing", "m", fix=op("put_link")), drift("extra", "e", delete=None, adopt=ADOPT)]
    code, _ = restore(monkeypatch, ds, args(yes=True, extras="adopt"), answers(), rec)
    assert code == 0
    assert [c[0] for c in rec.calls] == ["write", "apply", "deploy"]


def test_adoptions_stay_written_when_apply_fails(monkeypatch, rec):
    rec.apply_error = ApplyError("boom")
    ds = [drift("missing", "m", fix=op("put_link")), drift("extra", "e", adopt=ADOPT)]
    code, lines = restore(monkeypatch, ds, args(yes=True, extras="adopt"), answers(), rec)
    assert code == 4 and [c[0] for c in rec.calls] == ["write", "apply"] and "boom" in " ".join(lines)


def test_no_deploy_skips_config_deploy(monkeypatch, rec):
    code, lines = restore(monkeypatch, [drift("missing", "m", fix=op("put_link"))], args(yes=True, no_deploy=True), answers(), rec)
    assert code == 0 and [c[0] for c in rec.calls] == ["apply"]
    assert "deployed nothing." in lines[-1]


def test_live_read_error_exits_3(monkeypatch):
    def boom(snapshot, topo):
        raise LiveReadError("no fabric")

    monkeypatch.setattr(golden, "read_live_from_snapshot", boom)
    lines: list[str] = []
    assert golden.main(["drift", "--topology", str(TOPO_PATH), "--snapshot", "x", "--nd-ip", "9.9.9.9"], out=lines.append) == 3
    assert lines == ["golden: cannot read x: no fabric"]


def test_adopt_prints_conflicts_filters_classes_and_exits_1(monkeypatch):
    other = Adoption(("fabrics", "SITE1", "interfaces"), {"switch": "S"})
    written: list = []
    monkeypatch.setattr(golden, "compute", lambda t, lv: [])
    monkeypatch.setattr(golden, "bootstrap_conflicts", lambda t, lv: ["clash"])
    monkeypatch.setattr(golden, "bootstrap_adoptions", lambda t, lv, d: [ADOPT, other])
    monkeypatch.setattr(golden, "write_adoptions", lambda path, ad: written.extend(ad) or len(ad))
    lines: list[str] = []
    code = golden.main(["adopt", "--topology", str(TOPO_PATH), "--snapshot", str(SNAP), "--classes", "links"], out=lines.append)
    assert code == 1 and written == [ADOPT]
    assert lines[0] == "CONFLICT: clash" and lines[-1] == f"adopt: 1 entries written to {TOPO_PATH}"
    monkeypatch.setattr(golden, "bootstrap_conflicts", lambda t, lv: [])
    assert golden.main(["adopt", "--topology", str(TOPO_PATH), "--snapshot", str(SNAP)], out=lambda m: None) == 0


def test_restore_deploys_fabrics_with_pending_config_from_an_earlier_run(monkeypatch, rec):
    prov = prov_stub()
    prov.pending = lambda fabric, serial: ["l1"] if fabric == "SITE1" else []
    topo = load(TOPO_PATH)
    rec.live.update({f.name: LiveFabric(f.name, "fabric", switches={s.hostname: {"serialNumber": "S-" + s.hostname} for s in f.switches}) for f in topo.fabrics})
    monkeypatch.setattr(golden, "compute", lambda t, lv: [drift("extra", "e", adopt=ADOPT)] if not rec.calls else [])
    lines: list[str] = []
    code = golden.run_restore(args(yes=True, extras="skip"), topo, rec.live, prov, answers(), lines.append)
    assert code == 0 and rec.calls == [("deploy", ["SITE1"])]
    assert any(line.startswith("restore: deploying 1 fabric(s) with pending config from an earlier run: SITE1") for line in lines)


def test_restore_transport_error_during_apply_exits_4(monkeypatch, rec):
    rec.apply_error = requests.ConnectionError("connection reset by peer")
    code, lines = restore(monkeypatch, [drift("missing", "m", fix=op("put_link"))], args(yes=True), answers(), rec)
    assert code == 4 and lines[-1] == "restore: apply failed: connection reset by peer"


def test_restore_deploy_runtime_error_exits_4_with_the_message(monkeypatch, rec):
    rec.deploy_error = RuntimeError("POST /fabrics/SITE1/actions/configSave -> HTTP 500: boom")
    code, lines = restore(monkeypatch, [drift("missing", "m", fix=op("put_link"))], args(yes=True), answers(), rec)
    assert code == 4 and [c[0] for c in rec.calls] == ["apply", "deploy"]
    assert lines[-1] == "restore: apply failed: POST /fabrics/SITE1/actions/configSave -> HTTP 500: boom"


def test_restore_pre_apply_pending_read_error_exits_3_before_any_write(monkeypatch, rec):
    prov = prov_stub(rec)

    def pending(fabric, serial):
        raise requests.ConnectionError("unreachable")

    prov.pending = pending
    monkeypatch.setattr(golden, "compute", lambda t, lv: [drift("missing", "m", fix=op("put_link"))])
    lines: list[str] = []
    code = golden.run_restore(args(yes=True), load(TOPO_PATH), rec.live, prov, answers(), lines.append)
    assert code == 3 and rec.calls == [] and lines[-1] == "golden: cannot read 1.2.3.4: unreachable"


@pytest.mark.parametrize("where", ["login", "get"])
def test_drift_against_an_unreachable_controller_exits_3(monkeypatch, where):
    class Client:
        def __init__(self, creds):
            self.creds = creds

        def login(self):
            if where == "login":
                raise requests.ConnectionError("login: no route to host")

        def get(self, path, params=None):
            raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(golden, "NDCredentials", SimpleNamespace(from_env=lambda ip: SimpleNamespace(ip=ip)))
    monkeypatch.setattr(golden, "NDClient", Client)
    lines: list[str] = []
    assert golden.main(["drift", "--topology", str(TOPO_PATH), "--nd-ip", "9.9.9.9"], out=lines.append) == 3
    assert lines[0].startswith("golden: cannot read 9.9.9.9: ") and "no route to host" in lines[0]
