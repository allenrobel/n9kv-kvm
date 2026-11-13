"""golden.py convert: move a testbed's mode fabrics between multicast and ingress replication.

ND refuses the mode change while a fabric holds any overlay definition (VRFs, networks, `ebgpVrfLite` links, fabric-group membership), so
the conversion tears those down, changes the mode, and then rebuilds with the normal restore against the target mode's golden:

    1. remove overlay   detach, deploy and delete every VRF and network of the group and of the mode fabrics (networks first), golden or not
    2. leave group      removeMembers for each mode fabric, then Recalculate and Deploy the fabrics that left
    3. delete links     DELETE every live `ebgpVrfLite` link of the mode fabrics
    4. change mode      PUT the target settings, then Recalculate and Deploy, per fabric not yet in the target mode; verified by a re-read
    5. rebuild          golden.py restore against the target golden (members, links, deploy, then overlay), then a zero-drift check

Every step is decided from the live state: a run that stopped part way is continued by running the same command again. Steps 1 to 4 run
only while some mode fabric's setting is not the target or a switch still holds a policy of the other mode; a fabric whose setting was
saved but never deployed therefore converts again and the rebuild does not start until it is converted. Pending config lines alone do not
count: the rebuild's deploy clears them, and the final check requires zero drift and nothing pending.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from typing import Any

from golden import READ_ERRORS, Ask, Out, _nd_ip, _pending_fabrics, run_restore
from golden_apply import RANK, ApplyError, Applier
from golden_drift import BUILT_IN_VRFS, Op, _extra_overlay_drift, _live_key, _policy, compute, format_report
from golden_live import LiveFabric, LiveReadError, read_live
from provision import LOG_BODY_LIMIT, Provisioner, redact
from replication import fabric_state, settings_body
from topology import REPLICATION_MODES, Topology, endpoint_key

VRF_LITE = "ebgpVrfLite"


@dataclass
class ConvertPlan:
    target: str
    states: dict[str, str] = field(default_factory=dict)  # mode fabric -> fabric_state
    overlay_ops: list[Op] = field(default_factory=list)  # in execution order
    leave: list[tuple[str, str]] = field(default_factory=list)  # (group, member)
    link_ids: list[tuple[str, str, str]] = field(default_factory=list)  # (fabric, linkId, description)
    convert: list[str] = field(default_factory=list)  # mode fabrics not yet in the target mode
    intact_source: bool = False


def _groups(topo: Topology, live: dict[str, LiveFabric]) -> list[str]:
    """The fabric groups a mode fabric belongs to in the golden file."""
    return [g.name for g in topo.fabric_groups if g.name in live and set(g.members) & set(topo.mode_fabrics)]


def _overlay_ops(topo: Topology, live: dict[str, LiveFabric]) -> list[Op]:
    """Detach, deploy and delete for every VRF and network of the groups and the mode fabrics; a group object's propagated copy in a fabric
    that is still a member goes with the group object. Sorted by the Applier's rank, so networks are deleted before the VRFs."""
    ops: list[Op] = []
    groups = _groups(topo, live)
    for kind, key, attr in (("network", "networkName", "networks"), ("vrf", "vrfName", "vrfs")):
        builtin = BUILT_IN_VRFS if kind == "vrf" else set()
        for group in groups:
            scope = [m for m in live[group].members if m in live]
            for obj in getattr(live[group], attr):
                if obj[key] not in builtin:
                    ops.extend(_delete_sequence(kind, group, live, obj, scope))
        for fabric in topo.mode_fabrics:
            shared = {o[key] for g in groups if fabric in live[g].members for o in getattr(live[g], attr)}
            for obj in getattr(live[fabric], attr):
                if obj[key] not in shared and obj[key] not in builtin:
                    ops.extend(_delete_sequence(kind, fabric, live, obj, [fabric]))
    return sorted(ops, key=lambda o: RANK[o.action])


