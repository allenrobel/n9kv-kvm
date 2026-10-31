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
from provision import attachment_payload, link_payload, merge_settings, tor_associate_payload, vpc_pair_payload
from topology import TOOL_LINK_POLICIES, Fabric, FabricLink, FabricGroup, InterfaceIntent, Link, Topology, TorPair, endpoint_key

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
    create_network, delete_vrf, delete_network, deploy_overlay, pair_vpc, unpair_vpc, pair_tor, unpair_tor, add_switch, set_role, put_settings, deploy_owner."""

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
    delete: Op | list[Op] | None  # a list is an ordered sequence (detach, deploy, DELETE)
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


def _pending_delete(intf: dict) -> bool:
    """ND keeps a deleted interface (renamed, e.g. `Port-channel10`) until the next deploy, with the `interface_delete` template."""
    return _if_policy(intf).get("templateName") == "interface_delete"


def _same_name(a: str, b: str) -> bool:
    return a.lower() == b.lower()


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


INTEGER_INPUTS = ("mtu", "accessVlan", "nativeVlan")  # integer in every ND 4.3.1 int_*_host template (mtu only when numeric; "jumbo" stays)


# boolean in the ND 4.3.1 interface policy templates; only these are converted, so a description that reads "true" stays a string
BOOLEAN_INPUTS = (
    "adminState",
    "portTypeEdgeTrunk",
    "cdp",
    "netflow",
    "pfc",
    "qos",
    "monitor",
    "orphanPort",
    "negotiateAuto",
    "errorDetectionAcl",
    "stormControl",
    "ipRedirects",
    "pimSparse",
    "vlanMapping",
)


def _native(key: str, value: Any) -> Any:
    """ND's own type for a policy input: golden yaml and adopted defaults carry the lowercase strings the drift comparison uses
    ('true', '9216'), but ND 4.3.1's schema validation rejects them (adminState must be a boolean, a numeric mtu an integer)."""
    if key in BOOLEAN_INPUTS and isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    if key in INTEGER_INPUTS and isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def _if_body(serial: str, interface: str, interface_type: str, policy: dict, os_type: str = "nx-os") -> dict:
    """Empty-string inputs are dropped: ND 4.3.1 declares string inputs such as `description` with minLength 1."""
    body: dict = {"switchId": serial, "interfaceName": interface, "interfaceType": interface_type, "configData": {}}
    mode = _mode_for(policy.get("policyType", ""))
    if mode:
        body["configData"]["mode"] = mode
    native = {key: _native(key, value) for key, value in policy.items() if value != ""}
    body["configData"]["networkOS"] = {"networkOSType": os_type, "policy": native}
    return body


# Seed policy for an explicit `interfaces:` entry when the switch role's default cannot serve as the base. The NX-OS seed is the shape of
# Provisioner._ensure_access_port (live-proven on both controllers); ND 4.3.1's iosXe*Host templates have no portTypeEdgeTrunk and no
# bpduGuard on a trunk, and type mtu as an integer (1500-9216), so the IOS-XE seed carries only what every iosXe host template accepts.
NXOS_SEED: dict = {"adminState": True, "mtu": "jumbo", "speed": "auto", "bpduGuard": "default", "portTypeEdgeTrunk": True}
IOSXE_SEED: dict = {"adminState": True, "mtu": 1500}


