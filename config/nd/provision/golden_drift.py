#!/usr/bin/env python3
"""Golden drift: compare the live controller state (golden_live) with the golden topology and describe every difference.

Each drift class is one function returning `Drift` records. A `Drift` carries what is wrong (`kind`, `subject`, `golden`, `live`) and,
where a safe automatic action exists, the controller call that repairs it (`fix`), removes it (`delete`) or the topology entry that would
adopt it into the golden file (`adopt`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from golden_live import LiveFabric, free_ports, interface_path
from provision import link_payload
from topology import TOOL_LINK_POLICIES, Fabric, FabricLink, InterfaceIntent, Link, Topology, endpoint_key

Kind = Literal["missing", "different", "extra"]

BASE_FIELDS = (
    "srcFabricName",
    "srcSwitchId",
    "srcInterfaceName",
    "srcSwitchName",
    "dstFabricName",
    "dstSwitchId",
    "dstInterfaceName",
    "dstSwitchName",
)
LINKS = "links"
GENERATED = "genlinks"
INTERFACES = "interfaces"


@dataclass(frozen=True)
class Op:
    """One controller call. action is one of put_link, clear_link, put_interface, reset_interface, delete_interface, attach, detach, create_vrf,
    create_network, delete_vrf, delete_network, pair_vpc, unpair_vpc, pair_tor, unpair_tor, add_switch, set_role, put_settings, deploy_owner."""

    action: str
    fabric: str
    method: str
    path: str
    body: Any


@dataclass(frozen=True)
class Adoption:
    """A golden-file entry that would make an extra live object part of the baseline, e.g. ("fabrics", "SITE1", "links") plus the entry dict."""

    section: tuple[str, ...]
    entry: dict


@dataclass(frozen=True)
class Drift:
    cls: str
    fabric: str
    kind: Kind
    subject: str
    golden: str
    live: str
    fix: Op | None
    delete: Op | None
    adopt: Adoption | None


# ---------------------------------------------------------------- shared helpers


def _config(link_obj: dict) -> dict:
    """configData is null for discovered links with no policy."""
    value = link_obj.get("configData")
    return value if isinstance(value, dict) else {}


def _policy(link_obj: dict) -> str:
    return _config(link_obj).get("policyType") or ""


def _inputs(link_obj: dict) -> dict:
    value = _config(link_obj).get("templateInputs")
    return value if isinstance(value, dict) else {}


def _live_key(link_obj: dict) -> tuple:
    return endpoint_key(link_obj["srcSwitchName"], link_obj["srcInterfaceName"], link_obj["dstSwitchName"], link_obj["dstInterfaceName"])


def _index(objs: list[dict]) -> dict[tuple, dict]:
    return {_live_key(o): o for o in objs}


def _subject(a: str, a_if: str, b: str, b_if: str) -> str:
    return f"{a} {a_if} <-> {b} {b_if}"


def _short_pair(first: str, second: str) -> str:
    """10.14.0.5, 10.14.0.6 -> 10.14.0.5/.6 (same /24) else both in full."""
    head, _, _ = first.rpartition(".")
    if head and second.startswith(head + "."):
        return f"{first}/.{second.rpartition('.')[2]}"
    return f"{first}/{second}"


def _same_direction(link_obj: dict, src: str) -> bool:
    """True when the live object lists `src` as its source switch."""
    return link_obj["srcSwitchName"] == src


def _base(link_obj: dict) -> dict:
    return {name: link_obj[name] for name in BASE_FIELDS}


def _clear_op(fabric: str, link_obj: dict) -> Op:
    return Op("clear_link", fabric, "PUT", f"/links/{link_obj['linkId']}", {**_base(link_obj), "configData": None})


# ---------------------------------------------------------------- tool-owned fabric links


def numbered_link_body(link_obj: dict, golden: FabricLink) -> dict:
    """PUT body for an existing link: its 8 base fields plus a numbered configData. IPs follow the live object's orientation and each
    description names its own side; `golden.inputs` overrides any template input."""
    src_ip, dst_ip = (golden.src_ip, golden.dst_ip) if _same_direction(link_obj, golden.src) else (golden.dst_ip, golden.src_ip)
    inputs = {
        "srcIp": src_ip,
        "dstIp": dst_ip,
        "srcIpv6": "",
        "dstIpv6": "",
        "mtu": 9216,
        "speed": "auto",
        "fec": "auto",
        "interfaceAdminState": True,
        "srcInterfaceDescription": f"connected-to-{link_obj['srcSwitchName']}-{link_obj['srcInterfaceName']}",
        "dstInterfaceDescription": f"connected-to-{link_obj['dstSwitchName']}-{link_obj['dstInterfaceName']}",
        "srcInterfaceConfig": "",
        "dstInterfaceConfig": "",
        "bfdEchoOnSrcInterface": False,
        "bfdEchoOnDstInterface": False,
        "dhcpRelayOnSrcInterface": False,
        "dhcpRelayOnDstInterface": False,
    }
    inputs.update(golden.inputs)
    return {**_base(link_obj), "configData": {"policyType": "numbered", "templateInputs": inputs}}


def _tool_link_golden_text(golden: FabricLink) -> str:
    if golden.src_ip or golden.dst_ip:
        return f"{golden.policy} {_short_pair(golden.src_ip, golden.dst_ip)}"
    return golden.policy


def _tool_link_live_text(link_obj: dict, golden: FabricLink) -> str:
    """The live link in the golden entry's orientation."""
    policy = _policy(link_obj)
    if not policy:
        return "none"
    live_inputs = _inputs(link_obj)
    src_ip, dst_ip = str(live_inputs.get("srcIp", "")), str(live_inputs.get("dstIp", ""))
    if not _same_direction(link_obj, golden.src):
        src_ip, dst_ip = dst_ip, src_ip
    return f"{policy} {_short_pair(src_ip, dst_ip)}" if (src_ip or dst_ip) else policy


