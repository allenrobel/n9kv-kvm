"""Write golden adoptions (live ND objects the user chose to make golden) into a topology yaml, comments preserved, and build the bootstrap set.

The yaml is edited with ruamel's round-trip loader, but the file is not simply replaced by ruamel's dump: ruamel cannot reproduce the
hand-wrapped flow entries of the shipped files. Instead the dump of the untouched document is diffed against the dump of the edited
one, and only those differences are applied to the original text, so every line the adoption does not touch stays byte-identical.
"""

from __future__ import annotations

import io
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML  # type: ignore[import-untyped]
from ruamel.yaml.comments import CommentedMap, CommentedSeq  # type: ignore[import-untyped]

from golden_drift import COMPARED_INPUTS, Adoption, Drift, _if_policy, _live_key, _norm, _policy
from golden_live import LiveFabric, free_ports
from topology import GENERATED_LINK_POLICIES, Topology, endpoint_key

FABRIC_KEYS = ("links", "generated_links", "interfaces", "switches", "defaults")
OVERLAY_KEYS = ("vrfs", "networks", "vrf_attachments", "network_attachments")
TOP_LISTS = ("vpc_pairs", "tor_pairs")


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096  # new entries stay on one line
    return yaml


def _dump(yaml: YAML, doc: Any) -> str:
    buf = io.StringIO()
    yaml.dump(doc, buf)
    return buf.getvalue()


# ---------------------------------------------------------------- dedupe keys


def _entry_key(section: tuple[str, ...], entry: dict) -> Any:
    kind = section[-1]
    if kind in ("links", "generated_links"):
        return endpoint_key(entry["src"], entry["src_if"], entry["dst"], entry["dst_if"])
    if kind == "interfaces":
        return (entry["switch"], entry["interface"])
    if kind == "switches":
        return entry["hostname"]
    if kind == "vrfs":
        return entry["object"]["vrfName"]
    if kind == "networks":
        return entry["object"]["networkName"]
    if kind == "vrf_attachments":
        return (entry["fabric"], entry["vrf"], entry["switch"])
    if kind == "network_attachments":
        return (entry["fabric"], entry["network"], entry["switch"])
    if kind == "vpc_pairs":
        return (entry["fabric"], frozenset((entry["switch"], entry["peer"])))
    return (entry["fabric"], entry["tor"])  # tor_pairs


# ---------------------------------------------------------------- yaml editing


def _flow(value: Any) -> Any:
    """Plain data as flow-style ruamel nodes, so a new entry reads like `- {hostname: S1_BG1, ip: 1.2.3.4, role: leaf}`."""
    if isinstance(value, dict):
        node = CommentedMap((k, _flow(v)) for k, v in value.items())
        node.fa.set_flow_style()
        return node
    if isinstance(value, (list, tuple)):
        seq = CommentedSeq(_flow(v) for v in value)
        seq.fa.set_flow_style()
        return seq
    return value


def _container(doc: CommentedMap, section: tuple[str, ...]) -> tuple[CommentedMap, str]:
    """The mapping that holds the section's key, and that key; absent parents are created."""
    if len(section) == 3 and section[0] == "fabrics" and section[2] in FABRIC_KEYS:
        fabric = next((f for f in doc.get("fabrics") or [] if f.get("name") == section[1]), None)
        if fabric is None:
            raise ValueError(f"adoption section {section}: no fabric named {section[1]} in the topology file")
        return fabric, section[2]
    if len(section) == 2 and section[0] == "overlay" and section[1] in OVERLAY_KEYS:
        if doc.get("overlay") is None:
            doc["overlay"] = CommentedMap()
        return doc["overlay"], section[1]
    if len(section) == 1 and section[0] in TOP_LISTS:
        return doc, section[0]
    raise ValueError(f"unknown adoption section {section}")


def _apply(doc: CommentedMap, adoptions: list[Adoption]) -> int:
    written = 0
    for adoption in adoptions:
        parent, key = _container(doc, adoption.section)
        if key == "defaults":
            if parent.get("defaults") is None:
                parent["defaults"] = CommentedMap()
            for role, default in adoption.entry.items():
                if role not in parent["defaults"]:
                    parent["defaults"][role] = _flow(default)
                    written += 1
            continue
        if parent.get(key) is None:
            parent[key] = CommentedSeq()
        existing = {_entry_key(adoption.section, item) for item in parent[key]}
        if _entry_key(adoption.section, adoption.entry) in existing:
            continue
        parent[key].append(_flow(adoption.entry))
        written += 1
    return written


