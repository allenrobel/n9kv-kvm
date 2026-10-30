"""Disk handling of the Catalyst 8000V launcher: --reuse-disk keeps the per-VM qcow2 instead of re-copying the base image."""

import dataclasses
from pathlib import Path

from importlib import import_module

HERE = Path(__file__).resolve().parents[1]
c8000v = import_module("8000v")  # module name starts with a digit, so it cannot be imported with a plain import statement


def _manager(tmp_path: Path, monkeypatch) -> tuple:
    globals_ = dataclasses.replace(c8000v.ConfigLoader.load_global_config(HERE / "global_config.yaml"), cdrom_path=str(tmp_path))
    calls: list = []
    monkeypatch.setattr(c8000v.DiskManager, "create_vm_disk", staticmethod(lambda src, dst, size: calls.append(dst)))
    return c8000v.RouterVMManager(globals_), calls


def test_launch_rebuilds_the_disk_by_default_even_when_it_exists(tmp_path, monkeypatch):
    manager, calls = _manager(tmp_path, monkeypatch)
    (tmp_path / "WAN1.qcow2").touch()
    manager._prepare_vm_disk(c8000v.ConfigLoader.load_router_config(HERE / "WAN1.yaml"))  # pylint: disable=protected-access
    assert calls == [tmp_path / "WAN1.qcow2"]


def test_reuse_disk_keeps_an_existing_disk(tmp_path, monkeypatch, capsys):
    manager, calls = _manager(tmp_path, monkeypatch)
    (tmp_path / "WAN1.qcow2").touch()
    manager._prepare_vm_disk(c8000v.ConfigLoader.load_router_config(HERE / "WAN1.yaml"), reuse_disk=True)  # pylint: disable=protected-access
    assert calls == []
    assert f"Reusing existing disk: {tmp_path / 'WAN1.qcow2'}" in capsys.readouterr().out


def test_reuse_disk_falls_back_to_the_base_image_when_no_disk_exists(tmp_path, monkeypatch, capsys):
    manager, calls = _manager(tmp_path, monkeypatch)
    manager._prepare_vm_disk(c8000v.ConfigLoader.load_router_config(HERE / "WAN1.yaml"), reuse_disk=True)  # pylint: disable=protected-access
    assert calls == [tmp_path / "WAN1.qcow2"]
    assert "No existing disk for WAN1; creating from base image" in capsys.readouterr().out


def test_create_router_passes_reuse_disk_through(tmp_path, monkeypatch):
    manager, _ = _manager(tmp_path, monkeypatch)
    seen: list = []
    monkeypatch.setattr(manager.qemu_builder, "validate_files", lambda config, global_config: [])
    monkeypatch.setattr(manager, "_prepare_vm_disk", lambda config, reuse_disk=False: seen.append(reuse_disk))
    monkeypatch.setattr(manager, "_setup_network", lambda interfaces: None)
    monkeypatch.setattr(manager, "_start_vm", lambda cmd, config, debug=False: type("P", (), {"pid": 1})())
    manager.create_router(c8000v.ConfigLoader.load_router_config(HERE / "WAN1.yaml"), reuse_disk=True)
    assert seen == [True]