def interface_body(serial: str, intent: InterfaceIntent, fabric_defaults: dict, os_type: str = "nx-os", role: str = "") -> dict:
    """PUT body for an explicit `interfaces:` entry: a base policy overlaid with the entry's policyType, its description (only when
    non-empty) and its inputs. The base is the switch role's default (`fabric_defaults[role]`, the fabric's `defaults:`) when that default
    is in the same port mode as the entry (both trunk, both routed, ...), since its inputs then belong to the same template family; otherwise
    (no default, or e.g. a trunkHost leaf default under an accessHost entry, whose allowedVlans/numeric mtu the access template rejects)
    the platform seed."""
    default = fabric_defaults.get(role) if role else None
    if default and _mode_for(str(default.get("policyType", ""))) == _mode_for(intent.policy):
        policy: dict = dict(default)
    else:
        policy = dict(IOSXE_SEED if os_type == "ios-xe" else NXOS_SEED)
    policy["policyType"] = intent.policy
    if intent.description:
        policy["description"] = intent.description
    policy.update({key: value for key, value in intent.inputs.items() if key != "mode"})
    return _if_body(serial, intent.interface, intent.type, policy, os_type)


def default_body(serial: str, interface: str, role_default: dict, os_type: str = "nx-os") -> dict:
    """PUT body that puts a port back to its role default (the default's policy dict verbatim)."""
    return _if_body(serial, interface, "ethernet", dict(role_default), os_type)


def _os_type(fabric: Fabric, hostname: str, intf: dict | None = None) -> str:
    """networkOSType for an interface body: the live interface's own value when it has one, else the golden switch's platform."""
    live_type = ((_config(intf).get("networkOS") or {}).get("networkOSType")) if intf else None
    if live_type:
        return str(live_type)
    return next((s.platform for s in fabric.switches if s.hostname == hostname), "nx-os")


def _serial(live: LiveFabric, hostname: str) -> str:
    return (live.switches.get(hostname) or {}).get("serialNumber", "")


def _explicit_interface_drift(fabric: Fabric, live: LiveFabric, intent: InterfaceIntent) -> Drift | None:
    serial = _serial(live, intent.switch)
    if not serial:
        return None
    subject = f"{intent.switch} {intent.interface}"
    golden = _golden_values(intent.policy, intent.description, intent.inputs)
    found = next((i for i in live.interfaces.get(intent.switch, []) if _same_name(i.get("interfaceName", ""), intent.interface)), None)
    if found and _pending_delete(found):
        return Drift(INTERFACES, fabric.name, "different", subject, _if_text(golden), "pending deletion", None, None, None)
    live_values = _if_values(found) if found else {}
    if found and _if_policy(found) and not _if_differs(golden, live_values):
        return None
    kind: Kind = "different" if found and _if_policy(found) else "missing"
    role = next((s.role for s in fabric.switches if s.hostname == intent.switch), "")
    body = interface_body(serial, intent, fabric.defaults, _os_type(fabric, intent.switch, found), role)
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
        delete = Op("reset_interface", fabric.name, "PUT", path, default_body(serial, name, default, _os_type(fabric, hostname, intf)))
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
        return (hostname, name.split(".")[0].lower()) in endpoints
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
    endpoints = {(link.get(f"{side}SwitchName", ""), link.get(f"{side}InterfaceName", "").lower()) for link in all_links for side in ("src", "dst")}
    listed = {(i.switch, i.interface.lower()) for i in fabric.interfaces}
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
                if (switch.hostname, intf["interfaceName"].lower()) in listed or _pending_delete(intf):
                    continue
                if _if_differs(golden, _if_values(intf)):
                    drifts.append(_extra_interface_drift(fabric, fab_live, switch.hostname, intf, default))
        for intf in fab_live.interfaces.get(switch.hostname, []):
            if intf.get("interfaceType") not in LOGICAL_TYPES or (switch.hostname, intf["interfaceName"].lower()) in listed or _pending_delete(intf):
                continue
            if not _is_generated_logical(intf, vlans, endpoints, switch.hostname):
                drifts.append(_extra_interface_drift(fabric, fab_live, switch.hostname, intf, None))
    return drifts


# ---------------------------------------------------------------- settings

SETTINGS = "settings"


def _leaves(settings: dict, prefix: tuple = ()) -> list[tuple[tuple, Any]]:
    out: list[tuple[tuple, Any]] = []
    for key, value in settings.items():
        if isinstance(value, dict):
            out.extend(_leaves(value, (*prefix, key)))
        else:
            out.append(((*prefix, key), value))
    return out


