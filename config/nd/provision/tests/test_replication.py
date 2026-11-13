"""Tests for replication.py: the ingress settings body and the live-mode reader."""

from replication import MODE_POLICIES, MULTICAST_ONLY_KEYS, live_mode, settings_body


def test_ingress_body_drops_every_multicast_only_key():
    current = {"management": {"replicationMode": "multicast", "bgpLoopbackIpRange": "10.11.0.0/22", **{k: "x" for k in MULTICAST_ONLY_KEYS}}}
    body = settings_body(current, {"management": {"replicationMode": "ingress"}})
    assert body["management"] == {"replicationMode": "ingress", "bgpLoopbackIpRange": "10.11.0.0/22"}


def test_multicast_body_keeps_the_pinned_rp_range():
    current = {"management": {"replicationMode": "ingress"}}
    body = settings_body(current, {"management": {"replicationMode": "multicast", "anycastRendezvousPointIpRange": "10.13.0.0/24"}})
    assert body["management"]["anycastRendezvousPointIpRange"] == "10.13.0.0/24"


def test_modeless_settings_are_a_plain_merge():
    current = {"management": {"anycastRendezvousPointIpRange": "10.43.0.0/24"}}
    assert settings_body(current, {"management": {"fabricMtu": 8978}})["management"] == {"anycastRendezvousPointIpRange": "10.43.0.0/24", "fabricMtu": 8978}


def test_settings_body_does_not_modify_current():
    current = {"management": {"replicationMode": "multicast", "multicastGroupSubnet": "239.1.1.0/25"}}
    settings_body(current, {"management": {"replicationMode": "ingress"}})
    assert current["management"]["multicastGroupSubnet"] == "239.1.1.0/25"


def test_live_mode_reads_management_replication_mode():
    assert live_mode({"management": {"replicationMode": "ingress"}}) == "ingress"
    assert live_mode({"management": {}}) is None
    assert live_mode({}) is None


def test_mode_policies():
    assert MODE_POLICIES == {"multicast": ("base_multicast_11_1", "base_pim_asm_v6"), "ingress": ("ingress_rep_simulated",)}
