"""Pure payload builders in provision.py."""

from provision import fabric_create_payload, fabric_group_create_payload, merge_settings
from topology import Fabric, FabricGroup


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
