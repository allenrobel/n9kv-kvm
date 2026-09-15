"""Day-0 rendering and ISO staging for the Cat9kv (no genisoimage needed: subprocess is stubbed)."""

from pathlib import Path

import pytest

import startup_config
from startup_config import SERIAL_PLACEHOLDER, build_iso, load_yaml, render_config, render_vswitch_xml, serial_for, stage_day0

HERE = Path(__file__).resolve().parents[1]


def test_serial_for_matches_the_launcher_rule():
    assert serial_for({"sid": 1701}) == "CAT9KV1701"
    assert serial_for({"sid": "3701"}) == "CAT9KV3701"


def test_render_config_puts_mgmt_in_mgmt_vrf_with_dotted_mask():
    text = render_config(load_yaml(HERE / "C1_LE1.yaml"), "pw", startup_config._env())  # ggignore: unit-test placeholder, not a credential
    assert text.startswith("hostname C1_LE1\n")
    assert "interface GigabitEthernet0/0\n vrf forwarding Mgmt-vrf\n ip address 192.168.12.181 255.255.255.0\n no cdp enable\n no shutdown\n" in text
    assert "ip route vrf Mgmt-vrf 0.0.0.0 0.0.0.0 192.168.12.1\n" in text
    assert "username admin privilege 15 secret 0 pw\n" in text  # ggignore: unit-test placeholder, not a credential
    assert "line vty 0 15\n login local\n transport input ssh\n" in text
    assert "crypto key generate rsa modulus 2048" in text
    assert "GigabitEthernet1/0/" not in text  # front-panel ports are left at their defaults
    assert text.endswith("end\n")


def test_render_config_disables_cdp_on_the_management_port():
    """ND models a CDP adjacency between two switches' Gi0/0 (same ND data bridge) as a fabric link and then
    un-configures the management IP; the day-0 config must keep CDP off that port."""
    text = render_config(load_yaml(HERE / "C1_LE1.yaml"), "pw", startup_config._env())  # ggignore: unit-test placeholder, not a credential
    block = text.split("interface GigabitEthernet0/0\n", 1)[1].split("!\n", 1)[0]
    assert " no cdp enable\n" in block


def test_render_config_requires_a_prefix_length():
    with pytest.raises(ValueError, match="prefix"):
        switch = {"name": "X", "sid": 1702, "mgmt_ip": "192.168.12.182", "mgmt_gw": "192.168.12.1"}
        render_config(switch, "pw", startup_config._env())  # ggignore: unit-test placeholder, not a credential


def test_render_vswitch_xml_substitutes_only_the_serial():
    original = (HERE / "vswitch.xml").read_text(encoding="utf-8")
    text = render_vswitch_xml("CAT9KV1701")
    assert "<prod_serial_number>CAT9KV1701</prod_serial_number>" in text
    assert SERIAL_PLACEHOLDER not in text
    assert "<port_count>24</port_count>" in text and text.count("<port lpn=") == 24
    assert text.replace("CAT9KV1701", "CMLUADP") == original


def test_render_vswitch_xml_rejects_a_template_without_the_placeholder(tmp_path):
    bad = tmp_path / "vswitch.xml"
    bad.write_text("<switch></switch>", encoding="utf-8")
    with pytest.raises(ValueError, match="prod_serial_number"):
        render_vswitch_xml("CAT9KV1701", bad)


def test_stage_day0_writes_the_two_files_the_image_expects(tmp_path):
    stage_day0("hostname X\nend\n", "<switch/>", tmp_path)
    assert (tmp_path / "iosxe_config.txt").read_text(encoding="utf-8") == "hostname X\nend\n"
    assert (tmp_path / "conf" / "vswitch.xml").read_text(encoding="utf-8") == "<switch/>"


def test_build_iso_labels_the_volume_cdrom_and_uses_rock_ridge_and_joliet(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, check):
        calls.append(cmd)
        assert check is True
        staging = Path(cmd[-1])
        assert (staging / "iosxe_config.txt").exists() and (staging / "conf" / "vswitch.xml").exists()

    monkeypatch.setattr(startup_config.subprocess, "run", fake_run)
    monkeypatch.setattr(startup_config, "_iso_tool", lambda: "genisoimage")
    iso = build_iso("hostname X\nend\n", "<switch/>", "C1_LE1", tmp_path / "out")
    assert iso == tmp_path / "out" / "C1_LE1.iso"
    assert calls == [["genisoimage", "-o", str(iso), "-V", "CDROM", "-r", "-J", calls[0][-1]]]