def _tool_link_differs(link_obj: dict, golden: FabricLink) -> bool:
    if _policy(link_obj) != golden.policy:
        return True
    live_inputs = _inputs(link_obj)
    wanted = dict(golden.inputs)
    forward = _same_direction(link_obj, golden.src)
    if golden.policy == "numbered":
        wanted["srcIp" if forward else "dstIp"] = golden.src_ip
        wanted["dstIp" if forward else "srcIp"] = golden.dst_ip
    return any(live_inputs.get(key) != value for key, value in wanted.items())


def _tool_link_drift(fabric: Fabric, golden: FabricLink, link_obj: dict | None) -> Drift | None:
    subject = _subject(golden.src, golden.src_if, golden.dst, golden.dst_if)
    text = _tool_link_golden_text(golden)
    if link_obj is None:
        return Drift(LINKS, fabric.name, "missing", subject, text, "none", None, None, None)
    if _policy(link_obj) and not _tool_link_differs(link_obj, golden):
        return None
    kind: Kind = "different" if _policy(link_obj) else "missing"
    fix = Op("put_link", fabric.name, "PUT", f"/links/{link_obj['linkId']}", numbered_link_body(link_obj, golden)) if golden.policy == "numbered" else None
    return Drift(LINKS, fabric.name, kind, subject, text, _tool_link_live_text(link_obj, golden), fix, None, None)


def _adoption_entry(link_obj: dict) -> dict:
    live_inputs = _inputs(link_obj)
    entry = {
        "src": link_obj["srcSwitchName"],
        "src_if": link_obj["srcInterfaceName"],
        "dst": link_obj["dstSwitchName"],
        "dst_if": link_obj["dstInterfaceName"],
        "policy": _policy(link_obj),
    }
    src_ip = live_inputs.get("srcIp") or live_inputs.get("srcIpAddressMask")
    dst_ip = live_inputs.get("dstIp") or live_inputs.get("dstIpAddress")
    if src_ip:
        entry["src_ip"] = src_ip
    if dst_ip:
        entry["dst_ip"] = dst_ip
    return entry


def _extra_link_drift(fabric: Fabric, link_obj: dict) -> Drift:
    subject = _subject(link_obj["srcSwitchName"], link_obj["srcInterfaceName"], link_obj["dstSwitchName"], link_obj["dstInterfaceName"])
    entry = _adoption_entry(link_obj)
    ips = _short_pair(entry.get("src_ip", ""), entry.get("dst_ip", "")) if "src_ip" in entry or "dst_ip" in entry else ""
    live_text = f"{entry['policy']} {ips}".strip()
    return Drift(LINKS, fabric.name, "extra", subject, "none", live_text, None, _clear_op(fabric.name, link_obj), Adoption(("fabrics", fabric.name, LINKS), entry))