def _dig(settings: Any, path: tuple) -> Any:
    for key in path:
        if not isinstance(settings, dict):
            return None
        settings = settings.get(key)
    return settings


def drift_settings(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]:
    """Every leaf of a golden fabric's or group's `settings` whose live value differs (compared as strings); one `different` drift per key,
    subject `management.<key>`. All drifts of one fabric share one `put_settings` fix, the live settings merged with golden's. Keys the
    live object has beyond golden are never drift."""
    drifts: list[Drift] = []
    owners: list[Fabric | FabricGroup] = [*topo.fabrics, *topo.fabric_groups]
    for item in owners:
        if item.name not in live:
            continue
        current = live[item.name].settings
        fix: Op | None = None
        for path, wanted in _leaves(item.settings):
            found = _dig(current, path)
            if _norm(wanted) == _norm(found):
                continue
            if fix is None:
                fix = Op("put_settings", item.name, "PUT", f"/fabrics/{item.name}", merge_settings(current, item.settings))
            drifts.append(Drift(SETTINGS, item.name, "different", ".".join(path), _norm(wanted) or "none", _norm(found) or "none", fix, None, None))
    return drifts


# ---------------------------------------------------------------- switches

SWITCHES = "switches"


def drift_switches(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]:
    """Switch membership and role per golden fabric. A golden switch absent from its fabric is `missing` (fix add_switch; the body is a
    marker, the applier runs the switch phase), one with another role is `different` (fix set_role), one found only in another fabric is
    `different` without a fix, and a live switch golden does not list anywhere is `extra`: adoptable, never deletable."""
    golden_hosts = {s.hostname for f in topo.fabrics for s in f.switches}
    drifts: list[Drift] = []
    for fabric in topo.fabrics:
        if fabric.name not in live:
            continue
        fab_live = live[fabric.name]
        for switch in fabric.switches:
            found = fab_live.switches.get(switch.hostname)
            if found is None:
                elsewhere = next((n for n, lf in live.items() if n != fabric.name and switch.hostname in lf.switches), None)
                if elsewhere:
                    drifts.append(Drift(SWITCHES, fabric.name, "different", switch.hostname, f"in {fabric.name}", f"in {elsewhere}", None, None, None))
                else:
                    fix = Op("add_switch", fabric.name, "POST", f"/fabrics/{fabric.name}/switches", None)
                    drifts.append(Drift(SWITCHES, fabric.name, "missing", switch.hostname, switch.role, "none", fix, None, None))
            elif found.get("switchRole") != switch.role:
                body = {"switchRoles": [{"switchId": found["serialNumber"], "role": switch.role}]}
                fix = Op("set_role", fabric.name, "POST", f"/fabrics/{fabric.name}/switchActions/changeRoles", body)
                drifts.append(Drift(SWITCHES, fabric.name, "different", switch.hostname, switch.role, str(found.get("switchRole")), fix, None, None))
        listed = {s.hostname for s in fabric.switches}
        for hostname, found in fab_live.switches.items():
            if hostname in listed or hostname in golden_hosts:
                continue
            entry = {"hostname": hostname, "ip": found.get("fabricManagementIp", ""), "role": found.get("switchRole", "")}
            drifts.append(Drift(SWITCHES, fabric.name, "extra", hostname, "none", entry["role"], None, None, Adoption(("fabrics", fabric.name, SWITCHES), entry)))
    return drifts


# ---------------------------------------------------------------- vrfs, networks, attachments

VRFS = "vrfs"
NETWORKS = "networks"
ATTACHMENTS = "attachments"
VRF_KEYS = (("vrfName",), ("vrfId",), ("vlanId",))
NETWORK_KEYS = (("networkName",), ("networkId",), ("vlanId",), ("vrfName",), ("l3Data", "gatewayIpv4Address"))
ADOPT_EXTRA_KEYS = {VRFS: (("vrfType",),), NETWORKS: (("networkType",), ("networkMode",))}
BUILT_IN_VRFS = {"default"}  # ND's own VRF (the externalConnectivity fabrics list it); never an extra, never deleted


