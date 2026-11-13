"""Replication-mode knowledge shared by provision.py and the golden tools. Pure: no I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING

from topology import merge_settings

if TYPE_CHECKING:
    from golden_live import LiveFabric
    from topology import Topology

# fabric `management` keys that only exist (or only mean something) under multicast replication
MULTICAST_ONLY_KEYS: tuple[str, ...] = (
    "anycastRendezvousPointIpRange",
    "multicastGroupSubnet",
    "rendezvousPointLoopbackId",
    "underlayMulticastGroupAddressLimit",
    "autoGenerateMulticastGroupAddress",
    "tenantRoutedMulticastIpv6",
)

# fabric policies a switch carries for each replication mode
MODE_POLICIES: dict[str, tuple[str, ...]] = {
    "multicast": ("base_multicast_11_1", "base_pim_asm_v6"),
    "ingress": ("ingress_rep_simulated",),
}


def settings_body(current: dict, settings: dict) -> dict:
    """The PUT body for a fabric: `settings` merged over `current`; an ingress fabric loses every multicast-only key."""
    body = merge_settings(current, settings)
    management = body.get("management")
    if isinstance(management, dict) and management.get("replicationMode") == "ingress":
        for key in MULTICAST_ONLY_KEYS:
            management.pop(key, None)
    return body


def live_mode(fabric_obj: dict) -> str | None:
    """`management.replicationMode` of a fabric GET body."""
    return (fabric_obj.get("management") or {}).get("replicationMode")


def fabric_state(live: LiveFabric) -> str:
    """ "multicast", "ingress" or "mid": the fabric's real replication mode, not just its saved setting.

    "mid" means the setting disagrees with what the switches hold: a switch carries a policy of the other mode (saved, never deployed),
    or a switch still has pending config (recalculated, deploy unfinished). A snapshot read has no policies, so the setting alone decides.
    """
    mode = live_mode(live.settings)
    if live.mode_policies is None:
        return mode or "mid"
    other = {t for m, templates in MODE_POLICIES.items() if m != mode for t in templates}
    if any(held & other for held in live.mode_policies.values()) or any((live.pending or {}).values()):
        return "mid"
    return mode or "mid"


def testbed_state(topo: Topology, live: dict[str, LiveFabric]) -> str:
    """The common `fabric_state` of every fabric that declares replication modes, else "mid"."""
    states = {fabric_state(live[name]) for name in topo.mode_fabrics}
    return states.pop() if len(states) == 1 else "mid"