# ---------------------------------------------------------------- ISN (ebgpVrfLite) links


def _isn_text(link: Link) -> str:
    return f"ebgpVrfLite {link.src_ip} {link.dst_ip}"


def _isn_oriented(link_obj: dict, link: Link) -> Link:
    """The golden ISN link listed the way the live object lists it: endpoints, ASNs and addresses swapped when the live source is golden's
    destination (the source address carries the mask, the destination one does not)."""
    if _same_direction(link_obj, link.src):
        return link
    address, _, mask = link.src_ip.partition("/")
    return replace(
        link,
        src_fabric=link.dst_fabric,
        src=link.dst,
        src_if=link.dst_if,
        dst_fabric=link.src_fabric,
        dst=link.src,
        dst_if=link.src_if,
        src_asn=link.dst_asn,
        dst_asn=link.src_asn,
        src_ip=f"{link.dst_ip}/{mask}" if mask else link.dst_ip,
        dst_ip=address,
    )


def _isn_differs(link_obj: dict, link: Link) -> bool:
    live_inputs = _inputs(link_obj)
    oriented = _isn_oriented(link_obj, link)
    wanted = {"srcEbgpAsn": oriented.src_asn, "dstEbgpAsn": oriented.dst_asn, "srcIpAddressMask": oriented.src_ip, "dstIpAddress": oriented.dst_ip}
    return _policy(link_obj) != "ebgpVrfLite" or any(live_inputs.get(key) != value for key, value in wanted.items())


def _isn_live_text(link_obj: dict, link: Link) -> str:
    policy = _policy(link_obj)
    if not policy:
        return "none"
    live_inputs = _inputs(link_obj)
    src_ip, dst_ip = live_inputs.get("srcIpAddressMask"), live_inputs.get("dstIpAddress")
    if not (src_ip or dst_ip):
        return policy
    if not _same_direction(link_obj, link.src):
        src_ip, dst_ip = dst_ip, src_ip
    return f"{policy} {src_ip} {dst_ip}"


def _isn_drift(fabric: Fabric, link: Link, link_obj: dict | None) -> Drift | None:
    subject = _subject(link.src, link.src_if, link.dst, link.dst_if)
    if link_obj is None:
        return Drift(LINKS, fabric.name, "missing", subject, _isn_text(link), "none", None, None, None)
    if not _isn_differs(link_obj, link):
        return None
    body = link_payload(_isn_oriented(link_obj, link), link_obj["srcSwitchId"], link_obj["dstSwitchId"])["links"][0]
    fix = Op("put_link", link.src_fabric, "PUT", f"/links/{link_obj['linkId']}", body)
    kind: Kind = "different" if _policy(link_obj) else "missing"
    return Drift(LINKS, fabric.name, kind, subject, _isn_text(link), _isn_live_text(link_obj, link), fix, None, None)


def drift_links(topo: Topology, fabric: Fabric, live: dict[str, LiveFabric], seen: set) -> list[Drift]:
    """Tool-owned links of `fabric` (its `links:` plus the ISN links with an endpoint in it) against the live link list.

    Links are matched by endpoint_key. `seen` carries keys already reported (by this or another fabric) so a link that ND lists under
    every fabric owning an endpoint is reported once. Live links with a tool policy that golden does not know are `extra`; discovered links
    without a policy and ND-generated links are never extras."""
    objs = live[fabric.name].links if fabric.name in live else []
    by_key = _index(objs)
    drifts: list[Drift] = []
    golden_keys: set = set()

    candidates: list[tuple[tuple, FabricLink | Link]] = [(endpoint_key(fl.src, fl.src_if, fl.dst, fl.dst_if), fl) for fl in fabric.links]
    for link in topo.isn.links:
        if fabric.name in (link.src_fabric, link.dst_fabric):
            candidates.append((endpoint_key(link.src, link.src_if, link.dst, link.dst_if), link))
    for key, golden in candidates:
        golden_keys.add(key)
        if key in seen:
            continue
        link_obj = by_key.get(key)
        seen.add(key)
        drift = _isn_drift(fabric, golden, link_obj) if isinstance(golden, Link) else _tool_link_drift(fabric, golden, link_obj)
        if drift:
            drifts.append(drift)

    generated_keys = {endpoint_key(g.src, g.src_if, g.dst, g.dst_if) for f in topo.fabrics for g in f.generated_links}
    for link_obj in objs:
        key = _live_key(link_obj)
        if key in golden_keys or key in generated_keys or key in seen or _policy(link_obj) not in TOOL_LINK_POLICIES:
            continue
        seen.add(key)
        drifts.append(_extra_link_drift(fabric, link_obj))
    return drifts


