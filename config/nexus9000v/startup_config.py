#!/usr/bin/env python3
"""Generate NX-OS day-0 startup-config and boot ISO for Nexus9000v switches.

Single source of truth: the per-switch YAML (S*.yaml) that nexus9000v-ovs.py
already reads, plus global_config.yaml. Renders nxos_startup_config.j2 and wraps
the result in a per-switch ISO (genisoimage), byte-compatible with the retired
startup_config_iso.yaml playbook. The admin password is read from $NXOS_PASSWORD.

Usage (ISO build writes to global_config.yaml cdrom_path, usually needs sudo):
    sudo python3 startup_config.py S1_BG1.yaml      # build one ISO
    sudo python3 startup_config.py --all            # build every S*.yaml ISO
    python3 startup_config.py --print S1_BG1.yaml   # render to STDOUT only
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
GLOBAL_CONFIG = HERE / "global_config.yaml"
TEMPLATE = "nxos_startup_config.j2"
DEFAULT_PASSWORD = "SuperSecretPassword"


def load_global(path: Path = GLOBAL_CONFIG) -> dict:
    """Load global_config.yaml."""
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_switch(path: Path) -> dict:
    """Load one per-switch YAML."""
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def derive_interfaces(switch: dict) -> list:
    """Data-plane interfaces to bring up: Ethernet1/1..N for N isl_bridges."""
    count = len(switch.get("isl_bridges") or [])
    return [f"Ethernet1/{i}" for i in range(1, count + 1)]


def render_config(switch: dict, boot_image: str, password: str, env: Environment) -> str:
    """Render the NX-OS startup-config text for one switch."""
    context = {
        "hostname": switch["name"],
        "admin_password": password,
        "boot_image": boot_image,
        "mgmt_ip": switch["mgmt_ip"],
        "mgmt_gw": switch["mgmt_gw"],
        "interfaces": derive_interfaces(switch),
    }
    rendered = env.get_template(TEMPLATE).render(**context)
    return rendered.rstrip("\n") + "\n"


def _iso_tool() -> str:
    for tool in ("genisoimage", "mkisofs"):
        if shutil.which(tool):
            return tool
    raise FileNotFoundError("Neither genisoimage nor mkisofs found; install genisoimage")


def build_iso(config_text: str, hostname: str, out_dir: Path) -> Path:
    """Write config_text as nxos_config.txt and wrap it in <hostname>.iso."""
    out_dir.mkdir(parents=True, exist_ok=True)
    iso_path = out_dir / f"{hostname}.iso"
    tool = _iso_tool()
    with tempfile.TemporaryDirectory() as staging:
        cfg = Path(staging) / "nxos_config.txt"
        cfg.write_text(config_text, encoding="utf-8")
        subprocess.run(
            [tool, "-o", str(iso_path), "-l", "--iso-level", "2", "-V", f"{hostname}_CONFIG", str(cfg)],
            check=True,
        )
    return iso_path


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(HERE)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate NX-OS startup-config / boot ISO.")
    parser.add_argument("yaml", nargs="?", help="Per-switch YAML (e.g. S1_BG1.yaml)")
    parser.add_argument("--all", action="store_true", help="Build ISOs for every S*.yaml in this dir")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Render to STDOUT; build nothing")
    args = parser.parse_args()

    if args.all and args.yaml:
        parser.error("pass either a switch YAML or --all, not both")

    gcfg = load_global()
    boot_image = gcfg["nxos_boot_image"]
    out_dir = Path(gcfg.get("cdrom_path", "/iso2/nxos/config"))
    password = os.environ.get("NXOS_PASSWORD", DEFAULT_PASSWORD)
    env = _env()

    if args.all:
        targets = sorted(HERE.glob("S*.yaml"))
        targets = [t for t in targets if not t.name.endswith(".netplan.yaml")]
    elif args.yaml:
        targets = [Path(args.yaml) if Path(args.yaml).is_absolute() else HERE / args.yaml]
    else:
        parser.error("provide a switch YAML or --all")

    for path in targets:
        switch = load_switch(path)
        text = render_config(switch, boot_image, password, env)
        if args.print_only:
            print(text)
            continue
        iso = build_iso(text, switch["name"], out_dir)
        print(f"Built {iso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
