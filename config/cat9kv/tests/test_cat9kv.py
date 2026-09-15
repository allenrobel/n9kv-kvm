"""Pure parts of the Cat9kv launcher: config loading, interface generation, QEMU command."""

import subprocess
from pathlib import Path

import pytest

from cat9kv import Cat9kvQEMUBuilder, ConfigLoader, GlobalConfig, NetworkInterface, OVSPortManager, SwitchConfig, SwitchVMManager, guest_interface

HERE = Path(__file__).resolve().parents[1]


def _c1_le1() -> SwitchConfig:
    return ConfigLoader.load_switch_config(HERE / "C1_LE1.yaml")


def _globals() -> GlobalConfig:
    return ConfigLoader.load_global_config(HERE / "global_config.yaml")


def test_shipped_yamls_load_with_the_expected_identity():
    c1, c3 = _c1_le1(), ConfigLoader.load_switch_config(HERE / "C3_LE1.yaml")
    assert (c1.sid, c1.mgmt_bridge, c1.mgmt_ip, c1.mgmt_gw) == (1701, "BR_ND_DATA_12", "192.168.12.181/24", "192.168.12.1")
    assert (c3.sid, c3.mgmt_bridge, c3.mgmt_ip, c3.mgmt_gw) == (3701, "BR_ND_DATA_14", "192.168.14.181/24", "192.168.14.1")
    assert (c1.neighbors, c1.isl_bridges, c1.isl_ports) == (["C1_SP1"], ["BR_C1_SP1_LE1_1"], [8])
    assert (c3.neighbors, c3.isl_bridges, c3.isl_ports) == (["C3_SP1"], ["BR_C3_SP1_LE1_1"], [8])
    s1, s3 = ConfigLoader.load_switch_config(HERE / "C1_SP1.yaml"), ConfigLoader.load_switch_config(HERE / "C3_SP1.yaml")
    assert (s1.sid, s1.serial, s1.mgmt_bridge, s1.mgmt_ip, s1.mgmt_gw) == (1702, "CAT9KV1702", "BR_ND_DATA_12", "192.168.12.182/24", "192.168.12.1")
    assert (s3.sid, s3.serial, s3.mgmt_bridge, s3.mgmt_ip, s3.mgmt_gw) == (3702, "CAT9KV3702", "BR_ND_DATA_14", "192.168.14.182/24", "192.168.14.1")
    assert (s1.neighbors, s1.isl_bridges, s1.isl_ports) == (["C1_LE1"], ["BR_C1_SP1_LE1_1"], [1])
    assert (s3.neighbors, s3.isl_bridges, s3.isl_ports) == (["C3_LE1"], ["BR_C3_SP1_LE1_1"], [1])
    assert all(len(b) <= 15 for b in s1.isl_bridges + s3.isl_bridges)  # IFNAMSIZ


def test_serial_and_ports_derive_from_sid():
    cfg = _c1_le1()
    assert cfg.serial == "CAT9KV1701"
    assert cfg.telnet_port == 11701 and cfg.monitor_port == 21701


def test_global_config_carries_the_cat9kv_launch_parameters():
    gcfg = _globals()
    assert gcfg.default_ram == 18432 and gcfg.default_vcpus == 4
    assert gcfg.default_interface_type == "e1000" and gcfg.min_nics == 9
    assert gcfg.image_path == "/iso1/cml/cat9kv-17.15.03" and gcfg.default_image == "cat9kv_prd.17.15.03.qcow2"


def test_guest_interface_names():
    assert guest_interface(0) == "GigabitEthernet0/0"
    assert guest_interface(1) == "GigabitEthernet1/0/1"
    assert guest_interface(8) == "GigabitEthernet1/0/8"


def test_interfaces_are_padded_to_min_nics_with_unattached_taps():
    interfaces = SwitchVMManager(_globals())._generate_interfaces(_c1_le1())  # pylint: disable=protected-access
    assert len(interfaces) == 9
    assert interfaces[0].name == "MGMT" and interfaces[0].bridge == "BR_ND_DATA_12" and interfaces[0].tap == "tap1701-0"
    assert interfaces[0].mac == "52:54:00:11:00:01"
    # C1_LE1 carries a real fabric link on port 8 (GigabitEthernet1/0/8); ports 1-7 stay unattached padding.
    assert all(iface.bridge is None for iface in interfaces[1:8])
    assert interfaces[8].bridge == "BR_C1_SP1_LE1_1" and interfaces[8].name == "FP_8"
    assert [iface.tap for iface in interfaces[1:]] == [f"tap1701-{i}" for i in range(1, 9)]
    assert interfaces[3].mac == "52:54:00:11:03:01"
    assert all(iface.interface_type == "e1000" for iface in interfaces)


def test_isl_bridges_take_the_first_front_panel_slots_before_padding():
    cfg = SwitchConfig(name="X", role="Campus Leaf", sid=1702, mgmt_bridge="BR_ND_DATA_12", neighbors=["A", "B"], isl_bridges=["BR_A", "BR_B"])
    interfaces = SwitchVMManager(_globals())._generate_interfaces(cfg)  # pylint: disable=protected-access
    assert [iface.bridge for iface in interfaces] == ["BR_ND_DATA_12", "BR_A", "BR_B"] + [None] * 6
    assert interfaces[1].name == "FP_1" and interfaces[3].name == "PAD_3"