# ---------------------------------------------------------------- ND-generated links


def _owner_link_lists(topo: Topology, live: dict[str, LiveFabric], owner: str) -> list[list[dict]]:
    names = [owner] + [m for g in topo.fabric_groups if g.name == owner for m in g.members]
    return [live[n].links for n in dict.fromkeys(names) if n in live]


def drift_generated_links(topo: Topology, fabric: Fabric, live: dict[str, LiveFabric]) -> list[Drift]:
    """Links ND generates (multisite underlay/overlay, IOS-XE numbered) only need to exist with their policy. ND writes them when the
    owner is deployed, so the repair is `deploy_owner`; they are never cleared and never adopted. The link is looked for in the owner's
    list and in every member fabric's list and reported once, from the first list in which it is not as golden says."""
    drifts: list[Drift] = []
    for golden in fabric.generated_links:
        key = endpoint_key(golden.src, golden.src_if, golden.dst, golden.dst_if)
        found = [o for objs in _owner_link_lists(topo, live, golden.owner) for o in objs if _live_key(o) == key]
        if any(_policy(o) == golden.policy for o in found):
            continue
        bad = next((o for o in found if _policy(o)), found[0] if found else None)
        subject = _subject(golden.src, golden.src_if, golden.dst, golden.dst_if)
        live_policy = _policy(bad) if bad else ""
        kind: Kind = "different" if live_policy else "missing"
        fix = Op("deploy_owner", golden.owner, "", "", None)
        drifts.append(Drift(GENERATED, fabric.name, kind, subject, golden.policy, live_policy or "none", fix, None, None))
    return drifts


# ---------------------------------------------------------------- interfaces

COMPARED_INPUTS = ("adminState", "mode", "accessVlan", "allowedVlans", "nativeVlan", "description", "mtu")
GENERATED_LOGICAL_POLICIES = {"vpcPeerlinkPo", "vpcUplinkPo", "uplinkPo", "vpcUplink", "vpcBackupSvi"}
LOGICAL_TYPES = {"portChannel", "vpc", "svi", "subInterface"}
_MODES = (("routed", "routed"), ("trunk", "trunk"), ("access", "access"))  # substring of the lowercased policyType -> configData.mode


def _mode_for(policy: str) -> str:
    """configData.mode implied by a host policy name (routedHost, trunkHost, accessHost, iosXeTrunkHost, ...); "" when it implies none."""
    lowered = policy.lower()
    return next((mode for word, mode in _MODES if word in lowered), "")


def _if_policy(intf: dict) -> dict:
    value = (_config(intf).get("networkOS") or {}).get("policy")
    return value if isinstance(value, dict) else {}


def _if_values(intf: dict) -> dict:
    """The live interface as the comparable keys: policyType, mode and the COMPARED_INPUTS found in its policy."""
    policy = _if_policy(intf)
    values = {key: policy[key] for key in COMPARED_INPUTS if key in policy}
    values["policyType"] = policy.get("policyType") or ""
    if _config(intf).get("mode"):
        values["mode"] = _config(intf)["mode"]
    return values


