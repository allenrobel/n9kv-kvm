"""Tests for replication.py: the ingress settings body and the live-mode reader."""

from pathlib import Path

import pytest

import replication

from golden_live import LiveFabric
from replication import MODE_POLICIES, MULTICAST_ONLY_KEYS, fabric_state, live_mode, settings_body
from topology import load

HERE = Path(__file__).resolve().parents[1]


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


def _fabric(setting, policies, pending, name="SITE1"):
    return LiveFabric(name=name, category="fabric", settings={"management": {"replicationMode": setting}}, mode_policies=policies, pending=pending)


@pytest.mark.parametrize(
    "setting, policies, pending, expected",
    [
        ("multicast", {"S1_SP1": {"base_multicast_11_1"}}, {"S1_SP1": 0}, "multicast"),
        ("ingress", {"S1_SP1": {"ingress_rep_simulated"}}, {"S1_SP1": 0}, "ingress"),
        ("ingress", {"S1_SP1": set()}, {"S1_SP1": 0}, "ingress"),  # ToR-like switch, no mode policy at all
        ("ingress", {"S1_SP1": {"base_multicast_11_1"}}, {"S1_SP1": 0}, "mid"),  # setting saved, never deployed
        ("ingress", {"S1_SP1": set()}, {"S1_SP1": 9}, "ingress"),  # pending config is not part of the state (every test run leaves some)
        ("multicast", {"S1_SP1": {"base_multicast_11_1"}}, {"S1_SP1": 9}, "multicast"),
        (None, {"S1_SP1": set()}, {"S1_SP1": 0}, "mid"),  # no setting
        ("bogus", {"S1_SP1": set()}, {"S1_SP1": 0}, "mid"),  # unknown setting
        ("multicast", {"S1_SP1": {"ingress_rep_simulated"}}, {"S1_SP1": 0}, "mid"),
        ("multicast", {"S1_SP1": {"base_pim_asm_v6"}, "S1_LE1": {"ingress_rep_simulated"}}, {"S1_SP1": 0, "S1_LE1": 0}, "mid"),  # one switch lags
    ],
)
def test_fabric_state(setting, policies, pending, expected):
    assert fabric_state(_fabric(setting, policies, pending)) == expected


def test_fabric_state_treats_missing_pending_as_zero():
    assert fabric_state(_fabric("ingress", {"S1_SP1": {"ingress_rep_simulated"}}, None)) == "ingress"


def test_fabric_state_from_a_snapshot_uses_the_setting_alone():
    assert fabric_state(_fabric("ingress", None, None)) == "ingress"
    assert fabric_state(_fabric("bogus", None, None)) == "mid"


def test_testbed_state_is_the_common_fabric_state():
    topo = load(HERE / "topology_nd421.yaml", replication_mode="multicast")
    live = {n: _fabric("ingress", None, None, name=n) for n in topo.mode_fabrics}
    assert replication.testbed_state(topo, live) == "ingress"


def test_testbed_state_is_mid_when_fabrics_disagree():
    topo = load(HERE / "topology_nd421.yaml", replication_mode="multicast")
    assert topo.mode_fabrics == ("SITE1", "SITE2")
    live = {"SITE1": _fabric("ingress", None, None, name="SITE1"), "SITE2": _fabric("multicast", None, None, name="SITE2")}
    assert replication.testbed_state(topo, live) == "mid"


def test_testbed_state_is_mid_when_one_fabric_is_mid():
    topo = load(HERE / "topology_nd421.yaml", replication_mode="multicast")
    live = {"SITE1": _fabric("ingress", {"S1_SP1": {"base_multicast_11_1"}}, {"S1_SP1": 0}), "SITE2": _fabric("ingress", None, None, name="SITE2")}
    assert replication.testbed_state(topo, live) == "mid"
