"""Pure payload builders in provision.py."""

from provision import _switch_password, fabric_create_payload, fabric_group_create_payload, merge_settings, switch_add_payload
from topology import Fabric, FabricGroup, Switch


def test_fabric_create_payload_minimal_and_premier():
    fab = Fabric(name="ISN", type="externalConnectivity", asn="65535")
    assert fabric_create_payload(fab) == {
        "name": "ISN",
        "category": "fabric",
        "licenseTier": "premier",
        "securityDomain": "all",
        "telemetryCollection": False,
        "management": {"type": "externalConnectivity", "bgpAsn": "65535"},
    }


def test_fabric_group_payload():
    grp = FabricGroup(name="MSD", settings={"management": {"multisiteOverlayInterConnectType": "directPeering"}})
    expected = {"name": "MSD", "category": "fabricGroup", "management": {"type": "vxlan", "multisiteOverlayInterConnectType": "directPeering"}}
    assert fabric_group_create_payload(grp) == expected


def test_merge_settings_is_deep_and_non_destructive():
    current = {"name": "SITE1", "management": {"type": "vxlanIbgp", "bgpAsn": "65001", "ptp": False}}
    merged = merge_settings(current, {"management": {"vrfLiteAutoConfig": "back2BackAndToExternal"}})
    assert merged["management"] == {"type": "vxlanIbgp", "bgpAsn": "65001", "ptp": False, "vrfLiteAutoConfig": "back2BackAndToExternal"}
    assert current["management"] == {"type": "vxlanIbgp", "bgpAsn": "65001", "ptp": False}


def test_switch_add_payload_groups_by_platform_and_never_preserves_config():
    fab = Fabric(name="ISN", type="externalConnectivity", asn="65535", switches=[Switch("WAN2", "192.168.14.112", "edgeRouter", "ios-xe")])
    body = switch_add_payload(fab, "pw")  # ggignore: unit-test placeholder, not a credential
    assert body == {
        "switches": [{"ip": "192.168.14.112", "hostname": "WAN2", "switchRole": "edgeRouter"}],
        "platformType": "ios-xe",
        "preserveConfig": False,
        "useCredentialForWrite": True,
        "username": "admin",
        "password": "pw",  # ggignore: unit-test placeholder, not a credential
    }


def test_switch_password_uses_iosxe_for_external_connectivity(monkeypatch):
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-pw")  # ggignore: unit-test placeholder, not a credential
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    fab = Fabric(name="ISN", type="externalConnectivity", asn="65535")
    assert _switch_password(fab) == "iosxe-pw"  # ggignore: unit-test placeholder, not a credential


def test_switch_password_uses_nxos_for_vxlan_fabric(monkeypatch):
    monkeypatch.setenv("IOSXE_PASSWORD", "iosxe-pw")  # ggignore: unit-test placeholder, not a credential
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    fab = Fabric(name="SITE2", type="vxlanIbgp", asn="65002")
    assert _switch_password(fab) == "nxos-pw"  # ggignore: unit-test placeholder, not a credential


def test_switch_password_falls_back_to_nxos_when_iosxe_unset(monkeypatch):
    monkeypatch.delenv("IOSXE_PASSWORD", raising=False)
    monkeypatch.setenv("NXOS_PASSWORD", "nxos-pw")  # ggignore: unit-test placeholder, not a credential
    fab = Fabric(name="ISN", type="externalConnectivity", asn="65535")
    assert _switch_password(fab) == "nxos-pw"  # ggignore: unit-test placeholder, not a credential
