#!/usr/bin/env python3
"""Generate IOS-XE day-0 config and boot ISO for Catalyst 8000V routers.

Single source of truth: the per-router YAML (e.g. WAN1.yaml) that 8000v.py
already reads, plus global_config.yaml. Renders iosxe_startup_config.j2 and
wraps the result in a per-router ISO (genisoimage) containing iosxe_config.txt,
which the C8000V consumes as day-0 bootstrap config from the cdrom on first
boot. The admin password is read from $IOSXE_PASSWORD, falling back to
$NXOS_PASSWORD; it is an error if neither is set.

Usage (ISO build writes to global_config.yaml cdrom_path, usually needs sudo):
    sudo python3 startup_config.py WAN1.yaml       # build one ISO
    sudo python3 startup_config.py --all           # build every router YAML ISO
    python3 startup_config.py --print WAN1.yaml    # render to STDOUT only
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from ipaddress import IPv4Interface
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
GLOBAL_CONFIG = HERE / "global_config.yaml"
TEMPLATE = "iosxe_startup_config.j2"


def load_yaml(path: Path) -> dict:
    """Load one YAML file."""
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def derive_interfaces(router: dict) -> list:
    """Data-plane interfaces to bring up: GigabitEthernet2..N+1 for N isl_bridges."""
    count = len(router.get("isl_bridges") or [])
    return [f"GigabitEthernet{i}" for i in range(2, count + 2)]


def render_config(router: dict, password: str, env: Environment) -> str:
    """Render the IOS-XE day-0 config text for one router."""
    mgmt_ip = router["mgmt_ip"]
    if "/" not in mgmt_ip:
        raise ValueError(f"{router['name']}: mgmt_ip must include a prefix (e.g. /24), got {mgmt_ip!r}")
    mgmt = IPv4Interface(mgmt_ip)  # IOS-XE wants address + dotted netmask, not CIDR
    context = {
        "hostname": router["name"],
        "admin_password": password,
        "mgmt_ip_addr": str(mgmt.ip),
        "mgmt_netmask": str(mgmt.network.netmask),
        "mgmt_gw": router["mgmt_gw"],
        "interfaces": derive_interfaces(router),
    }
    rendered = env.get_template(TEMPLATE).render(**context)
    return rendered.rstrip("\n") + "\n"


def _iso_tool() -> str:
    for tool in ("genisoimage", "mkisofs"):
        if shutil.which(tool):
            return tool
    raise FileNotFoundError("Neither genisoimage nor mkisofs found; install genisoimage")


def build_iso(config_text: str, hostname: str, out_dir: Path) -> Path:
    """Write config_text as iosxe_config.txt and wrap it in <hostname>.iso."""
    out_dir.mkdir(parents=True, exist_ok=True)
    iso_path = out_dir / f"{hostname}.iso"
    tool = _iso_tool()
    with tempfile.TemporaryDirectory() as staging:
        cfg = Path(staging) / "iosxe_config.txt"
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
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate IOS-XE day-0 config / boot ISO.")
    parser.add_argument("yaml", nargs="?", help="Per-router YAML (e.g. WAN1.yaml)")
    parser.add_argument("--all", action="store_true", help="Build ISOs for every router YAML in this dir")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Render to STDOUT; build nothing")
    args = parser.parse_args()

    if args.all and args.yaml:
        parser.error("pass either a router YAML or --all, not both")

    password = os.environ.get("IOSXE_PASSWORD") or os.environ.get("NXOS_PASSWORD")
    if not password:
        print("Error: set IOSXE_PASSWORD (or NXOS_PASSWORD) in the environment", file=sys.stderr)
        return 1

    gcfg = load_yaml(GLOBAL_CONFIG)
    out_dir = Path(gcfg.get("cdrom_path", "/iso2/iosxe/config"))
    env = _env()

    if args.all:
        targets = sorted(t for t in HERE.glob("*.yaml") if t.name != "global_config.yaml")
    elif args.yaml:
        targets = [Path(args.yaml) if Path(args.yaml).is_absolute() else HERE / args.yaml]
    else:
        parser.error("provide a router YAML or --all")

    failed = False
    for path in targets:
        try:
            router = load_yaml(path)
            text = render_config(router, password, env)
            if args.print_only:
                print(text)
                continue
            iso = build_iso(text, router["name"], out_dir)
            print(f"Built {iso}")
        except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
            print(f"{path.name}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
