"""Generate the IOS-XE day-0 config and boot ISO for Catalyst 9000v switches.

Single source of truth: the per-switch YAML (e.g. C1_LE1.yaml) that cat9kv.py already reads, plus
global_config.yaml. Renders iosxe_startup_config.j2 to iosxe_config.txt, substitutes the switch serial into
vswitch.xml (the ASIC selector the image reads as conf/vswitch.xml), and wraps both in <cdrom_path>/<name>.iso
with volume label CDROM, which the Cat9kv consumes on first boot. The admin password is read from
$IOSXE_PASSWORD, falling back to $NXOS_PASSWORD; it is an error if neither is set.

Usage (ISO build writes to global_config.yaml cdrom_path, usually needs sudo):
    sudo -E python3 startup_config.py C1_LE1.yaml    # build one ISO
    sudo -E python3 startup_config.py --all          # build every switch YAML ISO
    python3 startup_config.py --print C1_LE1.yaml    # render the config to STDOUT only
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
VSWITCH_XML = HERE / "vswitch.xml"
SERIAL_PLACEHOLDER = "<prod_serial_number>CMLUADP</prod_serial_number>"
ISO_VOLUME_LABEL = "CDROM"  # the image looks for this label


def load_yaml(path: Path) -> dict:
    """Load one YAML file."""
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def serial_for(switch: dict) -> str:
    """Serial written into conf/vswitch.xml; must match cat9kv.py's SwitchConfig.serial (CAT9KV<sid>)."""
    return f"CAT9KV{int(switch['sid'])}"


def render_config(switch: dict, password: str, env: Environment) -> str:
    """Render the IOS-XE day-0 config text for one switch."""
    mgmt_ip = switch["mgmt_ip"]
    if "/" not in mgmt_ip:
        raise ValueError(f"{switch['name']}: mgmt_ip must include a prefix (e.g. /24), got {mgmt_ip!r}")
    mgmt = IPv4Interface(mgmt_ip)  # IOS-XE wants address + dotted netmask, not CIDR
    context = {
        "hostname": switch["name"],
        "admin_password": password,
        "mgmt_ip_addr": str(mgmt.ip),
        "mgmt_netmask": str(mgmt.network.netmask),
        "mgmt_gw": switch["mgmt_gw"],
    }
    rendered = env.get_template(TEMPLATE).render(**context)
    return rendered.rstrip("\n") + "\n"


def render_vswitch_xml(serial: str, template_path: Path = VSWITCH_XML) -> str:
    """The committed vswitch.xml with the CML serial placeholder replaced; nothing else (port_count stays 24, as
    Cisco's node definition ships it regardless of NIC count)."""
    text = template_path.read_text(encoding="utf-8")
    if SERIAL_PLACEHOLDER not in text:
        raise ValueError(f"{template_path}: expected the placeholder {SERIAL_PLACEHOLDER}")
    return text.replace(SERIAL_PLACEHOLDER, f"<prod_serial_number>{serial}</prod_serial_number>")


def stage_day0(config_text: str, vswitch_text: str, staging: Path) -> None:
    """Lay out the ISO root: iosxe_config.txt and conf/vswitch.xml."""
    (staging / "conf").mkdir(parents=True, exist_ok=True)
    (staging / "iosxe_config.txt").write_text(config_text, encoding="utf-8")
    (staging / "conf" / "vswitch.xml").write_text(vswitch_text, encoding="utf-8")


def _iso_tool() -> str:
    for tool in ("genisoimage", "mkisofs"):
        if shutil.which(tool):
            return tool
    raise FileNotFoundError("Neither genisoimage nor mkisofs found; install genisoimage")


def build_iso(config_text: str, vswitch_text: str, hostname: str, out_dir: Path) -> Path:
    """Wrap the staged day-0 files in <hostname>.iso (ISO9660 + Rock Ridge + Joliet, volume label CDROM)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    iso_path = out_dir / f"{hostname}.iso"
    tool = _iso_tool()
    with tempfile.TemporaryDirectory() as staging:
        stage_day0(config_text, vswitch_text, Path(staging))
        subprocess.run([tool, "-o", str(iso_path), "-V", ISO_VOLUME_LABEL, "-r", "-J", staging], check=True)
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
    parser = argparse.ArgumentParser(description="Generate the Cat9kv IOS-XE day-0 config / boot ISO.")
    parser.add_argument("yaml", nargs="?", help="Per-switch YAML (e.g. C1_LE1.yaml)")
    parser.add_argument("--all", action="store_true", help="Build ISOs for every switch YAML in this dir")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Render to STDOUT; build nothing")
    args = parser.parse_args()

    if args.all and args.yaml:
        parser.error("pass either a switch YAML or --all, not both")

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
        parser.error("provide a switch YAML or --all")

    failed = False
    for path in targets:
        try:
            switch = load_yaml(path)
            text = render_config(switch, password, env)
            if args.print_only:
                print(text)
                continue
            iso = build_iso(text, render_vswitch_xml(serial_for(switch)), switch["name"], out_dir)
            print(f"Built {iso} (serial {serial_for(switch)})")
        except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
            print(f"{path.name}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
