#!/usr/bin/env python3
"""Golden drift/restore: compare a Nexus Dashboard with the topology yaml (the golden baseline), push it back, or adopt the live state.

    golden.py drift   --topology T.yaml [--nd-ip IP | --snapshot DIR]
    golden.py restore --topology T.yaml [--nd-ip IP] [--yes] [--extras adopt|delete|skip] [--no-deploy]
    golden.py adopt   --topology T.yaml [--nd-ip IP | --snapshot DIR] [--classes links,interfaces,...]

`drift` prints one line per difference (MISSING / DIFFERENT / EXTRA) and exits 1 when there is any. `restore` creates or overwrites what is
missing or different, asks per EXTRA object whether to adopt it into the yaml or delete it from ND, writes the adoptions, applies, and
deploys the touched fabrics. `adopt` writes the live state into the yaml (bootstrap of a golden file); live-only objects become entries.

A topology that declares `replication_modes` needs one chosen before it loads: `--replication-mode` or, when omitted, the mode detected from the
live ND (or the snapshot). A testbed caught between modes is refused (exit 2); `golden.py convert` finishes the conversion.

Exit codes: 0 ok / no drift, 1 drift (drift) or conflicts (adopt), 2 refused or cancelled, 3 live read failed (an HTTP error or an unreachable controller
while reading), 4 apply failed (a failed op, a dropped connection or an HTTP error while `restore` writes or deploys).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

import requests

from golden_adopt import bootstrap_adoptions, bootstrap_conflicts, write_adoptions
from golden_apply import ApplyError, Applier
from golden_drift import Adoption, Drift, Op, compute, format_report
from golden_live import LiveFabric, LiveReadError, read_live, read_live_from_snapshot
from nd_client import NDClient, NDCredentials
from provision import Provisioner
from replication import live_mode, testbed_state
from topology import REPLICATION_MODES, Topology, declared_mode_fabrics, load

Ask = Callable[[str], str]
Out = Callable[[str], None]

PROMPT = "[a]dopt / [d]elete / [s]kip / [A]ll adopt / [D]ll delete: "
MAX_TRIES = 3
# what a controller read or write can raise: RuntimeError for an HTTP error (NDClient), RequestException (an OSError) for a dropped connection
READ_ERRORS = (RuntimeError, requests.RequestException, OSError)


class Refused(Exception):
    """A request golden.py will not act on (exit 2)."""


def _ask_default(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def run_drift(topo: Topology, live: dict[str, LiveFabric], out: Out) -> list[Drift]:
    """Compute and print the drift report; return the drifts."""
    drifts = compute(topo, live)
    if drifts:
        out(format_report(drifts))
    return drifts


def _flatten(delete: Op | list[Op]) -> list[Op]:
    return list(delete) if isinstance(delete, list) else [delete]


def _fix_ops(drifts: list[Drift]) -> list[Op]:
    """The create/overwrite ops of missing/different drifts; settings drifts of one fabric share one Op, so dedupe by identity."""
    ops: list[Op] = []
    seen: set[int] = set()
    for d in drifts:
        if d.kind != "extra" and d.fix is not None and id(d.fix) not in seen:
            seen.add(id(d.fix))
            ops.extend(d.fix if isinstance(d.fix, list) else [d.fix])
    return ops


def choose_extras(drifts: list[Drift], mode: str | None, ask: Ask, out: Out = print) -> tuple[list[Adoption], list[Op]]:
    """Decide for every `extra` drift: adopt it into the golden yaml, delete it from ND, or skip. mode None asks per extra (A / D answer for all
    remaining); "adopt" / "delete" / "skip" applies without asking. Returns (adoptions, delete ops in order)."""
    adoptions: list[Adoption] = []
    deletes: list[Op] = []
    sticky: str | None = mode
    for d in (d for d in drifts if d.kind == "extra"):
        choice = sticky
        if choice is None:
            choice = _prompt_one(d, ask, out)
            if choice in ("adopt-all", "delete-all"):
                sticky = choice.split("-")[0]
                choice = sticky
        if choice == "adopt":
            if d.adopt is None:
                out(f"cannot adopt {d.subject}: no golden entry exists for this object; skipped")
            else:
                adoptions.append(d.adopt)
        elif choice == "delete":
            if d.delete is None:
                out(f"cannot delete {d.subject}: no delete operation exists for this object; skipped")
            else:
                deletes.extend(_flatten(d.delete))
    return adoptions, deletes


def _prompt_one(d: Drift, ask: Ask, out: Out) -> str:
    can_adopt, can_delete = d.adopt is not None, d.delete is not None
    options = {"a": "adopt", "d": "delete", "s": "skip", "A": "adopt-all", "D": "delete-all"}
    if not can_adopt:
        out(f"{d.subject}: cannot be adopted (no golden entry exists for it)")
        options = {k: v for k, v in options.items() if not v.startswith("adopt")}
    if not can_delete:
        out(f"{d.subject}: cannot be deleted (no delete operation exists for it)")
        options = {k: v for k, v in options.items() if not v.startswith("delete")}
    text = f"{format_report([d])}\n{PROMPT}"
    if not (can_adopt and can_delete):
        text = f"{format_report([d])}\n" + " / ".join(f"[{k}]{v}" for k, v in options.items()) + ": "
    for _ in range(MAX_TRIES):
        answer = ask(text).strip()
        if answer in options:
            return options[answer]
    return "skip"


def _nd_ip(args: argparse.Namespace, prov: Provisioner) -> str:
    return args.nd_ip or str(getattr(getattr(prov.client, "creds", None), "ip", "ND"))


def _pending_report(prov: Provisioner, topo: Topology, live: dict[str, LiveFabric], out: Out) -> None:
    for fabric in topo.fabrics:
        fab_live = live.get(fabric.name)
        if fab_live is None:
            continue
        total = 0
        for sw in fabric.switches:
            serial = fab_live.switches.get(sw.hostname, {}).get("serialNumber")
            if serial:
                try:
                    total += len(prov.pending(fabric.name, serial))
                except READ_ERRORS as exc:
                    out(f"{fabric.name} {sw.hostname}: pending config unreadable: {exc}")
        out(f"{fabric.name}: {total} pending config line(s) remain")


def _pending_fabrics(prov: Provisioner, topo: Topology, live: dict[str, LiveFabric]) -> set[str]:
    """Golden fabrics in which some golden switch has undeployed config (e.g. left by an earlier run that stopped part way)."""
    found: set[str] = set()
    for fabric in topo.fabrics:
        fab_live = live.get(fabric.name)
        for sw in fabric.switches:
            serial = ((fab_live.switches.get(sw.hostname) if fab_live else None) or {}).get("serialNumber")
            if serial and prov.pending(fabric.name, serial):
                found.add(fabric.name)
                break
    return found


def run_restore(args: argparse.Namespace, topo: Topology, live: dict[str, LiveFabric], prov: Provisioner, ask: Ask, out: Out) -> int:
    drifts = run_drift(topo, live, out)
    if not drifts:
        out("restore: no drift")
        return 0
    extras = [d for d in drifts if d.kind == "extra"]
    if args.yes and extras and args.extras is None:
        out(f"restore: {len(extras)} extra object(s) need a decision; pass --extras adopt|delete|skip")
        return 2
    ops = _fix_ops(drifts)
    adoptions, deletes = choose_extras(drifts, args.extras, ask, out)
    if adoptions:
        out(f"restore: {write_adoptions(Path(args.topology), adoptions)} adoption(s) written to {args.topology}")
    nd_ip = _nd_ip(args, prov)
    all_ops = [*ops, *deletes]
    if all_ops and not args.yes:
        answer = ask(f"Apply {len(ops)} create/overwrite operation(s) and {len(deletes)} delete operation(s) to {nd_ip}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            out("restore: cancelled")
            return 2
    applier = Applier(prov, topo)
    deployed: list[str] = []
    try:
        pending_fabrics = set() if args.no_deploy else _pending_fabrics(prov, topo, live)
    except READ_ERRORS as exc:
        out(f"golden: cannot read {nd_ip}: {exc}")
        return 3
    try:
        touched = applier.apply(all_ops) if all_ops else set()
        if not args.no_deploy and (touched or pending_fabrics):
            earlier = sorted(pending_fabrics - touched)
            if earlier:
                out(f"restore: deploying {len(earlier)} fabric(s) with pending config from an earlier run: {', '.join(earlier)}")
            applier.deploy(touched | pending_fabrics, topo)
            deployed = sorted(touched | pending_fabrics)
    except (ApplyError, *READ_ERRORS) as exc:  # a failed op, or RuntimeError/RequestException from configSave/deploy
        out(f"restore: apply failed: {exc}")
        return 4
    try:
        after = read_live(prov.client, topo)
    except LiveReadError as exc:
        out(f"golden: cannot read {nd_ip}: {exc}")
        return 3
    remaining = compute(topo, after)
    resets = sum(1 for o in deletes if o.action == "reset_interface")  # a "delete" of a free physical port is a PUT back to its role default
    out(f"restore: {len(remaining)} drift item(s) remain")
    _pending_report(prov, topo, after, out)
    out(
        f"restore: {len(ops)} applied, {len(adoptions)} adopted, {resets} reset, {len(deletes) - resets} deleted; deployed {', '.join(deployed) or 'nothing'}. "
        "Now run the restore-lab-topologies Step 4.6 fabric checks and container pings."
    )
    return 0


def run_adopt(args: argparse.Namespace, topo: Topology, live: dict[str, LiveFabric], out: Out) -> int:
    drifts = compute(topo, live)
    conflicts = bootstrap_conflicts(topo, live)
    for line in conflicts:
        out(f"CONFLICT: {line}")
    adoptions = bootstrap_adoptions(topo, live, drifts)
    if args.classes:
        wanted = {c.strip() for c in args.classes.split(",") if c.strip()}
        adoptions = [a for a in adoptions if a.section[-1] in wanted]
    for a in adoptions:
        out(f"adopt {'/'.join(a.section)}: {a.entry}")
    written = write_adoptions(Path(args.topology), adoptions)
    out(f"adopt: {written} entries written to {args.topology}")
    return 1 if conflicts else 0


def _detect(source: NDClient | Path, fabric: str) -> str | None:
    """The saved replication mode of one fabric, read from the controller or from the snapshot dump."""
    if isinstance(source, Path):
        path = source / f"fabric_{fabric}.json"
        if not path.exists():
            raise LiveReadError(f"snapshot {source} has no fabric_{fabric}.json content")
        return live_mode(json.loads(path.read_text(encoding="utf-8")) or {})
    try:
        return live_mode(source.get(f"/fabrics/{fabric}"))
    except READ_ERRORS as exc:
        raise LiveReadError(f"GET /fabrics/{fabric}: {exc}") from exc


def resolve_mode(args: argparse.Namespace, source: NDClient | Path, out: Out) -> str | None:
    """The replication mode to load the topology with: None for a file that declares none, else the flag or the mode detected from `source`.
    Raises Refused for a flag on a modeless file, a fabric whose mode is unreadable, or fabrics that disagree; LiveReadError when a read fails."""
    fabrics = declared_mode_fabrics(args.topology)
    flag = getattr(args, "replication_mode", None)
    if not fabrics:
        if flag is not None:
            raise Refused(f"{Path(args.topology).name} declares no replication_modes; drop --replication-mode")
        return None
    if flag is not None:
        return str(flag)
    found = {name: _detect(source, name) for name in fabrics}
    for name, mode in found.items():
        if mode not in REPLICATION_MODES:
            raise Refused(f"fabric {name} has replication mode {mode!r}, expected one of {', '.join(REPLICATION_MODES)}; pass --replication-mode")
    if len(set(found.values())) != 1:
        detail = ", ".join(f"{name}={mode}" for name, mode in found.items())
        raise Refused(f"fabrics disagree on the replication mode ({detail}); run golden.py convert --replication-mode <mode>")
    mode = found[fabrics[0]]
    assert mode is not None
    out(f"replication mode: {mode} (detected)")
    return mode


def _check_conversion(args: argparse.Namespace, topo: Topology, live: dict[str, LiveFabric], mode: str | None) -> None:
    """Refuse a testbed that is mid-conversion (live reads only), and a restore toward a mode other than the live setting."""
    if not topo.mode_fabrics or any(live[name].mode_policies is None for name in topo.mode_fabrics):
        return
    if testbed_state(topo, live) == "mid":
        raise Refused(f"testbed is mid-conversion; run golden.py convert --replication-mode {mode}")
    if args.cmd == "restore" and mode is not None and any(live_mode(live[name].settings) != mode for name in topo.mode_fabrics):
        raise Refused(f"the live testbed is not in {mode} mode; run golden.py convert --replication-mode {mode} first")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("drift", "restore", "adopt"):
        p = sub.add_parser(name)
        p.add_argument("--topology", type=Path, required=True)
        p.add_argument("--nd-ip", help="override ND_IP4")
        p.add_argument("--replication-mode", choices=REPLICATION_MODES, help="mode to load a topology that declares replication_modes (default: detected)")
        if name != "restore":
            p.add_argument("--snapshot", type=Path, help="read the live state from a snapshot dump instead of ND")
    restore = sub.choices["restore"]
    restore.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    restore.add_argument("--extras", choices=["adopt", "delete", "skip"], help="what to do with live-only objects without asking")
    restore.add_argument("--no-deploy", action="store_true", help="push the changes but do not run configDeploy")
    sub.choices["adopt"].add_argument("--classes", help="comma list of sections to adopt, e.g. links,interfaces,defaults")
    return parser


def main(argv: list[str] | None = None, ask: Ask = _ask_default, out: Out = print) -> int:
    args = _parser().parse_args(argv)
    where = args.nd_ip or "ND"
    client = None
    try:
        if getattr(args, "snapshot", None):
            where = str(args.snapshot)
            source: NDClient | Path = args.snapshot
        else:
            client = NDClient(NDCredentials.from_env(args.nd_ip))
            source = client
            client.login()
            where = args.nd_ip or client.creds.ip
        topo = load(args.topology, resolve_mode(args, source, out))
        live = read_live_from_snapshot(args.snapshot, topo) if client is None else read_live(client, topo)
        _check_conversion(args, topo, live, topo.replication_mode)
    except Refused as exc:
        out(f"golden: {exc}")
        return 2
    except (LiveReadError, requests.RequestException, OSError) as exc:  # login can fail on the connection before read_live wraps anything
        out(f"golden: cannot read {where}: {exc}")
        return 3
    if args.cmd == "drift":
        return 1 if run_drift(topo, live, out) else 0
    if args.cmd == "adopt":
        return run_adopt(args, topo, live, out)
    assert client is not None
    return run_restore(args, topo, live, Provisioner(client, topo), ask, out)


if __name__ == "__main__":
    # line-buffer stdout even when piped (`| tee log`): a restore prints one line per REST call over many minutes, and the default
    # 8 KB block buffer makes a running restore look hung for minutes at a time
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