def _overlay_text(obj: dict, keys: tuple) -> str:
    return " ".join(f"{'.'.join(k)}={_norm(_dig(obj, k))}" for k in keys if _norm(_dig(obj, k)))


def _overlay_differs(golden: dict, live_obj: dict, keys: tuple) -> bool:
    return any(_norm(_dig(live_obj, k)) != _norm(_dig(golden, k)) for k in keys if _dig(golden, k) is not None)


def _adopt_object(live_obj: dict, keys: tuple, extra: tuple) -> dict:
    out: dict = {}
    for path in (*keys, *extra):
        value = _dig(live_obj, path)
        if value is None:
            continue
        target = out
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = value
    return out


def _attachment_rows(fab_live: LiveFabric, kind: str) -> list[dict]:
    return fab_live.vrf_attachments if kind == "vrf" else fab_live.network_attachments


def _row_host(fab_live: LiveFabric, row: dict) -> str:
    name = row.get("switchName")
    if name:
        return name
    return next((h for h, s in fab_live.switches.items() if s.get("serialNumber") == row.get("switchId")), row.get("switchId", ""))


def _extra_overlay_drift(kind: str, fabric: str, live: dict[str, LiveFabric], obj: dict, scope: list[str]) -> Drift:
    """Extra VRF/network: delete = detach every attached switch (in `scope`: the fabric, or a group's member fabrics, where the propagated
    copies are attached), deploy them, then DELETE the object."""
    key = "vrfName" if kind == "vrf" else "networkName"
    name = obj[key]
    names_key = "vrfNames" if kind == "vrf" else "networkNames"
    ops: list[Op] = []
    for target in scope:
        rows = [r for r in _attachment_rows(live[target], kind) if r.get(key) == name]
        for row in rows:
            att = {"vrf": name} if kind == "vrf" else {"network": name, "vlan": row.get("vlanId"), "interfaces": row.get("interfaces") or []}
            body = attachment_payload(kind, att, row["switchId"])
            body["attachments"][0]["attach"] = False
            ops.append(Op("detach", target, "POST", f"/fabrics/{target}/{kind}Attachments", body))
        if rows:
            deploy = {names_key: [name], "switchIds": sorted({r["switchId"] for r in rows})}
            ops.append(Op("deploy_overlay", target, "POST", f"/fabrics/{target}/{kind}Actions/deploy", deploy))
    plural = "vrfs" if kind == "vrf" else "networks"
    ops.append(Op(f"delete_{kind}", fabric, "DELETE", f"/fabrics/{fabric}/{plural}/{name}", None))
    keys = VRF_KEYS if kind == "vrf" else NETWORK_KEYS
    entry = {"fabrics": [fabric], "object": _adopt_object(obj, keys, ADOPT_EXTRA_KEYS[plural])}
    return Drift(plural, fabric, "extra", name, "none", _overlay_text(obj, keys), None, ops, Adoption(("overlay", plural), entry))


def _group_copies(topo: Topology, live: dict[str, LiveFabric], group: str, kind: str, name: str) -> list[dict] | None:
    """The live copies of a group-level object: the group's own object, else the propagated copy in every member that can hold one (all
    but externalConnectivity fabrics); None when neither exists. The dumps hold no group objects, so this is how a snapshot shows them."""
    key = "vrfName" if kind == "vrf" else "networkName"
    attr = "vrfs" if kind == "vrf" else "networks"
    own = [o for o in getattr(live[group], attr) if o.get(key) == name] if group in live else []
    if own:
        return own
    types = {f.name: f.type for f in topo.fabrics}
    members = [m for g in topo.fabric_groups if g.name == group for m in g.members if m in live and types.get(m) != "externalConnectivity"]
    copies = [o for m in members for o in getattr(live[m], attr) if o.get(key) == name]
    return copies if members and len(copies) == len(members) else None


