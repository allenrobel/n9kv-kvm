"""Replication-mode knowledge shared by provision.py and the golden tools. Pure: no I/O."""

from __future__ import annotations

from topology import merge_settings

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