def _delete_sequence(kind: str, fabric: str, live: dict[str, LiveFabric], obj: dict, scope: list[str]) -> list[Op]:
    delete = _extra_overlay_drift(kind, fabric, live, obj, scope).delete
    return delete if isinstance(delete, list) else [delete] if delete else []


def _vrf_lite_links(topo: Topology, live: dict[str, LiveFabric]) -> list[tuple[str, dict]]:
    """(fabric, link) for every live ebgpVrfLite link of the mode fabrics, each link once."""
    found: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for fabric in topo.mode_fabrics:
        for link in live[fabric].links:
            if _policy(link) == VRF_LITE and link["linkId"] not in seen:
                seen.add(link["linkId"])
                found.append((fabric, link))
    return found


def _ignoring_pending(fab: LiveFabric) -> str:
    """fabric_state without the pending-config rule: what the setting and the held policies say."""
    return fabric_state(replace(fab, pending=None))


def plan(topo_target: Topology, live: dict[str, LiveFabric]) -> ConvertPlan:
    """What a conversion of `live` to `topo_target.replication_mode` still has to do. A fabric needs converting while its setting is not the
    target or a switch still holds an other-mode policy; pending config alone does not count (the rebuild deploys it). Teardown (overlay,
    members, links) is planned only while some fabric needs converting. `intact_source` also ignores pending config, which the run refuses
    it for. `states` keeps the plain `fabric_state` for display."""
    target = str(topo_target.replication_mode)
    source = next(m for m in REPLICATION_MODES if m != target)
    fabrics = list(topo_target.mode_fabrics)
    states = {f: fabric_state(live[f]) for f in fabrics}
    convert = [f for f in fabrics if _ignoring_pending(live[f]) != target]  # pending lines alone are cleared by the rebuild's deploy
    leave = [(g, f) for g in _groups(topo_target, live) for f in fabrics if f in live[g].members]
    golden_keys = {endpoint_key(link.src, link.src_if, link.dst, link.dst_if) for link in topo_target.isn.links}
    links = _vrf_lite_links(topo_target, live)
    live_keys = {_live_key(link) for _, link in links}
    intact = all(_ignoring_pending(live[f]) == source for f in fabrics) and {f for _, f in leave} == set(fabrics) and golden_keys <= live_keys
    result = ConvertPlan(target=target, states=states, convert=convert, intact_source=intact)
    if convert:
        result.overlay_ops = _overlay_ops(topo_target, live)
        result.leave = leave
        result.link_ids = [(f, link["linkId"], _link_text(link, golden_keys)) for f, link in links]
    return result


def _link_text(link: dict, golden_keys: set) -> str:
    text = f"{link['srcSwitchName']} {link['srcInterfaceName']} <-> {link['dstSwitchName']} {link['dstInterfaceName']}"
    return text if _live_key(link) in golden_keys else f"{text} (not in golden)"


def describe(p: ConvertPlan) -> str:
    """The plan as shown before the prompt and by --dry-run: classification, then every object each step will act on."""
    lines = [f"convert: target replication mode {p.target}; live " + " ".join(f"{f}={s}" for f, s in p.states.items())]
    if not p.convert:
        lines.append(f"convert: every mode fabric is in {p.target} mode; nothing to convert")
    else:
        if p.intact_source:
            lines.append("convert: the testbed is intact in the source mode")
        else:
            lines.append("convert: resuming a partly converted testbed")
        removed = [o for o in p.overlay_ops if o.action.startswith("delete_")]
        detaches = sum(1 for o in p.overlay_ops if o.action == "detach")
        lines.append(f"1. remove overlay: {len(removed)} object(s), {detaches} detach(es) first")
        lines.extend(f"     {o.action.removeprefix('delete_')} {o.path.rsplit('/', 1)[1]} in {o.fabric}" for o in removed)
        lines.append(f"2. leave fabric group: {len(p.leave)} member(s)")
        lines.extend(f"     {member} from {group}, then Recalculate and Deploy {member}" for group, member in p.leave)
        lines.append(f"3. delete VRF-Lite links: {len(p.link_ids)}")
        lines.extend(f"     {fabric} {link_id} {text}" for fabric, link_id, text in p.link_ids)
        lines.append(f"4. change mode to {p.target}, then Recalculate and Deploy: {', '.join(p.convert)}")
    lines.append(f"5. rebuild: golden.py restore against the {p.target} golden, then a zero-drift check")
    return "\n".join(lines)