def _norm(value: Any) -> str:
    """None and "" are the same as absent; everything else compares as a string (accessVlan is 1 on one controller and "1" on the other)."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _golden_values(policy: str, description: str, inputs: dict) -> dict:
    values: dict = {"policyType": policy, "description": description}
    mode = _mode_for(policy)
    if mode:
        values["mode"] = mode
    values.update({key: value for key, value in inputs.items() if key in COMPARED_INPUTS})
    return values


def _if_differs(golden: dict, live: dict) -> bool:
    """Golden's keys (and description, always) decide; a live-only key such as ND's accessVlan on a trunk port is not drift."""
    keys = ["policyType", "description", *(k for k in COMPARED_INPUTS if k in golden and k != "description")]
    return any(_norm(golden.get(key)) != _norm(live.get(key)) for key in keys)


def _if_text(values: dict) -> str:
    parts = [f"{key}={_norm(values[key])}" for key in COMPARED_INPUTS if key != "mode" and key in values and _norm(values[key])]
    return " ".join([values.get("policyType") or "none", *parts])


def _if_body(serial: str, interface: str, interface_type: str, policy: dict) -> dict:
    body: dict = {"switchId": serial, "interfaceName": interface, "interfaceType": interface_type, "configData": {}}
    mode = _mode_for(policy.get("policyType", ""))
    if mode:
        body["configData"]["mode"] = mode
    body["configData"]["networkOS"] = {"networkOSType": "nx-os", "policy": policy}
    return body


def interface_body(serial: str, intent: InterfaceIntent, fabric_defaults: dict) -> dict:
    """PUT body for an explicit `interfaces:` entry, in the shape of Provisioner._ensure_access_port; intent.inputs override the built-in
    values. `fabric_defaults` is the fabric's `defaults` (role -> policy); it is accepted for the caller's convenience and not consulted."""
    policy: dict = {
        "policyType": intent.policy,
        "adminState": True,
        "mtu": "jumbo",
        "speed": "auto",
        "bpduGuard": "default",
        "portTypeEdgeTrunk": True,
        "description": intent.description,
    }
    policy.update({key: value for key, value in intent.inputs.items() if key != "mode"})
    return _if_body(serial, intent.interface, intent.type, policy)


def default_body(serial: str, interface: str, role_default: dict) -> dict:
    """PUT body that puts a port back to its role default (the default's policy dict verbatim)."""
    return _if_body(serial, interface, "ethernet", dict(role_default))


def _serial(live: LiveFabric, hostname: str) -> str:
    return (live.switches.get(hostname) or {}).get("serialNumber", "")


def _explicit_interface_drift(fabric: Fabric, live: LiveFabric, intent: InterfaceIntent) -> Drift | None:
    serial = _serial(live, intent.switch)
    if not serial:
        return None
    subject = f"{intent.switch} {intent.interface}"
    golden = _golden_values(intent.policy, intent.description, intent.inputs)
    found = next((i for i in live.interfaces.get(intent.switch, []) if i.get("interfaceName") == intent.interface), None)
    live_values = _if_values(found) if found else {}
    if found and _if_policy(found) and not _if_differs(golden, live_values):
        return None
    kind: Kind = "different" if found and _if_policy(found) else "missing"
    body = interface_body(serial, intent, fabric.defaults)
    fix = Op("put_interface", fabric.name, "PUT", interface_path(fabric.name, serial, intent.interface), body)
    return Drift(INTERFACES, fabric.name, kind, subject, _if_text(golden), _if_text(live_values) if found else "none", fix, None, None)


def _adoption_entry_for_interface(hostname: str, intf: dict, golden: dict | None) -> dict:
    """The `interfaces:` entry that would make the live interface golden. For a free port, `inputs` carries the keys the role default defines
    that differ."""
    live_values = _if_values(intf)
    entry: dict = {"switch": hostname, "interface": intf["interfaceName"], "policy": live_values["policyType"]}
    if intf.get("interfaceType") != "ethernet":
        entry["type"] = intf["interfaceType"]
    if live_values.get("description"):
        entry["description"] = live_values["description"]
    if golden is not None:
        inputs = {
            key: live_values[key]
            for key in COMPARED_INPUTS
            if key not in ("mode", "description") and key in golden and key in live_values and _norm(golden.get(key)) != _norm(live_values[key])
        }
        if inputs:
            entry["inputs"] = inputs
    return entry


def _extra_interface_drift(fabric: Fabric, live: LiveFabric, hostname: str, intf: dict, default: dict | None) -> Drift:
    """`default` is the role default for a free physical port (delete = reset to it); None for a logical interface (delete = DELETE)."""
    serial = _serial(live, hostname)
    name = intf["interfaceName"]
    path = interface_path(fabric.name, serial, name)
    golden = _golden_values(default.get("policyType", ""), default.get("description", ""), default) if default is not None else None
    if default is not None:
        delete = Op("reset_interface", fabric.name, "PUT", path, default_body(serial, name, default))
    else:
        delete = Op("delete_interface", fabric.name, "DELETE", path, None)
    adopt = Adoption(("fabrics", fabric.name, INTERFACES), _adoption_entry_for_interface(hostname, intf, golden))
    return Drift(INTERFACES, fabric.name, "extra", f"{hostname} {name}", _if_text(golden) if golden else "none", _if_text(_if_values(intf)), None, delete, adopt)


def _overlay_vlans(topo: Topology) -> set[int]:
    vlans = {1}
    for item in [*topo.overlay.vrfs, *topo.overlay.networks]:
        value = (item.get("object") or {}).get("vlanId")
        if value is not None:
            vlans.add(int(value))
    return vlans


def _is_generated_logical(intf: dict, vlans: set[int], endpoints: set[tuple[str, str]], hostname: str) -> bool:
    if _if_policy(intf).get("policyType") in GENERATED_LOGICAL_POLICIES:
        return True
    name = intf.get("interfaceName", "")
    kind = intf.get("interfaceType")
    if kind == "svi":
        match = re.fullmatch(r"[Vv]lan(\d+)", name)
        return match is not None and int(match.group(1)) in vlans
    if kind == "subInterface":
        return (hostname, name.split(".")[0]) in endpoints
    return False


def drift_interfaces(topo: Topology, fabric: Fabric, live: dict[str, LiveFabric], all_links: list[dict]) -> list[Drift]:
    """Interface drift of `fabric`: explicit `interfaces:` entries (missing/different, fix = put_interface), free physical ports that are not
    as the role default says (extra, delete = reset_interface) and logical interfaces golden does not list (extra, delete = delete_interface).

    Free ports come from `free_ports`, so a link endpoint or port-channel member is never an extra. A role without an entry in
    `fabric.defaults` has its free ports left unchecked. Core routers and externalConnectivity fabrics are skipped. Only the golden-defined
    keys and the description are compared (`COMPARED_INPUTS`, values as strings)."""
    if fabric.type == "externalConnectivity" or fabric.name not in live:
        return []
    fab_live = live[fabric.name]
    vlans = _overlay_vlans(topo)
    endpoints = {(link.get(f"{side}SwitchName", ""), link.get(f"{side}InterfaceName", "")) for link in all_links for side in ("src", "dst")}
    listed = {(i.switch, i.interface) for i in fabric.interfaces}
    drifts: list[Drift] = []
    for intent in fabric.interfaces:
        role = next((s.role for s in fabric.switches if s.hostname == intent.switch), "")
        if role == "coreRouter":
            continue
        drift = _explicit_interface_drift(fabric, fab_live, intent)
        if drift:
            drifts.append(drift)
    for switch in fabric.switches:
        if switch.role == "coreRouter":
            continue
        default = fabric.defaults.get(switch.role)
        if default:
            golden = _golden_values(default.get("policyType", ""), default.get("description", ""), default)
            for intf in free_ports(fab_live, switch.hostname, all_links):
                if (switch.hostname, intf["interfaceName"]) in listed:
                    continue
                if _if_differs(golden, _if_values(intf)):
                    drifts.append(_extra_interface_drift(fabric, fab_live, switch.hostname, intf, default))
        for intf in fab_live.interfaces.get(switch.hostname, []):
            if intf.get("interfaceType") not in LOGICAL_TYPES or (switch.hostname, intf["interfaceName"]) in listed:
                continue
            if not _is_generated_logical(intf, vlans, endpoints, switch.hostname):
                drifts.append(_extra_interface_drift(fabric, fab_live, switch.hostname, intf, None))
    return drifts


# ---------------------------------------------------------------- report


def format_report(drifts: list[Drift]) -> str:
    """One line per drift, e.g. `SITE1 links      MISSING policy  S1_SP1 Ethernet1/2 <-> S1_LE1 Ethernet1/1   golden=numbered 10.14.0.5/.6  live=none`."""
    lines = []
    for d in drifts:
        noun = "link" if d.kind == "extra" else "policy"
        lines.append(f"{d.fabric} {d.cls:<10} {d.kind.upper()} {noun}  {d.subject}   golden={d.golden}  live={d.live}")
    return "\n".join(lines)