def _graft(original: str, base_dump: str, new_dump: str) -> str:
    """Apply the line differences base_dump -> new_dump onto `original`, which differs from base_dump only in line wrapping."""
    orig, base, new = original.splitlines(keepends=True), base_dump.splitlines(keepends=True), new_dump.splitlines(keepends=True)
    boundary: dict[int, int] = {}  # line boundary in base -> line boundary in orig
    for block in SequenceMatcher(None, base, orig, autojunk=False).get_matching_blocks():
        for offset in range(block.size + 1):
            boundary[block.a + offset] = block.b + offset

    def to_orig(index: int) -> int:
        # A boundary inside a re-wrapped region has no exact twin; snap to the end of that region.
        return boundary.get(index) if index in boundary else boundary[min(i for i in boundary if i > index)]  # type: ignore[return-value]

    out: list[str] = []
    cursor = 0
    for tag, a1, a2, b1, b2 in SequenceMatcher(None, base, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        start, end = to_orig(a1), to_orig(a2)
        out.extend(orig[cursor:start])
        out.extend(new[b1:b2])
        cursor = end
    out.extend(orig[cursor:])
    return "".join(out)


def write_adoptions(path: Path, adoptions: list[Adoption]) -> int:
    """Append each adoption to its section of the topology yaml and return how many entries were written (a `defaults` adoption counts one per
    role added). An entry already present (same dedupe key) is skipped; a file that gains nothing is not rewritten. Raises ValueError for an
    unknown section, before anything is written."""
    original = path.read_text(encoding="utf-8")
    yaml = _yaml()
    base_dump = _dump(yaml, yaml.load(original))
    doc = yaml.load(original)
    written = _apply(doc, adoptions)
    if written:
        path.write_text(_graft(original, base_dump, _dump(yaml, doc)), encoding="utf-8")
    return written


# ---------------------------------------------------------------- bootstrap


def _dedupe(adoptions: list[Adoption]) -> list[Adoption]:
    seen: set = set()
    result: list[Adoption] = []
    for adoption in adoptions:
        if adoption.section[-1] == "defaults":
            result.append(adoption)
            continue
        key = (adoption.section, _entry_key(adoption.section, adoption.entry))
        if key not in seen:
            seen.add(key)
            result.append(adoption)
    return result


def _generated_scan(topo: Topology, live: dict[str, LiveFabric]) -> tuple[list[Adoption], list[str]]:
    tool_links = {endpoint_key(link.src, link.src_if, link.dst, link.dst_if): link.policy for fabric in topo.fabrics for link in fabric.links}
    tool_links.update({endpoint_key(link.src, link.src_if, link.dst, link.dst_if): "ebgpVrfLite" for link in topo.isn.links})
    known = {endpoint_key(g.src, g.src_if, g.dst, g.dst_if) for fabric in topo.fabrics for g in fabric.generated_links}
    adoptions: list[Adoption] = []
    conflicts: list[str] = []
    seen: set = set()
    for fabric in topo.fabrics:
        if fabric.name not in live:
            continue
        group = next((g.name for g in topo.fabric_groups if fabric.name in g.members), fabric.name)
        for link in live[fabric.name].links:
            policy = _policy(link)
            key = _live_key(link)
            if policy not in GENERATED_LINK_POLICIES or key in seen:
                continue
            seen.add(key)
            src, src_if, dst, dst_if = link["srcSwitchName"], link["srcInterfaceName"], link["dstSwitchName"], link["dstInterfaceName"]
            if key in tool_links:
                conflicts.append(f"{fabric.name}: {src} {src_if} <-> {dst} {dst_if} is {policy} live but golden lists it as {tool_links[key]}")
            elif key not in known:
                owner = fabric.name if policy == "iosXeNumbered" else group
                entry = {"src": src, "src_if": src_if, "dst": dst, "dst_if": dst_if, "policy": policy, "owner": owner}
                adoptions.append(Adoption(("fabrics", fabric.name, "generated_links"), entry))
    return adoptions, conflicts


def _role_default(intf: dict) -> dict:
    policy = _if_policy(intf)
    default = {"policyType": policy.get("policyType") or ""}
    for key in COMPARED_INPUTS:
        if key in policy and _norm(policy[key]):
            default[key] = _norm(policy[key])
    return default


def _majority_default(ports: list[dict]) -> dict:
    """The most common signature among `ports`; a tie goes to the signature with the fewest keys (then first seen)."""
    signatures = [_role_default(p) for p in ports]
    keys = [tuple(sorted(sig.items())) for sig in signatures]
    counts = {k: keys.count(k) for k in dict.fromkeys(keys)}
    best = min(counts, key=lambda k: (-counts[k], len(k)))
    return dict(best)


def _defaults_adoptions(topo: Topology, live: dict[str, LiveFabric]) -> list[Adoption]:
    all_links = [link for fab in live.values() for link in fab.links]
    adoptions: list[Adoption] = []
    for fabric in topo.fabrics:
        if fabric.type == "externalConnectivity" or fabric.name not in live:
            continue
        entry: dict = {}
        for role in dict.fromkeys(s.role for s in fabric.switches):
            if role == "coreRouter" or role in fabric.defaults:
                continue
            ports = [p for s in fabric.switches if s.role == role for p in free_ports(live[fabric.name], s.hostname, all_links)]
            if ports:
                entry[role] = _majority_default(ports)
        if entry:
            adoptions.append(Adoption(("fabrics", fabric.name, "defaults"), entry))
    return adoptions


def bootstrap_adoptions(topo: Topology, live: dict[str, LiveFabric], drifts: list[Drift]) -> list[Adoption]:
    """Everything needed to make the live controller the baseline: each drift's adoption, then the generated links ND made itself, then a
    per-fabric `defaults` map taken from the majority signature of each role's free ports."""
    adopted = _dedupe([d.adopt for d in drifts if d.adopt])
    return [*adopted, *_generated_scan(topo, live)[0], *_defaults_adoptions(topo, live)]


def bootstrap_conflicts(topo: Topology, live: dict[str, LiveFabric]) -> list[str]:
    """Live generated-policy links whose endpoints golden already lists as a tool link; they are never written, so the user must resolve them."""
    return _generated_scan(topo, live)[1]