def _call(method: str, path: str, body: Any = None) -> str:
    return f"{method} {path}" if body is None else f"{method} {path} {json.dumps(redact(body))[:LOG_BODY_LIMIT]}"


def _deploy_calls(fabric: str) -> list[str]:
    return [_call("POST", f"/fabrics/{fabric}/actions/configSave"), _call("POST", f"/fabrics/{fabric}/actions/deploy")]


def _remove_member(group: str, member: str) -> Op:
    return Op("remove_member", group, "POST", f"/fabrics/{group}/actions/removeMembers", {"members": [{"name": member}]})


def _mode_put(topo: Topology, current: dict, fabric: str) -> Op:
    """The target settings PUT for `fabric`, merged over `current` (its live GET body)."""
    golden = next(f for f in topo.fabrics if f.name == fabric)
    return Op("put_settings", fabric, "PUT", f"/fabrics/{fabric}", settings_body(current, golden.settings))


def _first_step(p: ConvertPlan, topo: Topology, live: dict[str, LiveFabric]) -> tuple[str, list[str]]:
    """The first step with work and its exact calls (dry run); for the rebuild, the drift its restore starts from. The teardown fields are
    empty when nothing needs converting."""
    if p.overlay_ops:
        return "remove overlay", [_call(o.method, o.path, o.body) for o in p.overlay_ops]
    if p.leave:
        removes = [_call(o.method, o.path, o.body) for o in (_remove_member(g, m) for g, m in p.leave)]
        return "leave fabric group", removes + [c for _, m in p.leave for c in _deploy_calls(m)]
    if p.link_ids:
        return "delete VRF-Lite links", [_call("DELETE", f"/links/{link_id}") for _, link_id, _ in p.link_ids]
    if p.convert:
        calls = []
        for fabric in p.convert:
            put = _mode_put(topo, live[fabric].settings, fabric)  # the run re-reads the fabric first; a dry run shows today's values
            calls += [_call(put.method, put.path, put.body), *_deploy_calls(fabric)]
        return "change mode", calls
    drifts = compute(topo, live)
    return "rebuild (golden.py restore)", format_report(drifts).splitlines() if drifts else ["no drift: the restore has nothing to do"]


def _only_pending(fab: LiveFabric, target: str) -> bool:
    """In the target setting with no old-mode policy, held back only by pending config."""
    return fabric_state(fab) != target and _ignoring_pending(fab) == target


def _convert(p: ConvertPlan, topo: Topology, prov: Provisioner, out: Out, steps: list[str]) -> None:
    """Steps 1 to 4. Each step with work is appended to `steps` before it starts, so a failure can name it. The mode PUT is built from a
    fresh GET of the fabric: leaving the group can change settings ND inherits or generates, and the preflight read would write them back."""
    applier = Applier(prov, topo)

    def send(op: Op) -> None:
        applier._run(op, lambda: applier._send(op))

    def start(step: str) -> None:
        steps.append(step)
        out(f"convert: {step}")

    if p.overlay_ops:
        start("remove overlay")
        applier.apply(p.overlay_ops)
    if p.leave:
        start("leave fabric group")
        for group, member in p.leave:
            send(_remove_member(group, member))
        for member in dict.fromkeys(m for _, m in p.leave):
            prov.config_deploy(member)
    if p.link_ids:
        start("delete VRF-Lite links")
        for fabric, link_id, _ in p.link_ids:
            send(Op("delete_link", fabric, "DELETE", f"/links/{link_id}", None))
    start(f"change mode to {p.target}")
    for fabric in p.convert:
        try:
            current = prov.client.get(f"/fabrics/{fabric}") or {}
        except READ_ERRORS as exc:
            raise LiveReadError(f"GET /fabrics/{fabric}: {exc}") from exc
        send(_mode_put(topo, current, fabric))
        prov.config_deploy(fabric)