def _expected_names(topo: Topology, kind: str) -> dict[str, set[str]]:
    """Per fabric or group, the golden object names it holds, including the copies a golden group object propagates to its members."""
    items = topo.overlay.vrfs if kind == "vrf" else topo.overlay.networks
    key = "vrfName" if kind == "vrf" else "networkName"
    groups = {g.name: g for g in topo.fabric_groups}
    expected: dict[str, set[str]] = {}
    for item in items:
        name = item["object"][key]
        for fabric in item["fabrics"]:
            expected.setdefault(fabric, set()).add(name)
            for member in groups[fabric].members if fabric in groups else []:
                expected.setdefault(member, set()).add(name)
    return expected


def _overlay_extras(topo: Topology, live: dict[str, LiveFabric], kind: str) -> list[tuple[str, dict, list[str]]]:
    """(fabric, live object, fabrics whose attachments the delete must detach) for every VRF/network golden does not name.

    A group-level extra (the group's own object, or, in a snapshot without group objects, a name every non-externalConnectivity member
    holds) carries all the members as scope; the propagated copies in the members are then not extras of their own."""
    key, attr = ("vrfName", "vrfs") if kind == "vrf" else ("networkName", "networks")
    expected = _expected_names(topo, kind)
    types = {f.name: f.type for f in topo.fabrics}
    group_objs: dict[str, dict[str, dict]] = {}
    for group in topo.fabric_groups:
        if group.name not in live:
            continue
        objs = {o[key]: o for o in getattr(live[group.name], attr)}
        holders = [m for m in group.members if m in live and types.get(m) != "externalConnectivity"]
        for member in holders[:1]:
            for obj in getattr(live[member], attr):
                if obj[key] not in objs and all(any(o[key] == obj[key] for o in getattr(live[m], attr)) for m in holders):
                    objs[obj[key]] = obj
        group_objs[group.name] = objs
    propagated = {m: set(objs) for g in topo.fabric_groups if g.name in group_objs for objs in [group_objs[g.name]] for m in g.members}
    extras: list[tuple[str, dict, list[str]]] = []
    for fabric in (f.name for f in topo.fabrics):
        if fabric not in live:
            continue
        for obj in getattr(live[fabric], attr):
            name = obj[key]
            if name in expected.get(fabric, set()) or name in propagated.get(fabric, set()) or (kind == "vrf" and name in BUILT_IN_VRFS):
                continue
            extras.append((fabric, obj, [fabric]))
    for group in topo.fabric_groups:
        for name, obj in group_objs.get(group.name, {}).items():
            if name not in expected.get(group.name, set()):
                extras.append((group.name, obj, [m for m in group.members if m in live]))
    return extras


def _overlay_object_drifts(topo: Topology, live: dict[str, LiveFabric], kind: str) -> list[Drift]:
    items = topo.overlay.vrfs if kind == "vrf" else topo.overlay.networks
    key, attr, plural = ("vrfName", "vrfs", VRFS) if kind == "vrf" else ("networkName", "networks", NETWORKS)
    keys = VRF_KEYS if kind == "vrf" else NETWORK_KEYS
    groups = {g.name: g for g in topo.fabric_groups}
    drifts: list[Drift] = []
    for item in items:
        golden = item["object"]
        name = golden[key]
        for fabric in item["fabrics"]:
            if fabric not in live:
                continue
            copies = _group_copies(topo, live, fabric, kind, name) if fabric in groups else [o for o in getattr(live[fabric], attr) if o.get(key) == name] or None
            create = Op(f"create_{kind}", fabric, "POST", f"/fabrics/{fabric}/{plural}", {plural: [dict(golden, fabricName=fabric)]})
            text = _overlay_text(golden, keys)
            if not copies:
                drifts.append(Drift(plural, fabric, "missing", name, text, "none", create, None, None))
                continue
            bad = next((c for c in copies if _overlay_differs(golden, c, keys)), None)
            if bad is not None:
                drifts.append(Drift(plural, fabric, "different", name, text, _overlay_text(bad, keys), None, None, None))
    drifts.extend(_extra_overlay_drift(kind, fabric, live, obj, scope) for fabric, obj, scope in _overlay_extras(topo, live, kind))
    return drifts