def test_switch_config_rejects_mismatched_neighbors_and_bad_sid():
    with pytest.raises(ValueError, match="neighbors"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A"], isl_bridges=[])
    with pytest.raises(ValueError, match="SID"):
        SwitchConfig(name="X", role="r", sid=17, mgmt_bridge="B")


def test_qemu_command_matches_the_cml_node_definition():
    gcfg, cfg = _globals(), _c1_le1()
    interfaces = SwitchVMManager(gcfg)._generate_interfaces(cfg)  # pylint: disable=protected-access
    cmd = Cat9kvQEMUBuilder().build_command(cfg, gcfg, interfaces)
    joined = " ".join(cmd)
    assert cmd[0] == "qemu-system-x86_64"
    assert "-machine type=pc,accel=kvm" in joined
    assert "-bios" not in cmd and "ahci" not in joined
    assert "-m 18432" in joined and "-smp 4,sockets=1,cores=4,threads=1" in joined
    assert "file=/iso2/iosxe/config/C1_LE1.qcow2,if=ide,format=qcow2,cache=writethrough" in joined
    assert "file=/iso2/iosxe/config/C1_LE1.iso,media=cdrom" in joined
    assert "-boot order=c" in joined
    assert cmd.count("-serial") == 2 and "-serial telnet:localhost:11701,server=on,wait=off" in joined and "-serial null" in joined
    assert "-monitor telnet:localhost:21701,server,nowait" in joined
    assert cmd.count("-netdev") == 9 and joined.count("e1000,netdev=") == 9
    assert "tap,id=MGMT,ifname=tap1701-0,script=no,downscript=no" in joined
    assert "-name C1_LE1" in joined


def test_isl_ports_default_to_the_first_front_panel_slots():
    cfg = SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A", "B"], isl_bridges=["BR_A", "BR_B"])
    assert cfg.isl_ports == [1, 2]


def test_isl_ports_place_the_link_on_the_named_port_and_pad_the_rest():
    cfg = SwitchConfig(name="X", role="r", sid=1701, mgmt_bridge="BR_ND_DATA_12", neighbors=["C1_SP1"], isl_bridges=["BR_C1_SP1_LE1_1"], isl_ports=[8])
    interfaces = SwitchVMManager(_globals())._generate_interfaces(cfg)  # pylint: disable=protected-access
    assert len(interfaces) == 9
    assert [iface.bridge for iface in interfaces] == ["BR_ND_DATA_12"] + [None] * 7 + ["BR_C1_SP1_LE1_1"]
    assert interfaces[8].name == "FP_8" and interfaces[8].tap == "tap1701-8" and interfaces[8].mac == "52:54:00:11:08:01"
    assert interfaces[1].name == "PAD_1"


def test_isl_ports_beyond_min_nics_grow_the_nic_count():
    cfg = SwitchConfig(name="X", role="r", sid=1701, mgmt_bridge="B", neighbors=["N"], isl_bridges=["BR_X"], isl_ports=[24])
    interfaces = SwitchVMManager(_globals())._generate_interfaces(cfg)  # pylint: disable=protected-access
    assert len(interfaces) == 25 and interfaces[24].bridge == "BR_X" and interfaces[9].bridge is None


def test_isl_ports_must_pair_with_isl_bridges_and_be_unique_front_panel_ports():
    with pytest.raises(ValueError, match="isl_ports"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A"], isl_bridges=["BR_A"], isl_ports=[1, 2])
    with pytest.raises(ValueError, match="isl_ports"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A", "B"], isl_bridges=["BR_A", "BR_B"], isl_ports=[3, 3])
    with pytest.raises(ValueError, match="isl_ports"):
        SwitchConfig(name="X", role="r", sid=1702, mgmt_bridge="B", neighbors=["A"], isl_bridges=["BR_A"], isl_ports=[0])


def test_attach_port_adds_an_existing_tap_to_its_bridge_without_recreating_it(monkeypatch):
    calls = []

    def fake_run(cmd, check=True):  # pylint: disable=unused-argument
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(OVSPortManager, "_run", staticmethod(fake_run))
    OVSPortManager.attach_port(NetworkInterface(name="FP_8", bridge="BR_C1_SP1_LE1_1", mac="m", tap="tap1701-8"))
    assert ["ovs-vsctl", "--may-exist", "add-port", "BR_C1_SP1_LE1_1", "tap1701-8"] in calls
    assert ["ovs-vsctl", "set", "int", "tap1701-8", "mtu_request=9216"] in calls
    assert ["ovs-vsctl", "set", "bridge", "BR_C1_SP1_LE1_1", "other-config:forward-bpdu=true"] in calls
    assert not any("tuntap" in cmd or "del" in cmd for cmd in calls)


def test_attach_port_skips_padding_and_rejects_a_missing_tap(monkeypatch):
    calls = []

    def fake_run(cmd, check=True):  # pylint: disable=unused-argument
        calls.append(cmd)
        rc = 1 if cmd[:3] == ["ip", "link", "show"] else 0
        return subprocess.CompletedProcess(cmd, rc)

    monkeypatch.setattr(OVSPortManager, "_run", staticmethod(fake_run))
    OVSPortManager.attach_port(NetworkInterface(name="PAD_3", bridge=None, mac="m", tap="tap1701-3"))
    assert calls == []
    with pytest.raises(RuntimeError, match="tap1701-8"):
        OVSPortManager.attach_port(NetworkInterface(name="FP_8", bridge="BR_C1_SP1_LE1_1", mac="m", tap="tap1701-8"))
