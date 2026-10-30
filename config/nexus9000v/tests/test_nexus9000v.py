"""Disk handling of the Nexus 9000v launcher: --reuse-disk keeps the per-VM qcow2 instead of re-copying the base image."""

import dataclasses
from pathlib import Path

from nexus9000v import ConfigLoader, DiskManager, SwitchVMManager

HERE = Path(__file__).resolve().parents[1]


def _manager(tmp_path: Path, monkeypatch) -> tuple[SwitchVMManager, list]:
    """A manager whose disks live under tmp_path; records create_vm_disk/create_external_storage calls instead of running them."""
    globals_ = dataclasses.replace(ConfigLoader.load_global_config(HERE / "global_config.yaml"), cdrom_path=str(tmp_path))
    calls: list = []
    monkeypatch.setattr(DiskManager, "create_vm_disk", staticmethod(lambda src, dst, size: calls.append(("disk", dst))))
    monkeypatch.setattr(DiskManager, "create_external_storage", staticmethod(lambda path, size: calls.append(("external", path))))
    return SwitchVMManager(globals_), calls


def test_launch_rebuilds_the_disk_by_default_even_when_it_exists(tmp_path, monkeypatch):
    manager, calls = _manager(tmp_path, monkeypatch)
    (tmp_path / "S1_LE1.qcow2").touch()
    manager._prepare_vm_disk(ConfigLoader.load_switch_config(HERE / "S1_LE1.yaml"))  # pylint: disable=protected-access
    assert calls == [("disk", tmp_path / "S1_LE1.qcow2"), ("external", tmp_path / "S1_LE1_external.qcow2")]


def test_reuse_disk_keeps_an_existing_disk_and_leaves_existing_external_storage_alone(tmp_path, monkeypatch, capsys):
    manager, calls = _manager(tmp_path, monkeypatch)
    (tmp_path / "S1_LE1.qcow2").touch()
    (tmp_path / "S1_LE1_external.qcow2").touch()
    manager._prepare_vm_disk(ConfigLoader.load_switch_config(HERE / "S1_LE1.yaml"), reuse_disk=True)  # pylint: disable=protected-access
    assert calls == []
    assert f"Reusing existing disk: {tmp_path / 'S1_LE1.qcow2'}" in capsys.readouterr().out


def test_reuse_disk_falls_back_to_the_base_image_when_no_disk_exists(tmp_path, monkeypatch, capsys):
    manager, calls = _manager(tmp_path, monkeypatch)
    manager._prepare_vm_disk(ConfigLoader.load_switch_config(HERE / "S1_LE1.yaml"), reuse_disk=True)  # pylint: disable=protected-access
    assert calls == [("disk", tmp_path / "S1_LE1.qcow2"), ("external", tmp_path / "S1_LE1_external.qcow2")]
    assert "No existing disk for S1_LE1; creating from base image" in capsys.readouterr().out


def test_create_switch_passes_reuse_disk_through(tmp_path, monkeypatch):
    manager, _ = _manager(tmp_path, monkeypatch)
    seen: list = []
    monkeypatch.setattr(manager.qemu_builder, "_validate_files", lambda config, global_config: None)  # no OVMF/base image on the dev box
    monkeypatch.setattr(manager, "_prepare_vm_disk", lambda config, reuse_disk=False: seen.append(reuse_disk))
    monkeypatch.setattr(manager, "_setup_network", lambda interfaces: None)
    monkeypatch.setattr(manager, "_start_vm", lambda cmd, config, debug=False: type("P", (), {"pid": 1})())
    manager.create_switch(ConfigLoader.load_switch_config(HERE / "S1_LE1.yaml"), reuse_disk=True)
    assert seen == [True]