def _norm_interfaces(value: Any) -> list[tuple[str, str]]:
    return sorted((str(i.get("interfaceRange", "")), str(i.get("mode", ""))) for i in (value or []))


def _attachment_text(kind: str, vlan: Any, interfaces: Any) -> str:
    if kind == "vrf":
        return "attached"
    ranges = ",".join(f"{r}:{m}" for r, m in _norm_interfaces(interfaces)) or "none"
    return f"vlan={_norm(vlan)} interfaces={ranges}"


def _attachment_drifts(topo: Topology, live: dict[str, LiveFabric], kind: str) -> list[Drift]:
    rows = topo.overlay.vrf_attachments if kind == "vrf" else topo.overlay.network_attachments
    key = "vrfName" if kind == "vrf" else "networkName"
    gkey = "vrf" if kind == "vrf" else "network"
    drifts: list[Drift] = []
    wanted: set[tuple[str, str, str]] = set()
    owned = {(target, obj[key]) for _, obj, scope in _overlay_extras(topo, live, kind) for target in scope}  # their delete lists detach these
    for att in rows:
        fabric, name, switch = att["fabric"], att[gkey], att["switch"]
        wanted.add((fabric, name, switch))
        if fabric not in live:
            continue
        fab_live = live[fabric]
        found = next((r for r in _attachment_rows(fab_live, kind) if r.get(key) == name and _row_host(fab_live, r) == switch), None)
        golden_text = _attachment_text(kind, att.get("vlan"), att.get("interfaces"))
        if found is not None and (
            kind == "vrf"
            or (_norm(found.get("vlanId")) == _norm(att.get("vlan")) and _norm_interfaces(found.get("interfaces")) == _norm_interfaces(att.get("interfaces")))
        ):
            continue
        serial = (fab_live.switches.get(switch) or {}).get("serialNumber", "")
        fix = Op("attach", fabric, "POST", f"/fabrics/{fabric}/{kind}Attachments", attachment_payload(kind, att, serial)) if serial else None
        live_text = "none" if found is None else _attachment_text(kind, found.get("vlanId"), found.get("interfaces"))
        drifts.append(Drift(ATTACHMENTS, fabric, "missing" if found is None else "different", f"{name} {switch}", golden_text, live_text, fix, None, None))
    for fabric in [f.name for f in topo.fabrics]:
        if fabric not in live:
            continue
        fab_live = live[fabric]
        for row in _attachment_rows(fab_live, kind):
            host = _row_host(fab_live, row)
            name = row.get(key, "")
            if (fabric, name, host) in wanted or (fabric, name) in owned:
                continue
            att = {"vrf": name} if kind == "vrf" else {"network": name, "vlan": row.get("vlanId"), "interfaces": row.get("interfaces") or []}
            body = attachment_payload(kind, att, row["switchId"])
            body["attachments"][0]["attach"] = False
            delete = Op("detach", fabric, "POST", f"/fabrics/{fabric}/{kind}Attachments", body)
            entry = {"fabric": fabric, gkey: name, "switch": host, **({} if kind == "vrf" else {"vlan": row.get("vlanId"), "interfaces": row.get("interfaces") or []})}
            adopt = Adoption(("overlay", f"{kind}_attachments"), entry)
            drifts.append(
                Drift(ATTACHMENTS, fabric, "extra", f"{name} {host}", "none", _attachment_text(kind, row.get("vlanId"), row.get("interfaces")), None, delete, adopt)
            )
    return drifts