def run(args: argparse.Namespace, topo_target: Topology, prov: Provisioner, ask: Ask, out: Out) -> int:
    """Exit 0 converted with zero drift and nothing pending, 2 refused or cancelled, 3 a live read failed, 4 a step failed or drift remains."""
    nd_ip = _nd_ip(args, prov)
    target = str(topo_target.replication_mode)
    try:
        live = read_live(prov.client, topo_target)
    except LiveReadError as exc:
        out(f"convert: cannot read {nd_ip} (preflight): {exc}")
        return 3
    p = plan(topo_target, live)
    pending = [f for f in topo_target.mode_fabrics if any((live[f].pending or {}).values())]
    if p.intact_source and pending:
        out(
            f"convert: refused: pending config in {', '.join(pending)} on a testbed intact in its source mode; "
            "deploy it first (golden.py restore) so the conversion starts from a deployed state"
        )
        return 2
    out(describe(p))
    if args.dry_run:
        name, calls = _first_step(p, topo_target, live)
        out(f"dry run: first step with work: {name}")
        out("\n".join(f"  {c}" for c in calls))
        return 0
    if args.yes and args.extras is None:
        out("convert: --yes needs --extras adopt|delete|skip for the rebuild's restore; nothing was sent")
        return 2
    if not args.yes:
        answer = ask(f"Run this conversion on {nd_ip}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            out("convert: cancelled")
            return 2
    steps: list[str] = []
    try:
        if p.convert:
            _convert(p, topo_target, prov, out, steps)
            steps.append("verify mode")
            after = read_live(prov.client, topo_target)
            again = [f for f in p.convert if _only_pending(after[f], target)]
            for fabric in again:
                out(f"convert: {fabric} still has pending config; Recalculate and Deploy once more")
                prov.config_deploy(fabric)
            if again:
                after = read_live(prov.client, topo_target)
            stuck = [f"{f}={_ignoring_pending(after[f])}" for f in p.convert if _ignoring_pending(after[f]) != target]
            if stuck:
                out(f"convert: not in {target} mode after the deploy: {', '.join(stuck)}; rerun golden.py convert --replication-mode {target}")
                return 4
        steps.append("rebuild")
        out("convert: rebuild")
        rebuild_live = read_live(prov.client, topo_target)
    except LiveReadError as exc:
        out(f"convert: cannot read {nd_ip} ({steps[-1]}): {exc}")
        return 3
    except (ApplyError, *READ_ERRORS) as exc:  # a failed op, or RuntimeError/RequestException from configSave/deploy
        out(f"convert: {steps[-1]} failed: {exc}")
        return 4
    code = run_restore(argparse.Namespace(**{**vars(args), "no_deploy": False}), topo_target, rebuild_live, prov, ask, out)
    if code != 0:
        return code
    try:
        final = read_live(prov.client, topo_target)
        pending_after = sorted(_pending_fabrics(prov, topo_target, final))
    except READ_ERRORS as exc:
        out(f"convert: cannot read {nd_ip} (verify): {exc}")
        return 3
    drift = compute(topo_target, final)
    if drift or pending_after:
        out(f"convert: {len(drift)} drift item(s) remain; pending config in {', '.join(pending_after) or 'no fabric'}; run golden.py restore")
        return 4
    out(f"convert: done; {', '.join(topo_target.mode_fabrics)} are in {target} mode with zero drift and nothing pending")
    return 0