def drift_overlay(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]:
    """VRFs, networks, then VRF and network attachments. Objects compare on the identity keys only (never vrfType/networkType, which differ
    between a group's object and its propagated copies); a group-level golden object is present when the group or all its member fabrics
    hold it, and propagated copies are never extras. Attachments compare `vlanId` and `interfaces` (any order) of rows with attach true."""
    return [
        *_overlay_object_drifts(topo, live, "vrf"),
        *_overlay_object_drifts(topo, live, "network"),
        *_attachment_drifts(topo, live, "vrf"),
        *_attachment_drifts(topo, live, "network"),
    ]


# ---------------------------------------------------------------- vPC and ToR pairs

PAIRS = "pairs"


def _vpc_drifts(topo: Topology, fabric: Fabric, fab_live: LiveFabric) -> list[Drift]:
    drifts: list[Drift] = []
    golden = [p for p in topo.vpc_pairs if p.fabric == fabric.name]
    listed = {frozenset((p.switch, p.peer)) for p in golden}
    present = {frozenset((p.get("switchName"), p.get("peerSwitchName"))) for p in fab_live.vpc_pairs}
    for pair in golden:
        if frozenset((pair.switch, pair.peer)) in present:
            continue
        serial, peer = _serial(fab_live, pair.switch), _serial(fab_live, pair.peer)
        fix = Op("pair_vpc", fabric.name, "PUT", f"/fabrics/{fabric.name}/switches/{serial}/vpcPair", vpc_pair_payload(serial, peer)) if serial and peer else None
        drifts.append(Drift(PAIRS, fabric.name, "missing", f"{pair.switch} <-> {pair.peer}", "paired", "none", fix, None, None))
    for entry in fab_live.vpc_pairs:
        if frozenset((entry.get("switchName"), entry.get("peerSwitchName"))) in listed:
            continue
        name, peer = entry.get("switchName", ""), entry.get("peerSwitchName", "")
        serial = entry.get("switchId", "")
        delete = Op("unpair_vpc", fabric.name, "PUT", f"/fabrics/{fabric.name}/switches/{serial}/vpcPair", {"vpcAction": "unPair"})
        adopt = Adoption(("vpc_pairs",), {"fabric": fabric.name, "switch": name, "peer": peer})
        drifts.append(Drift(PAIRS, fabric.name, "extra", f"{name} <-> {peer}", "none", "paired", None, delete, adopt))
    return drifts


def _tor_key(tor: str, leaf: str, peer: str) -> tuple[str, frozenset]:
    return (tor, frozenset((leaf, peer)))


def _tor_adoption(fabric: str, tor: str, leaf: str, peer: str, resources: dict) -> Adoption:
    entry: dict = {"fabric": fabric, "tor": tor, "leaf": leaf, "peer": peer}
    for field_name, key in (("tor_po", "accessOrTorPortChannelId"), ("leaf_po", "aggregationOrLeafPortChannelId"), ("vpc_id", "aggregationOrLeafVpcId")):
        if resources.get(key) is not None:
            entry[field_name] = resources[key]
    return Adoption(("tor_pairs",), entry)


def _tor_drifts(topo: Topology, fabric: Fabric, fab_live: LiveFabric) -> list[Drift]:
    drifts: list[Drift] = []
    golden: list[TorPair] = [p for p in topo.tor_pairs if p.fabric == fabric.name]
    live_assocs = [a for a in fab_live.tor_associations if a.get("resources")]  # a record without ids is only ND's recommendation
    present = {_tor_key(a.get("accessOrTorSwitchId", ""), a.get("aggregationOrLeafSwitchId", ""), a.get("aggregationOrLeafPeerSwitchId", "")) for a in live_assocs}
    listed: set = set()
    for pair in golden:
        tor, leaf, peer = _serial(fab_live, pair.tor), _serial(fab_live, pair.leaf), _serial(fab_live, pair.peer)
        listed.add(_tor_key(tor, leaf, peer))
        if _tor_key(tor, leaf, peer) in present:
            continue
        resources = pair.resources()
        fix = Op("pair_tor", fabric.name, "POST", f"/fabrics/{fabric.name}/accessAssociationActions/associate", tor_associate_payload(tor, leaf, peer, resources))
        drifts.append(
            Drift(
                PAIRS,
                fabric.name,
                "missing",
                f"{pair.tor} -> {pair.leaf}/{pair.peer}",
                "associated",
                "none",
                fix if tor and leaf and peer and resources else None,
                None,
                None,
            )
        )
    names = {s.get("serialNumber"): h for h, s in fab_live.switches.items()}
    for assoc in live_assocs:
        tor, leaf, peer = assoc.get("accessOrTorSwitchId", ""), assoc.get("aggregationOrLeafSwitchId", ""), assoc.get("aggregationOrLeafPeerSwitchId", "")
        if _tor_key(tor, leaf, peer) in listed:
            continue
        # disassociate takes the three serial-number keys per item only (ND 4.3.1 schema); `resources` belongs to associate
        body = [{"accessOrTorSwitchId": tor, "aggregationOrLeafSwitchId": leaf, "aggregationOrLeafPeerSwitchId": peer}]
        delete = Op("unpair_tor", fabric.name, "POST", f"/fabrics/{fabric.name}/accessAssociationActions/disassociate", body)
        n_tor, n_leaf, n_peer = names.get(tor, tor), names.get(leaf, leaf), names.get(peer, peer)
        drifts.append(
            Drift(
                PAIRS,
                fabric.name,
                "extra",
                f"{n_tor} -> {n_leaf}/{n_peer}",
                "none",
                "associated",
                None,
                delete,
                _tor_adoption(fabric.name, n_tor, n_leaf, n_peer, assoc["resources"]),
            )
        )
    return drifts


def drift_pairs(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]:
    """vPC pairs (either switch order matches), then ToR associations. Missing pairs fix with the phase_vpc / phase_tor call; extras unpair
    or disassociate with the same body and are adoptable. A ToR pair without port-channel ids in the topology has no fix."""
    fabrics = [f for f in topo.fabrics if f.name in live]
    return [*(d for f in fabrics for d in _vpc_drifts(topo, f, live[f.name])), *(d for f in fabrics for d in _tor_drifts(topo, f, live[f.name]))]


# ---------------------------------------------------------------- everything


def compute(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]:
    """All drift classes in a stable order: settings, switches, links, generated links, interfaces, vrfs, networks, attachments, pairs."""
    all_links = [link for fab in live.values() for link in fab.links]
    seen: set = set()
    drifts = [*drift_settings(topo, live), *drift_switches(topo, live)]
    for fabric in topo.fabrics:
        drifts.extend(drift_links(topo, fabric, live, seen))
    for fabric in topo.fabrics:
        drifts.extend(drift_generated_links(topo, fabric, live))
    for fabric in topo.fabrics:
        drifts.extend(drift_interfaces(topo, fabric, live, all_links))
    drifts.extend(drift_overlay(topo, live))
    drifts.extend(drift_pairs(topo, live))
    return drifts


# ---------------------------------------------------------------- report


def format_report(drifts: list[Drift]) -> str:
    """One line per drift, e.g. `SITE1 links      MISSING policy  S1_SP1 Ethernet1/2 <-> S1_LE1 Ethernet1/1   golden=numbered 10.14.0.5/.6  live=none`."""
    lines = []
    for d in drifts:
        noun = "link" if d.kind == "extra" else "policy"
        lines.append(f"{d.fabric} {d.cls:<10} {d.kind.upper()} {noun}  {d.subject}   golden={d.golden}  live={d.live}")
    return "\n".join(lines)
