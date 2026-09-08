# ND 4.3.1 Mirror Testbed (SITE3/SITE4 + WAN2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define, wire and bring up an exact mirror of the ND 4.2.1 testbed (SITE1/SITE2/ISN/MSD, WAN1, S1_H1/S2_H1) as SITE3/SITE4 + WAN2 + S3_H1/S4_H1 under
ND 4.3.1.175, and turn the ND-side provisioning that today lives in memory and the `provision-isn` skill into a repo tool that can target either controller.

**Architecture:** Day-0 stays what it is: one YAML per VM under `config/nexus9000v/` and `config/8000v/` (launcher + ISO generator read the same file), OVS bridges
from netplan, libvirt-LXC host containers from `config/containers/`. The new part is `config/nd/provision/`: a small `requests`-based ND client, a read-only
`snapshot.py` (dump + diff), a declarative topology file per controller, and an idempotent phased `provision.py`. The testbeds share only the
host: ND 4.2.1 manages over `BR_ND_DATA_12`, ND 4.3.1 over `BR_ND_DATA_14`.

**Tech Stack:** Python 3.13 (`uv`, `requests`, `pyyaml`, `pytest` new dev dep), netplan + Open vSwitch, bash one-liners, NX-OS 10.6(2), IOS-XE 17.15.05, ND REST
`/api/v1/manage`.

**Spec:** `docs/superpowers/specs/2026-09-08-nd431-mirror-testbed-design.md` (decisions D1-D6 are binding; the address table in D2 and link table in D4 are copied
below verbatim).

## Global Constraints

- Management segment for every new device: `BR_ND_DATA_14`, 192.168.14.0/24, gateway `192.168.14.1` (spec D1). ND 4.3.1 is re-instantiated there (runbook R0).
- Addresses (spec D2): every mirror device = its counterpart's address with `192.168.12.` -> `192.168.14.`: S3_BG1 `.131`, S3_SP1 `.141`, S3_LE1 `.151`,
  S3_LE2 `.152`, S3_LE3 `.154`, S3_LE4 `.155`, S3_TOR1 `.161`, S3_H1 `.171`, S4_BG1 `.132`, S4_SP1 `.142`, S4_LE1 `.153`, S4_H1 `.172`, WAN2 `.112`.
  Container test-net addresses stay 192.0.1.171/.172 (separate overlay); container MACs are `00:00:73/74:...` (spec D2).
- sids: S3_BG1 3301, S3_SP1 3401, S3_LE1 3501, S3_LE2 3502, S3_LE3 3503, S3_LE4 3504, S3_TOR1 3601, S4_BG1 4301, S4_SP1 4401, S4_LE1 4501, WAN2 9102.
  Console = 10000+sid, monitor = 20000+sid. `sid` must be unique across `config/nexus9000v/*.yaml` and `config/8000v/*.yaml` (MACs derive from it).
- Bridge names <= 15 chars; intra-site `BR_S<site>_<upper>_<lower>_<n>`, `TOR` -> `T` in bridge names only; cross-site `BR_ISN_S<a>_S<b>_<n>`, WAN `BR_ISN_WAN_S<x>_1`.
- `isl_bridges` order == `Ethernet1/N` order; copy position-for-position from the S1/S2 file being mirrored. `len(neighbors) == len(isl_bridges)` is enforced.
- Fabric names/ASNs/pools/VNIs on ND 4.3.1 are identical to ND 4.2.1 (spec D3). Only hostnames and mgmt IPs differ between `topology_nd421.yaml` and
  `topology_nd431.yaml`; `diff` of the two files must show nothing else.
- Line length 169 (`black`, `flake8`, `pylint`, `pymarkdown` are all configured). Validate Python with `mypy` + `flake8` + `black --check`; Markdown with
  `pymarkdown scan`.
- `env_prod/` is never staged or committed. Credentials come only from the environment (`ND_IP4`, `ND_USERNAME`, `ND_PASSWORD`, `ND_DOMAIN`, `NXOS_PASSWORD`,
  `IOSXE_PASSWORD`).
- Work on branch `nd431-mirror-testbed` off `main`; finish with one PR covering Tasks 1-13 (never push to `main`).
- Host is `glide-wired.laukapu.com` (replaces `glide`). `sudo` there needs a password; `virsh -c qemu:///system` and `ip`/`ps` do not.
- No test suite exists today. This plan adds the first one (`config/nd/provision/tests/`, pytest) for the pure functions of the provisioning tool only.

## File map

| Path | Action | Responsibility |
|------|--------|----------------|
| `config/bridges/netplan/9914-bridges.yaml` | rewrite | SITE3/SITE4 data bridges (16) + `Vlan14`/`BR_ND_DATA_14` (mgmt) |
| `config/nd/nd-4-3-1-175-node1.sh` | modify | `ND_DATA_NET=BR_ND_DATA_14` |
| `config/bridges/bridges_config_ovs.sh`, `bridges_down.sh` | modify | add the SITE3/SITE4 bridge set |
| `monitor/show_bridges_stats_s34` | modify | new bridge list |
| `config/nexus9000v/S3_*.yaml` (7), `S4_*.yaml` (3) | rewrite/create | per-switch SoT for launcher + ISO |
| `config/nexus9000v/S4_LE2.yaml`, `S4_LE3.yaml` | delete | not in the mirrored topology |
| `config/nexus9000v/con_s3_*`, `ssh_s3_*`, `con_s4_*`, `ssh_s4_*`, `site3.sh`, `site4.sh` | create/update | helpers |
| `config/8000v/WAN2.yaml`, `con_wan2`, `ssh_wan2` | create | second WAN router |
| `config/containers/container_configs_*.yaml`, `S3_H1.netplan.yaml`, `S4_H1.netplan.yaml`, `README.md` | modify/create | host containers |
| `config/ansible/dynamic_inventory.py` | modify | S3/S4 IPs, hostnames, interfaces; ND 4.3.1 host group |
| `config/nd/provision/nd_client.py` | create | login/cookie session, GET/POST/PUT, paging |
| `config/nd/provision/snapshot.py` | create | read-only dump of an ND; normalized diff of two dumps |
| `config/nd/provision/topology.py` | create | load + validate topology YAML into dataclasses |
| `config/nd/provision/provision.py` | create | phased idempotent provisioning with `--dry-run` |
| `config/nd/provision/topology_nd421.yaml`, `topology_nd431.yaml` | create | declarative testbed definitions |
| `config/nd/provision/tests/` | create | pytest for loaders, normalizer, payload builders |
| `config/nd/provision/README.md`, `README.md`, `CLAUDE.md`, `docs/bridges.md`, `docs/nd4_fabrics_bringup.md` | modify | docs |

---

### Task 1: ND client + read-only snapshot tool; capture the ND 4.2.1 baseline

**Files:**

- Create: `config/nd/provision/nd_client.py`
- Create: `config/nd/provision/snapshot.py`
- Create: `config/nd/provision/tests/conftest.py`, `config/nd/provision/tests/test_snapshot.py`
- Modify: `pyproject.toml` (add `pytest` dev dependency via `uv`)

**Interfaces:**

- Consumes: env vars `ND_IP4`, `ND_USERNAME`, `ND_PASSWORD`, `ND_DOMAIN` (default `DefaultAuth`).
- Produces: `NDCredentials.from_env(ip: str | None) -> NDCredentials`; `NDClient(creds).login()`, `.get(path, params=None) -> Any`, `.post(path, json=None) -> Any`,
  `.put(path, json) -> Any`, `.paged(path, key, params=None, page=100) -> list[dict]`; `snapshot.dump(client, out_dir: Path) -> None`;
  `snapshot.normalize(obj, name_map: dict[str, str]) -> Any`; CLI `snapshot.py dump <dir>` and `snapshot.py diff <dirA> <dirB> --map A=B ...`.
  Later tasks import `NDClient`, `NDCredentials` from `nd_client` and `normalize` from `snapshot`.

- [ ] **Step 1: Branch and dev dependency**

```bash
cd ~/repos/n9kv-kvm && git checkout main && git pull --ff-only && git checkout -b nd431-mirror-testbed
uv add --dev pytest
mkdir -p config/nd/provision/tests
```

- [ ] **Step 2: Write the failing test for the diff normalizer**

`config/nd/provision/tests/conftest.py`:

```python
"""Make the provision package importable without installing it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

`config/nd/provision/tests/test_snapshot.py`:

```python
"""Tests for snapshot.normalize: hostname mapping, volatile-key stripping, stable list order."""
from snapshot import normalize


def test_normalize_maps_hostnames_and_drops_volatile_keys():
    src = {
        "switches": [
            {"hostname": "S2_BG1", "serialNumber": "9ABC", "fabricManagementIp": "192.168.12.132", "switchRole": "borderGateway"},
            {"hostname": "S1_BG1", "serialNumber": "9DEF", "fabricManagementIp": "192.168.12.131", "switchRole": "borderGateway"},
        ],
        "meta": {"counts": {"total": 2}},
    }
    out = normalize(src, {"S1_BG1": "S3_BG1", "S2_BG1": "S4_BG1"})
    assert out == {"switches": [{"hostname": "S3_BG1", "switchRole": "borderGateway"}, {"hostname": "S4_BG1", "switchRole": "borderGateway"}]}


def test_normalize_rewrites_names_embedded_in_strings():
    out = normalize({"description": "connected-to-S1_BG1-Ethernet1/3", "source": "LINK-UUID-7850"}, {"S1_BG1": "S3_BG1"})
    assert out == {"description": "connected-to-S3_BG1-Ethernet1/3"}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest config/nd/provision/tests -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'snapshot'`.

- [ ] **Step 4: Write `nd_client.py`**

```python
#!/usr/bin/env python3
"""Minimal Nexus Dashboard REST client for lab provisioning (cookie auth, self-signed certs).

Credentials come from the environment only (source env_prod/env.sh on the lab host):
ND_IP4, ND_USERNAME, ND_PASSWORD, ND_DOMAIN (default DefaultAuth).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass(frozen=True)
class NDCredentials:
    """Where and how to log in."""

    ip: str
    username: str
    password: str
    domain: str = "DefaultAuth"

    @classmethod
    def from_env(cls, ip: Optional[str] = None) -> "NDCredentials":
        env = os.environ
        try:
            return cls(ip=ip or env["ND_IP4"], username=env["ND_USERNAME"], password=env["ND_PASSWORD"], domain=env.get("ND_DOMAIN", "DefaultAuth"))
        except KeyError as exc:
            raise SystemExit(f"missing environment variable {exc}; source env_prod/env.sh first") from exc


class NDClient:
    """Thin wrapper around requests.Session for /api/v1/manage."""

    BASE = "/api/v1/manage"

    def __init__(self, creds: NDCredentials, timeout: int = 60) -> None:
        self.creds = creds
        self.timeout = timeout
        self.url = f"https://{creds.ip}"
        self.session = requests.Session()
        self.session.verify = False

    def login(self) -> None:
        body = {"userName": self.creds.username, "userPasswd": self.creds.password, "domain": self.creds.domain}
        resp = self.session.post(f"{self.url}/login", json=body, timeout=self.timeout)
        if resp.status_code != 200:
            raise SystemExit(f"ND login to {self.creds.ip} failed: HTTP {resp.status_code} {resp.text[:200]}")

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{self.url}{self.BASE}{path}"
        return self.session.request(method, url, timeout=self.timeout, **kwargs)

    def _json(self, resp: requests.Response, path: str) -> Any:
        if resp.status_code >= 400:
            raise RuntimeError(f"{resp.request.method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json() if resp.content else None

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        return self._json(self.request("GET", path, params=params), path)

    def post(self, path: str, json: Any = None) -> Any:
        return self._json(self.request("POST", path, json=json), path)

    def put(self, path: str, json: Any) -> Any:
        return self._json(self.request("PUT", path, json=json), path)

    def delete(self, path: str) -> Any:
        return self._json(self.request("DELETE", path), path)

    def paged(self, path: str, key: str, params: Optional[dict] = None, page: int = 100) -> list:
        """Walk offset/max pagination. ND silently pages some lists (policies) at 10; never trust one read."""
        items: list = []
        offset = 0
        while True:
            query = dict(params or {}, offset=offset, max=page)
            body = self.get(path, params=query) or {}
            chunk = body.get(key, []) if isinstance(body, dict) else body
            items.extend(chunk)
            total = (body.get("meta", {}).get("counts", {}) or {}).get("total") if isinstance(body, dict) else None
            if len(chunk) < page or (total is not None and len(items) >= total):
                return items
            offset += page
```

- [ ] **Step 5: Write `snapshot.py`**

```python
#!/usr/bin/env python3
"""Read-only dump of a Nexus Dashboard's fabric state, and a normalized diff of two dumps.

    snapshot.py dump <out_dir> [--nd-ip IP]
    snapshot.py diff <dir_a> <dir_b> [--map S1_BG1=S3_BG1 ...]

`dump` writes one JSON file per object type per fabric. `diff` rewrites hostnames per --map, strips
volatile fields (serials, IPs, UUIDs, timestamps, counters), sorts lists, then prints a unified diff.
An empty diff is the mechanical proof that two testbeds mirror each other.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any

from nd_client import NDClient, NDCredentials

VOLATILE_KEYS = {
    "serialNumber", "switchId", "srcSwitchId", "dstSwitchId", "switchIds", "fabricManagementIp", "ipAddress", "ip", "mgmtIp",
    "systemUpTime", "id", "uuid", "linkId", "policyId", "source", "meta", "createdOn", "modifiedOn", "lastModified", "timestamp",
    "additionalData", "anomalyLevel", "advisoryLevel", "networkStatus", "vrfStatus", "vpcData", "softwareVersion", "model",
}


def normalize(obj: Any, name_map: dict[str, str]) -> Any:
    """Return obj with hostnames rewritten, volatile keys removed and lists of dicts sorted deterministically."""
    if isinstance(obj, dict):
        return {k: normalize(v, name_map) for k, v in sorted(obj.items()) if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        items = [normalize(v, name_map) for v in obj]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(obj, str):
        for old, new in name_map.items():
            obj = re.sub(rf"\b{re.escape(old)}\b", new, obj)
        return obj
    return obj


def _write(out_dir: Path, name: str, data: Any) -> None:
    (out_dir / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump(client: NDClient, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fabrics = client.get("/fabrics") or {}
    _write(out_dir, "fabrics", fabrics)
    _write(out_dir, "inventory_switches", client.get("/inventory/switches"))
    for fabric in fabrics.get("fabrics", []):
        name = fabric["name"]
        _write(out_dir, f"fabric_{name}", client.get(f"/fabrics/{name}"))
        switches = client.get(f"/fabrics/{name}/switches") or {}
        _write(out_dir, f"switches_{name}", switches)
        _write(out_dir, f"members_{name}", client.get(f"/fabrics/{name}/members"))
        _write(out_dir, f"links_{name}", client.paged("/links", "links", params={"fabricName": name}))
        _write(out_dir, f"policies_{name}", client.paged(f"/fabrics/{name}/policies", "policies"))
        _write(out_dir, f"vrfs_{name}", client.get(f"/fabrics/{name}/vrfs"))
        _write(out_dir, f"networks_{name}", client.get(f"/fabrics/{name}/networks"))
        serials = [s["serialNumber"] for s in switches.get("switches", [])]
        if serials:
            _write(out_dir, f"vrf_attachments_{name}", client.post(f"/fabrics/{name}/vrfAttachments/query", json={"switchIds": serials}))
            _write(out_dir, f"network_attachments_{name}", client.post(f"/fabrics/{name}/networkAttachments/query", json={"switchIds": serials}))
        for switch in switches.get("switches", []):
            _write(out_dir, f"interfaces_{name}_{switch['hostname']}", client.get(f"/fabrics/{name}/switches/{switch['serialNumber']}/interfaces"))
    print(f"snapshot written to {out_dir}")


def diff(dir_a: Path, dir_b: Path, name_map: dict[str, str]) -> int:
    """Print a unified diff of normalized JSON for every file present in dir_a; return 1 if any differ."""
    rc = 0
    for file_a in sorted(dir_a.glob("*.json")):
        mapped_name = normalize(file_a.name, name_map)
        file_b = dir_b / mapped_name
        if not file_b.exists():
            print(f"--- only in {dir_a}: {file_a.name}")
            rc = 1
            continue
        text_a = json.dumps(normalize(json.loads(file_a.read_text()), name_map), indent=1, sort_keys=True).splitlines()
        text_b = json.dumps(normalize(json.loads(file_b.read_text()), {}), indent=1, sort_keys=True).splitlines()
        lines = list(difflib.unified_diff(text_a, text_b, fromfile=str(file_a), tofile=str(file_b), lineterm=""))
        if lines:
            rc = 1
            print("\n".join(lines))
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_dump = sub.add_parser("dump")
    p_dump.add_argument("out_dir", type=Path)
    p_dump.add_argument("--nd-ip", help="override ND_IP4")
    p_diff = sub.add_parser("diff")
    p_diff.add_argument("dir_a", type=Path)
    p_diff.add_argument("dir_b", type=Path)
    p_diff.add_argument("--map", action="append", default=[], help="OLD=NEW hostname mapping applied to dir_a (repeatable)")
    args = parser.parse_args()
    if args.cmd == "dump":
        client = NDClient(NDCredentials.from_env(args.nd_ip))
        client.login()
        dump(client, args.out_dir)
        return 0
    name_map = dict(item.split("=", 1) for item in args.map)
    return diff(args.dir_a, args.dir_b, name_map)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the tests and linters**

```bash
uv run pytest config/nd/provision/tests -q
flake8 config/nd/provision && mypy config/nd/provision/nd_client.py config/nd/provision/snapshot.py && black --check config/nd/provision
```

Expected: `2 passed`; linters silent.

- [ ] **Step 7: Capture the ND 4.2.1 baseline (on the host; needs the prod credentials, so the user runs it)**

```bash
ssh glide-wired.laukapu.com
cd ~/repos/n9kv-kvm && git fetch && git checkout nd431-mirror-testbed
source env_prod/env.sh
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421 --nd-ip 10.10.20.10
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431 --nd-ip 10.10.20.20     # expected: fabrics.json with an empty list
ls ~/tmp/snap_nd421
```

Expected: files for fabrics SITE1, SITE2, ISN, MSD. Keep `~/tmp/snap_nd421` on the host; Task 8 transcribes from it. Do not commit the dump (serials, IPs).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock config/nd/provision/nd_client.py config/nd/provision/snapshot.py config/nd/provision/tests
git commit -m "Add ND REST client and read-only fabric snapshot/diff tool"
```

---

### Task 2: SITE3/SITE4 bridges (netplan, OVS scripts, monitor)

**Files:**

- Rewrite: `config/bridges/netplan/9914-bridges.yaml`
- Modify: `config/bridges/bridges_config_ovs.sh:22-40` (`BRIDGES` array), `config/bridges/bridges_down.sh:5-21`
- Modify: `monitor/show_bridges_stats_s34:9`
- Modify: `docs/bridges.md` (mention 9914)

**Interfaces:**

- Produces the 16 bridge names of spec D4 (every later YAML references them verbatim):
  `BR_ISN_S3_S4_1 BR_S3_BG1_SP1_1 BR_S4_BG1_SP1_1 BR_ISN_WAN_S3_1 BR_ISN_WAN_S4_1 BR_S3_SP1_LE1_1 BR_S3_SP1_LE2_1 BR_S3_SP1_LE3_1 BR_S3_SP1_LE4_1 BR_S3_LE1_LE2_1
  BR_S3_LE3_LE4_1 BR_S3_LE1_T1_1 BR_S3_LE2_T1_1 BR_S3_T1_H1_1 BR_S4_SP1_LE1_1 BR_S4_LE1_H1_1`.

- [ ] **Step 1: Rewrite `9914-bridges.yaml`**

Header comment, then one stanza per bridge (identical shape to `9912-bridges.yaml`), then the unchanged `BR_ND_DATA_14` management stanza:

```yaml
# SITE3/SITE4 data-plane bridges: the ND 4.3.1 mirror of SITE1/SITE2 (see 9912-bridges.yaml).
#
# Management for ND 4.3.1, S3_*/S4_*, WAN2 and S3_H1/S4_H1 is BR_ND_DATA_14 (Vlan14, 192.168.14.0/24,
# host 192.168.14.2, gateway 192.168.14.1) -- the 192.168.14.x twin of BR_ND_DATA_12 in 9912-bridges.yaml.
#
# Copy to /etc/netplan/9914-bridges.yaml on the target system.
# sudo cp $HOME/repos/n9kv-kvm/config/bridges/netplan/9914-bridges.yaml /etc/netplan/9914-bridges.yaml
# sudo chmod 600 /etc/netplan/9914-bridges.yaml
# sudo netplan try
# sudo netplan apply
#
# Src Interface           Dst Interface           Bridge            Mirror of
# S3_BG1_INTERFACE_1      S4_BG1_INTERFACE_1      BR_ISN_S3_S4_1    BR_ISN_S1_S2_1   (cross-site MSD)
# S3_BG1_INTERFACE_2      S3_SP1_INTERFACE_1      BR_S3_BG1_SP1_1   BR_S1_BG1_SP1_1
# S4_BG1_INTERFACE_2      S4_SP1_INTERFACE_1      BR_S4_BG1_SP1_1   BR_S2_BG1_SP1_1
# S3_SP1_INTERFACE_2      S3_LE1_INTERFACE_1      BR_S3_SP1_LE1_1   BR_S1_SP1_LE1_1
# S4_SP1_INTERFACE_2      S4_LE1_INTERFACE_1      BR_S4_SP1_LE1_1   BR_S2_SP1_LE1_1
# S3_TOR1_INTERFACE_3     S3_H1_INTERFACE_1       BR_S3_T1_H1_1     BR_S1_T1_H1_1
# S4_LE1_INTERFACE_2      S4_H1_INTERFACE_1       BR_S4_LE1_H1_1    BR_S2_LE1_H1_1
# S3_SP1_INTERFACE_3      S3_LE2_INTERFACE_1      BR_S3_SP1_LE2_1   BR_S1_SP1_LE2_1
# S3_LE1_INTERFACE_2      S3_LE2_INTERFACE_2      BR_S3_LE1_LE2_1   BR_S1_LE1_LE2_1  (VPC peer-link)
# S3_LE1_INTERFACE_3      S3_TOR1_INTERFACE_1     BR_S3_LE1_T1_1    BR_S1_LE1_T1_1
# S3_LE2_INTERFACE_3      S3_TOR1_INTERFACE_2     BR_S3_LE2_T1_1    BR_S1_LE2_T1_1
# S3_SP1_INTERFACE_4      S3_LE3_INTERFACE_1      BR_S3_SP1_LE3_1   BR_S1_SP1_LE3_1
# S3_SP1_INTERFACE_5      S3_LE4_INTERFACE_1      BR_S3_SP1_LE4_1   BR_S1_SP1_LE4_1
# S3_LE3_INTERFACE_2      S3_LE4_INTERFACE_2      BR_S3_LE3_LE4_1   BR_S1_LE3_LE4_1  (VPC peer-link)
# WAN2_INTERFACE_2        S3_BG1_INTERFACE_3      BR_ISN_WAN_S3_1   BR_ISN_WAN_S1_1  (C8000V WAN/ISN router)
# WAN2_INTERFACE_3        S4_BG1_INTERFACE_3      BR_ISN_WAN_S4_1   BR_ISN_WAN_S2_1  (C8000V WAN/ISN router)
# All mgmt0                                       BR_ND_DATA_14

network:
  version: 2
  renderer: networkd
  vlans:
    Vlan14:
      id: 14
      link: eno6
      optional: true
  bridges:
    BR_ISN_S3_S4_1:
      openvswitch: {}
      dhcp4: false
      dhcp6: false
      mtu: 9216
      accept-ra: false
      parameters:
        stp: false
      interfaces: []
```

Repeat that exact stanza for each of the other 15 names in the Interfaces list above (same 8 lines, only the key changes), then close the file with the
management stanza copied unchanged from the current file:

```yaml
    BR_ND_DATA_14:
      openvswitch: {}
      interfaces:
      - Vlan14
      addresses:
      - 192.168.14.2/24
      - 2000:192:168:14::2/24
      parameters:
        stp: false
```

- [ ] **Step 2: Verify the netplan file**

```bash
python3 -c "import yaml,sys; d=yaml.safe_load(open('config/bridges/netplan/9914-bridges.yaml')); b=d['network']['bridges']; print(len(b)); \
bad=[n for n in b if len(n)>15]; assert not bad, bad; assert 'BR_S4_LE2_H2_1' not in b"
```

Expected: `17` (16 data bridges + `BR_ND_DATA_14`), no assertion.

- [ ] **Step 3: Extend `bridges_config_ovs.sh` and `bridges_down.sh`**

In `bridges_config_ovs.sh`, after the `BR_ISN_WAN_S2_1` line of the `BRIDGES` array, add a comment and the 16 names:

```bash
    # SITE3/SITE4 mirror (canonical, from 9914-bridges.yaml); BR_ND_DATA_14 is their management bridge.
    BR_ND_DATA_14
    BR_ISN_S3_S4_1
    BR_S3_BG1_SP1_1
    BR_S4_BG1_SP1_1
    BR_S3_SP1_LE1_1
    BR_S3_SP1_LE2_1
    BR_S3_SP1_LE3_1
    BR_S3_SP1_LE4_1
    BR_S3_LE1_LE2_1
    BR_S3_LE3_LE4_1
    BR_S3_LE1_T1_1
    BR_S3_LE2_T1_1
    BR_S3_T1_H1_1
    BR_S4_SP1_LE1_1
    BR_S4_LE1_H1_1
    BR_ISN_WAN_S3_1
    BR_ISN_WAN_S4_1
```

Change the header comment `# SITE1/SITE2 bridges (canonical, from 9912-bridges.yaml).` to `# SITE1/SITE2 bridges (canonical, from 9912-bridges.yaml) followed by
SITE3/SITE4.`. Apply the same 16-name block to `bridges_down.sh` and change its two "SITE1/SITE2" strings to "SITE1-SITE4".

- [ ] **Step 4: Update the monitor list and the bridges doc**

`monitor/show_bridges_stats_s34` line 9 becomes:

```bash
export BRIDGES="BR_ISN_S3_S4_1 BR_S3_BG1_SP1_1 BR_S4_BG1_SP1_1 BR_S3_SP1_LE1_1 BR_S3_SP1_LE2_1 BR_S3_SP1_LE3_1 BR_S3_SP1_LE4_1 BR_S3_LE1_LE2_1 \
BR_S3_LE3_LE4_1 BR_S3_LE1_T1_1 BR_S3_LE2_T1_1 BR_S3_T1_H1_1 BR_S4_SP1_LE1_1 BR_S4_LE1_H1_1 BR_ISN_WAN_S3_1 BR_ISN_WAN_S4_1"
```

In `docs/bridges.md`, after the netplan bullet, add:

```markdown
- **`9914-bridges.yaml`** carries the SITE3/SITE4 bridges for the ND 4.3.1 mirror testbed. Install it the same way; its
  switches, WAN2, containers and ND 4.3.1 itself manage over its `BR_ND_DATA_14` (`Vlan14`, 192.168.14.2/24).
```

- [ ] **Step 5: Point the ND 4.3.1 install script at `BR_ND_DATA_14`**

In `config/nd/nd-4-3-1-175-node1.sh` change `ND_DATA_NET=BR_ND_DATA_12` to `ND_DATA_NET=BR_ND_DATA_14` and add the comment
`# ND 4.3.1 testbed: data on Vlan14 (192.168.14.0/24); persistent data IPs 192.168.14.30-.32, persistent mgmt 10.10.20.60-.62` above it.

- [ ] **Step 6: Verify and commit**

```bash
bash -n config/nd/nd-4-3-1-175-node1.sh && grep -q 'ND_DATA_NET=BR_ND_DATA_14' config/nd/nd-4-3-1-175-node1.sh && echo ND_SCRIPT_OK
bash -n config/bridges/bridges_config_ovs.sh config/bridges/bridges_down.sh monitor/show_bridges_stats_s34
grep -c 'BR_' config/bridges/bridges_config_ovs.sh   # expected 35 (17 + 17 + header mention)
pymarkdown scan docs/bridges.md
git add config/bridges monitor/show_bridges_stats_s34 docs/bridges.md config/nd/nd-4-3-1-175-node1.sh
git commit -m "Define SITE3/SITE4 mirror bridges on BR_ND_DATA_14; drop S4_LE2/S4_LE3/H2 bridges"
```

---

### Task 3: SITE3 switch definitions, helpers and launch script

**Files:**

- Rewrite: `config/nexus9000v/S3_BG1.yaml`, `S3_SP1.yaml`, `S3_LE1.yaml`
- Create: `config/nexus9000v/S3_LE2.yaml`, `S3_LE3.yaml`, `S3_LE4.yaml`, `S3_TOR1.yaml`
- Modify: `config/nexus9000v/con_s3_le1` (unchanged, 13501), `ssh_s3_le1` (new IP)
- Create: `con_s3_bg1 con_s3_sp1 con_s3_le2 con_s3_le3 con_s3_le4 con_s3_tor1 ssh_s3_bg1 ssh_s3_sp1 ssh_s3_le2 ssh_s3_le3 ssh_s3_le4 ssh_s3_tor1 site3.sh`

**Interfaces:**

- Consumes: bridge names from Task 2.
- Produces: hostnames `S3_BG1 S3_SP1 S3_LE1 S3_LE2 S3_LE3 S3_LE4 S3_TOR1` with the IPs in Global Constraints; Tasks 7 and 8 use them verbatim.

- [ ] **Step 1: Write the seven YAMLs** (each is the S1 file with `S1`->`S3`, `S2`->`S4`, `WAN1`->`WAN2`, sid `1xxx`->`3xxx`, new mgmt IP)

`S3_BG1.yaml`:

```yaml
---
# SITE3 (ND 4.3.1 mirror of SITE1)
# S3_BG1.yaml - Border Gateway 1 in SITE3 (mirror of S1_BG1)
name: S3_BG1
role: Border Gateway
sid: 3301
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.131/24
mgmt_gw: 192.168.12.1
neighbors:
  - S4_BG1
  - S3_SP1
  - WAN2
isl_bridges:
  - BR_ISN_S3_S4_1
  - BR_S3_BG1_SP1_1
  - BR_ISN_WAN_S3_1
```

`S3_SP1.yaml`:

```yaml
---
# SITE3 (ND 4.3.1 mirror of SITE1)
# S3_SP1.yaml - Spine Switch 1 in SITE3 (mirror of S1_SP1)
name: S3_SP1
role: Spine Switch
sid: 3401
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.141/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_BG1
  - S3_LE1
  - S3_LE2
  - S3_LE3
  - S3_LE4
isl_bridges:
  - BR_S3_BG1_SP1_1
  - BR_S3_SP1_LE1_1
  - BR_S3_SP1_LE2_1
  - BR_S3_SP1_LE3_1
  - BR_S3_SP1_LE4_1
```

`S3_LE1.yaml`:

```yaml
---
# SITE3 (ND 4.3.1 mirror of SITE1)
# S3_LE1.yaml - Leaf Switch 1 in SITE3 (VPC pair member with S3_LE2; uplink to S3_TOR1; mirror of S1_LE1)
name: S3_LE1
role: Leaf Switch
sid: 3501
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.151/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_SP1
  - S3_LE2
  - S3_TOR1
isl_bridges:
  - BR_S3_SP1_LE1_1
  - BR_S3_LE1_LE2_1
  - BR_S3_LE1_T1_1
```

`S3_LE2.yaml`:

```yaml
---
# SITE3 (ND 4.3.1 mirror of SITE1)
# S3_LE2.yaml - Leaf Switch 2 in SITE3 (VPC pair member with S3_LE1; downstream of S3_TOR1; mirror of S1_LE2)
name: S3_LE2
role: Leaf Switch
sid: 3502
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.152/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_SP1
  - S3_LE1
  - S3_TOR1
isl_bridges:
  - BR_S3_SP1_LE2_1
  - BR_S3_LE1_LE2_1
  - BR_S3_LE2_T1_1
```

`S3_LE3.yaml`:

```yaml
---
# SITE3 (ND 4.3.1 mirror of SITE1)
# S3_LE3.yaml - Leaf Switch 3 in SITE3 (VPC pair member with S3_LE4; mirror of S1_LE3)
name: S3_LE3
role: Leaf Switch
sid: 3503
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.154/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_SP1
  - S3_LE4
isl_bridges:
  - BR_S3_SP1_LE3_1
  - BR_S3_LE3_LE4_1
```

`S3_LE4.yaml`:

```yaml
---
# SITE3 (ND 4.3.1 mirror of SITE1)
# S3_LE4.yaml - Leaf Switch 4 in SITE3 (VPC pair member with S3_LE3; mirror of S1_LE4)
name: S3_LE4
role: Leaf Switch
sid: 3504
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.155/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_SP1
  - S3_LE3
isl_bridges:
  - BR_S3_SP1_LE4_1
  - BR_S3_LE3_LE4_1
```

`S3_TOR1.yaml`:

```yaml
---
# SITE3 (ND 4.3.1 mirror of SITE1)
# S3_TOR1.yaml - Top-of-Rack Switch 1 in SITE3 (dual-homed to VPC pair S3_LE1/S3_LE2; host S3_H1 on Eth1/3; mirror of S1_TOR1)
name: S3_TOR1
role: Top-of-Rack Switch
sid: 3601
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.161/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_LE1
  - S3_LE2
  - S3_H1
isl_bridges:
  - BR_S3_LE1_T1_1
  - BR_S3_LE2_T1_1
  - BR_S3_T1_H1_1
```

- [ ] **Step 2: Helpers and launch script**

```bash
cd config/nexus9000v
for s in bg1:3301:131 sp1:3401:141 le1:3501:151 le2:3502:152 le3:3503:154 le4:3504:155 tor1:3601:161; do
  IFS=: read -r name sid oct <<< "$s"
  printf 'telnet localhost %d\n' $((10000 + sid)) > "con_s3_$name"
  printf 'ssh admin@192.168.14.%s\n' "$oct" > "ssh_s3_$name"
  chmod +x "con_s3_$name" "ssh_s3_$name"
done
cat > site3.sh <<'SH'
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S3_BG1.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S3_LE1.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S3_LE2.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S3_LE3.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S3_LE4.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S3_TOR1.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S3_SP1.yaml
SH
cd -
```

- [ ] **Step 3: Verify (mirror check against SITE1, render, dry-run)**

```bash
cd config/nexus9000v
for s in BG1 SP1 LE1 LE2 LE3 LE4 TOR1; do
  diff <(sed -e 's/S1_/S3_/g; s/S2_/S4_/g; s/WAN1/WAN2/g; s/BR_ISN_S1_S2/BR_ISN_S3_S4/; s/BR_ND_DATA_12/BR_ND_DATA_14/; s/192\.168\.12\./192.168.14./' "S1_$s.yaml" \
         | grep -vE '^#|sid:') <(grep -vE '^#|sid:' "S3_$s.yaml") && echo "S3_$s mirrors S1_$s"
done
NXOS_PASSWORD=dummy python3 startup_config.py --print S3_SP1.yaml | grep -c 'interface Ethernet'   # expected 5
python3 nexus9000v.py --config S3_TOR1.yaml --dry-run | grep -E 'Telnet|tap3601'                   # expected Telnet: 13601, taps tap3601-0..3
python3 - <<'PY'
import glob, yaml
files = [f for f in glob.glob("S*.yaml") + glob.glob("../8000v/*.yaml") if "global" not in f and "netplan" not in f]
sids = [yaml.safe_load(open(f))["sid"] for f in files]
assert len(sids) == len(set(sids)), sorted(sids)
print("sids unique:", len(sids))
PY
bash -n site3.sh; cd -
```

Expected: seven `mirrors` lines, `5`, port 13601, no assertion.

- [ ] **Step 4: Commit**

```bash
git add config/nexus9000v/S3_*.yaml config/nexus9000v/con_s3_* config/nexus9000v/ssh_s3_* config/nexus9000v/site3.sh
git commit -m "SITE3: mirror SITE1 switch definitions on BR_ND_DATA_14 for ND 4.3.1"
```

---

### Task 4: SITE4 switch definitions, helpers, launch script; remove S4_LE2/S4_LE3

**Files:**

- Rewrite: `config/nexus9000v/S4_BG1.yaml`, `S4_SP1.yaml`, `S4_LE1.yaml`
- Delete: `config/nexus9000v/S4_LE2.yaml`, `S4_LE3.yaml`
- Modify: `con_s4_le1` (unchanged), create `ssh_s4_le1 con_s4_bg1 ssh_s4_bg1 con_s4_sp1 ssh_s4_sp1 site4.sh`

**Interfaces:**

- Produces hostnames `S4_BG1 S4_SP1 S4_LE1` with IPs `192.168.14.132 .142 .153`.

- [ ] **Step 1: Write the three YAMLs**

`S4_BG1.yaml`:

```yaml
---
# SITE4 (ND 4.3.1 mirror of SITE2)
# S4_BG1.yaml - Border Gateway 1 in SITE4 (mirror of S2_BG1)
name: S4_BG1
role: Border Gateway
sid: 4301
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.132/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_BG1
  - S4_SP1
  - WAN2
isl_bridges:
  - BR_ISN_S3_S4_1
  - BR_S4_BG1_SP1_1
  - BR_ISN_WAN_S4_1
```

`S4_SP1.yaml`:

```yaml
---
# SITE4 (ND 4.3.1 mirror of SITE2)
# S4_SP1.yaml - Spine Switch 1 in SITE4 (mirror of S2_SP1)
name: S4_SP1
role: Spine Switch
sid: 4401
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.142/24
mgmt_gw: 192.168.12.1
neighbors:
  - S4_BG1
  - S4_LE1
isl_bridges:
  - BR_S4_BG1_SP1_1
  - BR_S4_SP1_LE1_1
```

`S4_LE1.yaml`:

```yaml
---
# SITE4 (ND 4.3.1 mirror of SITE2)
# S4_LE1.yaml - Leaf Switch 1 in SITE4 (host S4_H1 on Eth1/2; mirror of S2_LE1)
name: S4_LE1
role: Leaf Switch
sid: 4501
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.153/24
mgmt_gw: 192.168.12.1
neighbors:
  - S4_SP1
  - S4_H1
isl_bridges:
  - BR_S4_SP1_LE1_1
  - BR_S4_LE1_H1_1
```

- [ ] **Step 2: Delete, helpers, launch script**

```bash
cd config/nexus9000v
git rm -q S4_LE2.yaml S4_LE3.yaml
for s in bg1:4301:132 sp1:4401:142 le1:4501:153; do
  IFS=: read -r name sid oct <<< "$s"
  printf 'telnet localhost %d\n' $((10000 + sid)) > "con_s4_$name"
  printf 'ssh admin@192.168.14.%s\n' "$oct" > "ssh_s4_$name"
  chmod +x "con_s4_$name" "ssh_s4_$name"
done
cat > site4.sh <<'SH'
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S4_BG1.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S4_LE1.yaml
sudo python3 nexus9000v.py --debug --global-config global_config.yaml --config S4_SP1.yaml
SH
cd -
```

- [ ] **Step 3: Verify**

```bash
cd config/nexus9000v
for s in BG1 SP1 LE1; do
  diff <(sed -e 's/S1_/S3_/g; s/S2_/S4_/g; s/WAN1/WAN2/g; s/BR_ISN_S1_S2/BR_ISN_S3_S4/; s/BR_ND_DATA_12/BR_ND_DATA_14/; s/192\.168\.12\./192.168.14./' "S2_$s.yaml" \
         | grep -vE '^#|sid:') <(grep -vE '^#|sid:' "S4_$s.yaml") && echo "S4_$s mirrors S2_$s"
done
grep -l 'BR_ND_DATA_12\|192.168.12' S3_*.yaml S4_*.yaml; echo "(expected: no output)"
NXOS_PASSWORD=dummy python3 startup_config.py --all --print >/dev/null && echo RENDER_OK
bash -n site4.sh; cd -
```

- [ ] **Step 4: Commit**

```bash
git add -A config/nexus9000v/S4_* config/nexus9000v/con_s4_* config/nexus9000v/ssh_s4_* config/nexus9000v/site4.sh
git commit -m "SITE4: mirror SITE2 switch definitions; retire S4_LE2/S4_LE3"
```

---

### Task 5: WAN2 (Catalyst 8000V)

**Files:**

- Create: `config/8000v/WAN2.yaml`, `config/8000v/con_wan2`, `config/8000v/ssh_wan2`
- Modify: `config/8000v/README.md` (Files list + one sentence)

**Interfaces:**

- Produces hostname `WAN2`, mgmt `192.168.14.112`, `GigabitEthernet2` -> `BR_ISN_WAN_S3_1`, `GigabitEthernet3` -> `BR_ISN_WAN_S4_1`.

- [ ] **Step 1: Write `WAN2.yaml`**

```yaml
---
# WAN2.yaml - Cross-site WAN/ISN router for the ND 4.3.1 mirror testbed (Catalyst 8000V, IOS-XE); mirror of WAN1.
# Cross-site infrastructure carries no site prefix (like ER).
name: WAN2
role: WAN Router
sid: 9102
mgmt_bridge: BR_ND_DATA_14
mgmt_ip: 192.168.14.112/24
mgmt_gw: 192.168.12.1
neighbors:
  - S3_BG1
  - S4_BG1
isl_bridges:
  - BR_ISN_WAN_S3_1
  - BR_ISN_WAN_S4_1
```

- [ ] **Step 2: Helpers + README**

```bash
cd config/8000v
printf 'telnet localhost 19102\n' > con_wan2; printf 'ssh admin@192.168.14.112\n' > ssh_wan2; chmod +x con_wan2 ssh_wan2
cd -
```

In `config/8000v/README.md`, replace the two Files bullets for the router YAML and the console/ssh helpers with:

```markdown
- `WAN1.yaml`, `WAN2.yaml` - per-router configs (ND 4.2.1 and ND 4.3.1 cross-site WAN/ISN routers)
- `con_wan1` / `ssh_wan1`, `con_wan2` / `ssh_wan2` - console / SSH one-liners
```

- [ ] **Step 3: Verify**

```bash
cd config/8000v
IOSXE_PASSWORD=dummy python3 startup_config.py --print WAN2.yaml | grep -E 'hostname|GigabitEthernet|ip address'
python3 8000v.py --config WAN2.yaml --dry-run | grep -E 'Telnet|tap9102'
pymarkdown scan README.md; cd -
```

Expected: `hostname WAN2`, `GigabitEthernet1..3`, `192.168.14.112 255.255.255.0`; `Telnet: 19102`; taps `tap9102-0..2`.

- [ ] **Step 4: Commit**

```bash
git add config/8000v/WAN2.yaml config/8000v/con_wan2 config/8000v/ssh_wan2 config/8000v/README.md
git commit -m "Add WAN2 (C8000V) for the ND 4.3.1 mirror testbed"
```

---

### Task 6: Host containers S3_H1 and S4_H1

**Files:**

- Modify: `config/containers/container_configs_access_mode.yaml`, `container_configs_trunk_mode.yaml`
- Create: `config/containers/S3_H1.netplan.yaml`, `S4_H1.netplan.yaml`
- Modify: `config/containers/README.md` (Quick Start + Container Specifications)

**Interfaces:**

- Produces containers `S3_H1` (eth0 192.168.14.171 on `BR_ND_DATA_14`, eth1 192.0.1.171 on `BR_S3_T1_H1_1`, MAC `00:00:73:00:00:01/02`) and `S4_H1`
  (eth0 192.168.14.172, eth1 192.0.1.172 on `BR_S4_LE1_H1_1`, MAC `00:00:74:00:00:01/02`). Test-net addresses equal S1_H1/S2_H1's on purpose.

- [ ] **Step 1: Append to `container_configs_access_mode.yaml`**

```yaml

  S3_H1:
    name: "S3_H1"
    management_interface:
      name: "eth0"
      ip_address: "192.168.14.171"
      netmask: "24"
      bridge: "BR_ND_DATA_14"
      mac_address: "00:00:73:00:00:01"
      description: "Management Interface"
    test_interface:
      name: "eth1"
      ip_address: "192.0.1.171"
      netmask: "24"
      bridge: "BR_S3_T1_H1_1"
      mac_address: "00:00:73:00:00:02"
      description: "Test Interface"
    vlans: []
    gateway_ip: "192.168.14.1"
    memory_kb: 1048576
    vcpus: 2

  S4_H1:
    name: "S4_H1"
    management_interface:
      name: "eth0"
      ip_address: "192.168.14.172"
      netmask: "24"
      bridge: "BR_ND_DATA_14"
      mac_address: "00:00:74:00:00:01"
      description: "Management Interface"
    test_interface:
      name: "eth1"
      ip_address: "192.0.1.172"
      netmask: "24"
      bridge: "BR_S4_LE1_H1_1"
      mac_address: "00:00:74:00:00:02"
      description: "Test Interface"
    vlans: []
    gateway_ip: "192.168.14.1"
    memory_kb: 1048576
    vcpus: 2
```

- [ ] **Step 2: Append to `container_configs_trunk_mode.yaml`** (same two blocks, but `test_interface.ip_address: ""`, `netmask: ""`, `gateway_ip: "192.168.14.2"`
  as the existing trunk entries do, and):

```yaml
    vlans:
      - vlan_id: 2
        ip_address: "192.0.1.171"
        netmask: "24"
        description: "VLAN 2 Test Interface"
      - vlan_id: 3
        ip_address: "192.0.2.171"
        netmask: "24"
        description: "VLAN 3 Test Interface"
```

(`.172` for S4_H1.)

- [ ] **Step 3: Netplan reference files** (`S3_H1.netplan.yaml`; `S4_H1.netplan.yaml` identical with `.172` and `74ff`)

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 192.168.14.171/24
      dhcp4: false
      dhcp6: false
      accept-ra: true
      link-local: [ipv6]
      routes:
        - to: 10.10.0.0/16
          via: 192.168.14.1

    eth1:
      addresses:
        - 192.0.1.171/24
        - 2001:192:0:1:200:73ff:fe00:2/64
      dhcp4: false
      dhcp6: false
      accept-ra: true
      link-local: [ipv6]
      routes:
        - to: 10.19.0.2/32
          via: 192.0.1.1
        - to: 10.29.0.2/32
          via: 192.0.1.1
```

- [ ] **Step 4: README** - add the two `main.py` lines under Quick Start (`S3_H1`, `S4_H1`) and two spec blocks under Container Specifications:

```markdown
### S3_H1 Container (access mode interfaces, SITE3 - ND 4.3.1 mirror of S1_H1)

- eth0: 192.168.14.171/24 on BR_ND_DATA_14
- eth1: 192.0.1.171/24 on BR_S3_T1_H1_1

### S4_H1 Container (access mode interfaces, SITE4 - ND 4.3.1 mirror of S2_H1)

- eth0: 192.168.14.172/24 on BR_ND_DATA_14
- eth1: 192.0.1.172/24 on BR_S4_LE1_H1_1
```

- [ ] **Step 5: Verify and commit**

```bash
cd config/containers
python3 main.py --config container_configs_access_mode.yaml --list-containers     # expected: S1_H1 S2_H1 S3_H1 S4_H1
python3 main.py --config container_configs_trunk_mode.yaml --list-containers
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ('S3_H1.netplan.yaml','S4_H1.netplan.yaml')]"
pymarkdown scan README.md; cd -
git add config/containers
git commit -m "Add S3_H1/S4_H1 host containers for the ND 4.3.1 mirror testbed"
```

---

### Task 7: Dynamic inventory

**Files:**

- Modify: `config/ansible/dynamic_inventory.py` (IPs ~44-71, hostnames ~103-112, links comment ~114, interfaces ~166-193, `all.vars`, `nxos.children`)

**Interfaces:**

- Produces env-overridable vars `ND_431_IP4` (default `10.10.20.20`), `S3_LE2_IP4 S3_LE3_IP4 S3_LE4_IP4 S3_TOR1_IP4`, hostnames, `S3_SP1_INTERFACE_3..5`,
  `S3_LE1_INTERFACE_3`, `S3_LE2_INTERFACE_1..3`, `S3_LE3/LE4_INTERFACE_1..2`, `S3_TOR1_INTERFACE_1..3`, `S3_BG1_INTERFACE_3`, `S4_BG1_INTERFACE_3`; group `nd431`.

- [ ] **Step 1: Addresses**

Replace the SITE3/SITE4 IP block with:

```python
# SITE3 / SITE4 (ND 4.3.1 mirror of SITE1 / SITE2: same last octet on 192.168.14.0/24 / BR_ND_DATA_14)
S3_BG1_IP4 = environ.get("S3_BG1_IP4", "192.168.14.131")
S4_BG1_IP4 = environ.get("S4_BG1_IP4", "192.168.14.132")
S3_SP1_IP4 = environ.get("S3_SP1_IP4", "192.168.14.141")
S4_SP1_IP4 = environ.get("S4_SP1_IP4", "192.168.14.142")
S3_LE1_IP4 = environ.get("S3_LE1_IP4", "192.168.14.151")
S3_LE2_IP4 = environ.get("S3_LE2_IP4", "192.168.14.152")
S3_LE3_IP4 = environ.get("S3_LE3_IP4", "192.168.14.154")
S3_LE4_IP4 = environ.get("S3_LE4_IP4", "192.168.14.155")
S3_TOR1_IP4 = environ.get("S3_TOR1_IP4", "192.168.14.161")
S4_LE1_IP4 = environ.get("S4_LE1_IP4", "192.168.14.153")
S3_LE1_IP4_INTERFACE_2 = environ.get("S3_LE1_IP4_INTERFACE_2", "192.168.0.3")
S4_LE1_IP4_INTERFACE_2 = environ.get("S4_LE1_IP4_INTERFACE_2", "192.168.0.4")
```

and next to `ND_IP4_2` add `ND_431_IP4 = environ.get("ND_431_IP4", "10.10.20.20")` with the comment
`# ND 4.3.1.175 node1 management IP; data 192.168.14.14 on BR_ND_DATA_14 (persistent data .30-.32, persistent mgmt 10.10.20.60-.62)`. Delete `S4_LE2_IP4`, `S4_LE3_IP4`,
`S4_LE2_IP4_INTERFACE_2`, `S4_LE3_IP4_INTERFACE_2`, `S4_LE2_HOSTNAME`, `S4_LE3_HOSTNAME`, every `S4_LE2_INTERFACE_*`/`S4_LE3_INTERFACE_*`, and their
`all.vars`/`nxos.children` entries. Add `S3_LE2_HOSTNAME`, `S3_LE3_HOSTNAME`, `S3_LE4_HOSTNAME`, `S3_TOR1_HOSTNAME` (defaults = names).

- [ ] **Step 2: Interfaces** - replace the SITE3/SITE4 interface block with the exact mirror of the SITE1/SITE2 block (same interface numbers, `S1`->`S3`,
  `S2`->`S4`), adding `S3_BG1_INTERFACE_3` / `S4_BG1_INTERFACE_3` = `Ethernet1/3` (WAN links; SITE1/SITE2 lack these today, add `S1_BG1_INTERFACE_3` and
  `S2_BG1_INTERFACE_3` too). Extend the `# Links` comment with the SITE3/SITE4 rows from the Task 2 header.

- [ ] **Step 3: Groups** - add

```python
    "nd431": {
        "hosts": [ND_431_IP4],
        "vars": {
            "ansible_connection": "ansible.netcommon.httpapi",
            "ansible_network_os": "cisco.nd.nd",
        },
    },
```

and publish every new var in `all.vars`; `nxos.children` gains `S3_LE2 S3_LE3 S3_LE4 S3_TOR1`, loses `S4_LE2 S4_LE3`.

- [ ] **Step 4: Verify and commit**

```bash
python3 config/ansible/dynamic_inventory.py | python3 -m json.tool > /dev/null && echo OK
python3 config/ansible/dynamic_inventory.py | grep -c '192.168.14'     # expected 10 (every S3/S4 IP4 var)
python3 config/ansible/dynamic_inventory.py | grep -c 'S4_LE[23]'       # expected 0
flake8 config/ansible/dynamic_inventory.py && black --check config/ansible/dynamic_inventory.py
git add config/ansible/dynamic_inventory.py
git commit -m "Inventory: SITE3/SITE4 mirror addresses and interfaces; ND 4.3.1 group"
```

---

### Task 8: Topology model and the two topology files

**Files:**

- Create: `config/nd/provision/topology.py`, `config/nd/provision/tests/test_topology.py`
- Create: `config/nd/provision/topology_nd421.yaml`, `config/nd/provision/topology_nd431.yaml`

**Interfaces:**

- Produces: `topology.load(path: Path) -> Topology` with dataclasses `Topology(fabrics: list[Fabric], fabric_groups: list[FabricGroup], isn: Isn,
  overlay: Overlay)`, `Fabric(name, type, asn, settings: dict, switches: list[Switch])`, `Switch(hostname, ip, role, platform)`,
  `FabricGroup(name, settings: dict, members: list[str])`, `Isn(links: list[Link], wan: Wan)`, `Link(src_fabric, src, src_if, dst_fabric, dst, dst_if, src_asn,
  dst_asn, src_ip, dst_ip, mtu)`, `Wan(hostname, fabric, cdp_interfaces: list[str], loopback: dict, bgp_router_id: dict)`,
  `Overlay(vrfs: list[dict], networks: list[dict], vrf_attachments: list[dict], network_attachments: list[dict])`; `Topology.switch_fabric(hostname) -> str`.

- [ ] **Step 1: Failing test**

`tests/test_topology.py`:

```python
"""topology.load must reject dangling references and accept the two shipped files."""
from pathlib import Path

import pytest

from topology import load

HERE = Path(__file__).resolve().parents[1]


def test_shipped_topologies_load_and_mirror():
    t421 = load(HERE / "topology_nd421.yaml")
    t431 = load(HERE / "topology_nd431.yaml")
    assert [f.name for f in t421.fabrics] == [f.name for f in t431.fabrics] == ["SITE1", "SITE2", "ISN"]
    assert t421.fabric_groups[0].members == t431.fabric_groups[0].members == ["SITE1", "SITE2", "ISN"]
    assert t421.switch_fabric("S1_BG1") == "SITE1" and t431.switch_fabric("S3_BG1") == "SITE1"
    assert len(t421.isn.links) == len(t431.isn.links) == 2
    assert t421.overlay.networks == t431.overlay.networks  # identical overlay objects, only attachments name different switches


def test_dangling_switch_reference_is_rejected(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(
        "fabrics:\n  - name: SITE1\n    type: vxlanIbgp\n    asn: '65001'\n    switches: []\n"
        "fabric_groups: []\nisn:\n  links:\n    - {src_fabric: ISN, src: WAN9, src_if: Gi2, dst_fabric: SITE1, dst: S1_BG1, dst_if: Eth1/3,"
        " src_asn: '1', dst_asn: '2', src_ip: 10.0.0.1/30, dst_ip: 10.0.0.2, mtu: 9000}\n  wan: {hostname: WAN9, fabric: ISN}\noverlay: {}\n"
    )
    with pytest.raises(ValueError, match="WAN9"):
        load(bad)
```

- [ ] **Step 2: Run to verify it fails** - `uv run pytest config/nd/provision/tests/test_topology.py -q` -> `ModuleNotFoundError: topology`.

- [ ] **Step 3: Write `topology.py`**

```python
#!/usr/bin/env python3
"""Declarative testbed description consumed by provision.py (see topology_nd421.yaml for the schema by example)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Switch:
    hostname: str
    ip: str
    role: str
    platform: str = "nx-os"


@dataclass(frozen=True)
class Fabric:
    name: str
    type: str
    asn: str
    settings: dict = field(default_factory=dict)
    switches: list[Switch] = field(default_factory=list)


@dataclass(frozen=True)
class FabricGroup:
    name: str
    settings: dict = field(default_factory=dict)
    members: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Link:
    src_fabric: str
    src: str
    src_if: str
    dst_fabric: str
    dst: str
    dst_if: str
    src_asn: str
    dst_asn: str
    src_ip: str
    dst_ip: str
    mtu: int = 9000


@dataclass(frozen=True)
class Wan:
    hostname: str
    fabric: str
    cdp_interfaces: list[str] = field(default_factory=list)
    loopback: dict = field(default_factory=dict)
    bgp_router_id: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Isn:
    links: list[Link] = field(default_factory=list)
    wan: Wan | None = None


@dataclass(frozen=True)
class Overlay:
    vrfs: list[dict] = field(default_factory=list)
    networks: list[dict] = field(default_factory=list)
    vrf_attachments: list[dict] = field(default_factory=list)
    network_attachments: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Topology:
    fabrics: list[Fabric]
    fabric_groups: list[FabricGroup]
    isn: Isn
    overlay: Overlay

    def switches(self) -> dict[str, Switch]:
        return {s.hostname: s for f in self.fabrics for s in f.switches}

    def switch_fabric(self, hostname: str) -> str:
        for fabric in self.fabrics:
            if any(s.hostname == hostname for s in fabric.switches):
                return fabric.name
        raise ValueError(f"unknown switch {hostname}")


def _validate(topo: Topology) -> None:
    names = set(topo.switches())
    fabrics = {f.name for f in topo.fabrics}
    for group in topo.fabric_groups:
        for member in group.members:
            if member not in fabrics:
                raise ValueError(f"fabric group {group.name}: unknown member fabric {member}")
    for link in topo.isn.links:
        for host in (link.src, link.dst):
            if host not in names:
                raise ValueError(f"isn link references unknown switch {host}")
    if topo.isn.wan and topo.isn.wan.hostname not in names:
        raise ValueError(f"isn.wan references unknown switch {topo.isn.wan.hostname}")
    for att in topo.overlay.vrf_attachments + topo.overlay.network_attachments:
        if att["switch"] not in names:
            raise ValueError(f"overlay attachment references unknown switch {att['switch']}")


def load(path: Path) -> Topology:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fabrics = [Fabric(name=f["name"], type=f["type"], asn=str(f["asn"]), settings=f.get("settings", {}), switches=[Switch(**s) for s in f.get("switches", [])])
               for f in raw.get("fabrics", [])]
    groups = [FabricGroup(**g) for g in raw.get("fabric_groups", [])]
    isn_raw = raw.get("isn", {}) or {}
    isn = Isn(links=[Link(**item) for item in isn_raw.get("links", [])], wan=Wan(**isn_raw["wan"]) if isn_raw.get("wan") else None)
    overlay = Overlay(**(raw.get("overlay", {}) or {}))
    topo = Topology(fabrics=fabrics, fabric_groups=groups, isn=isn, overlay=overlay)
    _validate(topo)
    return topo
```

- [ ] **Step 4: Write `topology_nd421.yaml`** (fabric settings from `docs/nd4_fabrics_bringup.md`; overlay objects transcribed from `~/tmp/snap_nd421`)

```yaml
# Declarative description of the ND 4.2.1 testbed. topology_nd431.yaml is the same file with only
# hostnames and mgmt IPs changed -- `diff` the two to prove the mirror. Values that must match the
# live ND 4.2.1 were captured with snapshot.py (fields noted per section).
fabrics:
  - name: SITE1
    type: vxlanIbgp
    asn: "65001"
    settings:            # merged into the fabric object (GET -> update -> PUT) after create
      management:
        bgpLoopbackIpRange: 10.11.0.0/22
        nveLoopbackIpRange: 10.12.0.0/22
        anycastRendezvousPointIpRange: 10.13.0.0/24
        intraFabricSubnetRange: 10.14.0.0/22
        vrfLiteSubnetRange: 10.15.0.0/16
        vrfLiteAutoConfig: back2BackAndToExternal
        autoSymmetricVrfLite: true
        autoVrfLiteDefaultVrf: true
        autoSymmetricDefaultVrf: true
    switches:
      - {hostname: S1_BG1, ip: 192.168.12.131, role: borderGateway}
      - {hostname: S1_SP1, ip: 192.168.12.141, role: spine}
      - {hostname: S1_LE1, ip: 192.168.12.151, role: leaf}
      - {hostname: S1_LE2, ip: 192.168.12.152, role: leaf}
      - {hostname: S1_LE3, ip: 192.168.12.154, role: leaf}
      - {hostname: S1_LE4, ip: 192.168.12.155, role: leaf}
      - {hostname: S1_TOR1, ip: 192.168.12.161, role: tor}
  - name: SITE2
    type: vxlanIbgp
    asn: "65002"
    settings:
      management:
        bgpLoopbackIpRange: 10.21.0.0/22
        nveLoopbackIpRange: 10.22.0.0/22
        anycastRendezvousPointIpRange: 10.23.0.0/24
        intraFabricSubnetRange: 10.24.0.0/22
        vrfLiteSubnetRange: 10.25.0.0/16
        vrfLiteAutoConfig: back2BackAndToExternal
        autoSymmetricVrfLite: true
        autoVrfLiteDefaultVrf: true
        autoSymmetricDefaultVrf: true
    switches:
      - {hostname: S2_BG1, ip: 192.168.12.132, role: borderGateway}
      - {hostname: S2_SP1, ip: 192.168.12.142, role: spine}
      - {hostname: S2_LE1, ip: 192.168.12.153, role: leaf}
  - name: ISN
    type: externalConnectivity
    asn: "65535"
    settings:
      management:
        monitoredMode: false          # API-created external fabrics default to true; true silently blocks every deploy
    switches:
      - {hostname: WAN1, ip: 192.168.12.112, role: edgeRouter, platform: ios-xe}

fabric_groups:
  - name: MSD
    settings:
      management:
        type: vxlan
        multisiteOverlayInterConnectType: directPeering
        autoMultisiteUnderlayInterConnect: true
        bgpSendCommunity: true
    members: [SITE1, SITE2, ISN]

isn:
  links:
    - {src_fabric: ISN, src: WAN1, src_if: GigabitEthernet2, dst_fabric: SITE1, dst: S1_BG1, dst_if: Ethernet1/3,
       src_asn: "65535", dst_asn: "65001", src_ip: 10.33.0.1/30, dst_ip: 10.33.0.2, mtu: 9000}
    - {src_fabric: ISN, src: WAN1, src_if: GigabitEthernet3, dst_fabric: SITE2, dst: S2_BG1, dst_if: Ethernet1/3,
       src_asn: "65535", dst_asn: "65002", src_ip: 10.33.0.5/30, dst_ip: 10.33.0.6, mtu: 9000}
  wan:
    hostname: WAN1
    fabric: ISN
    cdp_interfaces: [GigabitEthernet2, GigabitEthernet3]
    loopback: {ip: 10.35.0.1, description: "Routing loopback (router-id)"}
    bgp_router_id: {BGP_AS: "65535", LOOPBACK_IP: 10.35.0.1}

overlay:
  # vrfs / networks: the objects returned by snapshot files vrfs_SITE1.json / networks_SITE1.json, minus
  # fabricName, vrfStatus/networkStatus and any key listed in snapshot.VOLATILE_KEYS. Copy them verbatim
  # (vrfName, vrfId, vlanId, vrfTemplateName/coreData..., networkName, networkId, vlanId, vrfName,
  # networkMode, l2Data, l3Data.gatewayIpv4Address == 192.0.1.1/24). They are created in every fabric
  # listed under `fabrics:`.
  vrfs:
    - fabrics: [SITE1, SITE2]
      object: {}     # <- paste from vrfs_SITE1.json
  networks:
    - fabrics: [SITE1, SITE2]
      object: {}     # <- paste from networks_SITE1.json (VLAN 2, gateway 192.0.1.1/24)
  # attachments: from vrf_attachments_*.json / network_attachments_*.json; one entry per switch.
  # `interfaces` is the list from the snapshot (mode/name per interface, e.g. the S1_TOR1 host port
  # and the vPC pair's port-channel to the TOR, S2_LE1 Ethernet1/2).
  vrf_attachments:
    - {fabric: SITE1, vrf: "<vrfName>", switch: S1_LE1}
    - {fabric: SITE1, vrf: "<vrfName>", switch: S1_LE2}
    - {fabric: SITE1, vrf: "<vrfName>", switch: S1_TOR1}
    - {fabric: SITE2, vrf: "<vrfName>", switch: S2_LE1}
  network_attachments:
    - {fabric: SITE1, network: "<networkName>", switch: S1_LE1, vlan: 2, interfaces: []}
    - {fabric: SITE1, network: "<networkName>", switch: S1_LE2, vlan: 2, interfaces: []}
    - {fabric: SITE1, network: "<networkName>", switch: S1_TOR1, vlan: 2, interfaces: []}
    - {fabric: SITE2, network: "<networkName>", switch: S2_LE1, vlan: 2, interfaces: []}
```

Transcription rules for the `overlay:` section (do this with `~/tmp/snap_nd421` open; the file must contain no `<...>` markers or empty `object: {}` when done):

1. `vrfs[].object` = each element of `vrfs_SITE1.json["vrfs"]` with keys `fabricName`, `vrfStatus` and `snapshot.VOLATILE_KEYS` removed.
2. `networks[].object` = same from `networks_SITE1.json["networks"]`.
3. `vrf_attachments` / `network_attachments` = one entry per `(fabric, switch)` that has `attach: true` / `isAttached` in the `*_attachments_*.json` files; copy
   `vlanId` and the `interfaces` list verbatim. Delete the entries above for switches that are not attached, add entries for switches that are.
4. Fabric `settings` keys are checked against `fabric_SITE1.json`: if the snapshot shows a different value for any listed key, the snapshot wins (record why in the
   commit message).

- [ ] **Step 5: Write `topology_nd431.yaml`**

```bash
cd config/nd/provision
sed -e 's/\bS1_/S3_/g; s/\bS2_/S4_/g; s/\bWAN1\b/WAN2/g; s/ND 4\.2\.1/ND 4.3.1/; s/topology_nd431/topology_nd421/' \
    -e 's/192\.168\.12\./192.168.14./g' \
    topology_nd421.yaml > topology_nd431.yaml
diff topology_nd421.yaml topology_nd431.yaml | grep '^[<>]' | grep -vE 'S[1-4]_|WAN[12]|192\.168\.1[24]\.|ND 4\.[23]\.1|topology_nd4' ; echo "(expected: no output)"
cd -
```

- [ ] **Step 6: Tests, lint, commit**

```bash
uv run pytest config/nd/provision/tests -q && flake8 config/nd/provision && mypy config/nd/provision/topology.py && black --check config/nd/provision
git add config/nd/provision/topology.py config/nd/provision/tests/test_topology.py config/nd/provision/topology_nd4*.yaml
git commit -m "Add declarative topology model and the ND 4.2.1 / ND 4.3.1 testbed definitions"
```

---

### Task 9: `provision.py` - fabrics and MSD phases

**Files:**

- Create: `config/nd/provision/provision.py`, `config/nd/provision/tests/test_provision_payloads.py`

**Interfaces:**

- Consumes: `NDClient`, `Topology`.
- Produces: CLI `provision.py --topology <yaml> [--nd-ip IP] [--phase fabrics|msd|switches|isn|overlay|deploy|all] [--dry-run]`; pure builders
  `fabric_create_payload(fabric: Fabric) -> dict`, `fabric_group_create_payload(group: FabricGroup) -> dict`, `merge_settings(current: dict, settings: dict) -> dict`;
  class `Provisioner(client, topo, dry_run)` with one method per phase. Tasks 10-12 add methods to this class.

- [ ] **Step 1: Failing tests**

```python
"""Pure payload builders in provision.py."""
from provision import fabric_create_payload, fabric_group_create_payload, merge_settings
from topology import Fabric, FabricGroup


def test_fabric_create_payload_minimal_and_premier():
    fab = Fabric(name="ISN", type="externalConnectivity", asn="65535")
    assert fabric_create_payload(fab) == {
        "name": "ISN", "category": "fabric", "licenseTier": "premier", "securityDomain": "all", "telemetryCollection": False,
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
```

- [ ] **Step 2: Run to verify failure** - `uv run pytest config/nd/provision/tests/test_provision_payloads.py -q` -> `ModuleNotFoundError: provision`.

- [ ] **Step 3: Write `provision.py` (skeleton + fabrics + msd)**

```python
#!/usr/bin/env python3
"""Idempotent, phased provisioning of one lab testbed into one Nexus Dashboard.

    provision.py --topology topology_nd431.yaml [--nd-ip 10.10.20.20] [--phase all] [--dry-run]

Phases (each safe to re-run; --phase all runs them in order):
  fabrics   create SITE1/SITE2/ISN if absent, then merge `settings` into each fabric object (GET/update/PUT)
  msd       create the MSD fabric group if absent, add members one at a time (ND rejects batches)
  switches  add switches per fabric by IP (discover+import), wait until they list, set roles, configDeploy
  isn       WAN loopback + router-id policy, ebgpVrfLite links, CDP policies, deploy ISN/SITE1/SITE2
  overlay   VRFs + networks in each fabric, attachments per switch, vrfActions/networkActions deploy
  deploy    configDeploy every fabric and print any non-empty pendingConfig
Credentials: ND_IP4/ND_USERNAME/ND_PASSWORD/ND_DOMAIN (controller), NXOS_PASSWORD / IOSXE_PASSWORD (switch discovery).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import time
from pathlib import Path
from typing import Any

from nd_client import NDClient, NDCredentials
from topology import Fabric, FabricGroup, Topology, load

PHASES = ["fabrics", "msd", "switches", "isn", "overlay", "deploy"]


def fabric_create_payload(fabric: Fabric) -> dict:
    return {
        "name": fabric.name, "category": "fabric", "licenseTier": "premier", "securityDomain": "all", "telemetryCollection": False,
        "management": {"type": fabric.type, "bgpAsn": fabric.asn},
    }


def fabric_group_create_payload(group: FabricGroup) -> dict:
    management = {"type": "vxlan"}
    management.update(group.settings.get("management", {}))
    return {"name": group.name, "category": "fabricGroup", "management": management}


def merge_settings(current: dict, settings: dict) -> dict:
    merged = copy.deepcopy(current)
    for key, value in settings.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


class Provisioner:
    def __init__(self, client: NDClient, topo: Topology, dry_run: bool = False) -> None:
        self.client = client
        self.topo = topo
        self.dry_run = dry_run

    # -- helpers -------------------------------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        print(("[dry-run] " if self.dry_run else "") + msg)

    def _post(self, path: str, body: Any) -> Any:
        self._log(f"POST {path} {json.dumps(body)[:300]}")
        return None if self.dry_run else self.client.post(path, json=body)

    def _put(self, path: str, body: Any) -> Any:
        self._log(f"PUT {path}")
        return None if self.dry_run else self.client.put(path, json=body)

    def existing_fabrics(self) -> dict[str, dict]:
        return {f["name"]: f for f in (self.client.get("/fabrics") or {}).get("fabrics", [])}

    # -- phase: fabrics ------------------------------------------------------------------------------------
    def phase_fabrics(self) -> None:
        existing = self.existing_fabrics()
        for fabric in self.topo.fabrics:
            if fabric.name not in existing:
                self._post("/fabrics", fabric_create_payload(fabric))
            if fabric.settings and not self.dry_run:
                current = self.client.get(f"/fabrics/{fabric.name}")
                merged = merge_settings(current, fabric.settings)
                if merged != current:
                    self._put(f"/fabrics/{fabric.name}", merged)
            elif fabric.settings:
                self._log(f"would merge settings into /fabrics/{fabric.name}: {json.dumps(fabric.settings)}")

    # -- phase: msd ----------------------------------------------------------------------------------------
    def phase_msd(self) -> None:
        existing = self.existing_fabrics()
        for group in self.topo.fabric_groups:
            if group.name not in existing:
                self._post("/fabrics", fabric_group_create_payload(group))
            members = {m["name"] for m in (self.client.get(f"/fabrics/{group.name}/members") or {}).get("fabrics", [])} if not self.dry_run else set()
            for member in group.members:
                if member not in members:
                    self._post(f"/fabrics/{group.name}/actions/addMembers", {"members": [{"name": member}]})

    def run(self, phases: list[str]) -> None:
        for phase in phases:
            print(f"=== phase {phase} ===")
            getattr(self, f"phase_{phase}")()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--nd-ip", help="override ND_IP4")
    parser.add_argument("--phase", default="all", choices=PHASES + ["all"])
    parser.add_argument("--dry-run", action="store_true", help="print every write instead of sending it")
    args = parser.parse_args()
    topo = load(args.topology)
    client = NDClient(NDCredentials.from_env(args.nd_ip))
    client.login()
    Provisioner(client, topo, dry_run=args.dry_run).run(PHASES if args.phase == "all" else [args.phase])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Tests + lint + a dry run against ND 4.3.1 (on the host)**

```bash
uv run pytest config/nd/provision/tests -q && flake8 config/nd/provision && mypy config/nd/provision/provision.py && black --check config/nd/provision
# on glide-wired, prod env sourced:
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase fabrics --dry-run
```

Expected: three `[dry-run] POST /fabrics ...` lines (SITE1, SITE2, ISN) and three "would merge settings" lines.

- [ ] **Step 5: Commit** - `git add config/nd/provision && git commit -m "provision.py: fabrics and MSD phases"`

---

### Task 10: `provision.py` - switches phase

**Files:**

- Modify: `config/nd/provision/provision.py`, `tests/test_provision_payloads.py`

**Interfaces:**

- Produces: `switch_add_payload(fabric: Fabric, password: str) -> dict`, `Provisioner.serial(hostname) -> str` (cached, refreshed per phase),
  `Provisioner.wait_for_switches(fabric, hostnames, timeout=900)`, `Provisioner.config_deploy(fabric_name)`, `Provisioner.pending(fabric_name, serial) -> list`.

- [ ] **Step 1: Failing test**

```python
from provision import switch_add_payload
from topology import Fabric, Switch


def test_switch_add_payload_groups_by_platform_and_never_preserves_config():
    fab = Fabric(name="ISN", type="externalConnectivity", asn="65535", switches=[Switch("WAN2", "192.168.14.112", "edgeRouter", "ios-xe")])
    body = switch_add_payload(fab, "pw")
    assert body == {
        "switches": [{"ip": "192.168.14.112", "hostname": "WAN2", "switchRole": "edgeRouter"}],
        "platformType": "ios-xe", "preserveConfig": False, "useCredentialForWrite": True, "username": "admin", "password": "pw",
    }
```

- [ ] **Step 2: Verify failure** (`ImportError: switch_add_payload`), then implement:

```python
def switch_add_payload(fabric: Fabric, password: str, username: str = "admin") -> dict:
    platforms = {s.platform for s in fabric.switches}
    if len(platforms) != 1:
        raise ValueError(f"{fabric.name}: one platformType per add call, got {platforms}")
    return {
        "switches": [{"ip": s.ip, "hostname": s.hostname, "switchRole": s.role} for s in fabric.switches],
        "platformType": platforms.pop(), "preserveConfig": False, "useCredentialForWrite": True, "username": username, "password": password,
    }
```

and in `Provisioner`:

```python
    def fabric_switches(self, fabric_name: str) -> dict[str, dict]:
        return {s["hostname"]: s for s in (self.client.get(f"/fabrics/{fabric_name}/switches") or {}).get("switches", [])}

    def serial(self, hostname: str) -> str:
        """Serial number by hostname, looked up live (serials change on every VM rebuild). Placeholder in dry runs."""
        fabric = self.topo.switch_fabric(hostname)
        entry = self.fabric_switches(fabric).get(hostname)
        if entry:
            return entry["serialNumber"]
        if self.dry_run:
            return f"<{hostname}-serial>"
        raise RuntimeError(f"{hostname} is not in fabric {fabric} on {self.client.creds.ip}; run --phase switches first")

    def wait_for_switches(self, fabric_name: str, hostnames: list[str], timeout: int = 900) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            present = self.fabric_switches(fabric_name)
            if all(h in present for h in hostnames):
                return
            time.sleep(15)
        raise TimeoutError(f"{fabric_name}: switches never listed: {[h for h in hostnames if h not in present]}")

    def config_deploy(self, fabric_name: str) -> None:
        self._post(f"/fabrics/{fabric_name}/actions/configDeploy", None)

    def pending(self, fabric_name: str, serial: str) -> list:
        return self.client.get(f"/fabrics/{fabric_name}/switches/{serial}/pendingConfig") or []

    def phase_switches(self) -> None:
        for fabric in self.topo.fabrics:
            present = self.fabric_switches(fabric.name) if not self.dry_run else {}
            missing = [s for s in fabric.switches if s.hostname not in present]
            if missing:
                password = os.environ.get("IOSXE_PASSWORD" if fabric.type == "externalConnectivity" else "NXOS_PASSWORD") or os.environ.get("NXOS_PASSWORD", "")
                self._post(f"/fabrics/{fabric.name}/switches", switch_add_payload(Fabric(fabric.name, fabric.type, fabric.asn, {}, missing), password))
                if not self.dry_run:
                    self.wait_for_switches(fabric.name, [s.hostname for s in missing])
            if not self.dry_run:
                present = self.fabric_switches(fabric.name)
                wrong = [{"switchId": present[s.hostname]["serialNumber"], "role": s.role} for s in fabric.switches if present[s.hostname].get("switchRole") != s.role]
                if wrong:
                    self._post(f"/fabrics/{fabric.name}/switchActions/changeRoles", {"switchRoles": wrong})
            self.config_deploy(fabric.name)
```

- [ ] **Step 3: Tests, lint, dry run, commit**

```bash
uv run pytest config/nd/provision/tests -q && flake8 config/nd/provision && mypy config/nd/provision/provision.py && black --check config/nd/provision
git add config/nd/provision && git commit -m "provision.py: switches phase (add, wait, roles, configDeploy)"
```

---

### Task 11: `provision.py` - ISN phase (port of the `provision-isn` skill)

**Files:**

- Modify: `config/nd/provision/provision.py`, `tests/test_provision_payloads.py`

**Interfaces:**

- Produces: `link_payload(link: Link, src_serial: str, dst_serial: str) -> dict`, `cdp_policy(serial: str, interface: str) -> dict`,
  `cdp_run_policy(serial: str) -> dict`, `router_id_policy(serial: str, inputs: dict) -> dict`, `loopback_interface(serial: str, loopback: dict) -> dict`.

- [ ] **Step 1: Failing test**

```python
from provision import cdp_policy, link_payload, router_id_policy
from topology import Link


def test_link_payload_matches_the_known_good_isn_link():
    link = Link("ISN", "WAN1", "GigabitEthernet3", "SITE2", "S2_BG1", "Ethernet1/3", "65535", "65002", "10.33.0.5/30", "10.33.0.6", 9000)
    body = link_payload(link, "WSER", "BSER")
    assert body["links"][0]["srcSwitchId"] == "WSER" and body["links"][0]["dstSwitchId"] == "BSER"
    inputs = body["links"][0]["configData"]["templateInputs"]
    assert inputs["templateConfigGenPeer"] == "ios_xe_Ext_VRF_Lite_Jython" and inputs["srcIpAddressMask"] == "10.33.0.5/30" and inputs["dstIpAddress"] == "10.33.0.6"
    assert inputs["srcInterfaceDescription"] == "connected-to-S2_BG1-Ethernet1/3"


def test_policies():
    assert cdp_policy("W", "GigabitEthernet2") == {
        "templateName": "ios_xe_cdp_enable_interface", "entityType": "interface", "entityName": "GigabitEthernet2", "switchId": "W",
        "templateInputs": {"INTF_NAME": "GigabitEthernet2"},
    }
    assert router_id_policy("W", {"BGP_AS": "65535", "LOOPBACK_IP": "10.35.0.1"})["templateName"] == "ios_xe_bgp_router_id"
```

- [ ] **Step 2: Implement**

```python
def link_payload(link: Link, src_serial: str, dst_serial: str) -> dict:
    return {"links": [{
        "srcFabricName": link.src_fabric, "srcSwitchName": link.src, "srcSwitchId": src_serial, "srcInterfaceName": link.src_if,
        "dstFabricName": link.dst_fabric, "dstSwitchName": link.dst, "dstSwitchId": dst_serial, "dstInterfaceName": link.dst_if,
        "configData": {"policyType": "ebgpVrfLite", "templateInputs": {
            "srcEbgpAsn": link.src_asn, "dstEbgpAsn": link.dst_asn, "srcIpAddressMask": link.src_ip, "dstIpAddress": link.dst_ip,
            "linkMtu": link.mtu, "autoGenConfigPeer": True, "inheritTtagFabricSetting": True, "templateConfigGenPeer": "ios_xe_Ext_VRF_Lite_Jython",
            "srcInterfaceDescription": f"connected-to-{link.dst}-{link.dst_if}", "dstInterfaceDescription": f"connected-to-{link.src}-{link.src_if}",
        }},
    }]}


def cdp_run_policy(serial: str) -> dict:
    return {"templateName": "ios_xe_cdp_run", "entityType": "switch", "entityName": "SWITCH", "switchId": serial, "templateInputs": {}}


def cdp_policy(serial: str, interface: str) -> dict:
    return {"templateName": "ios_xe_cdp_enable_interface", "entityType": "interface", "entityName": interface, "switchId": serial,
            "templateInputs": {"INTF_NAME": interface}}


def router_id_policy(serial: str, inputs: dict) -> dict:
    return {"templateName": "ios_xe_bgp_router_id", "entityType": "switch", "entityName": "SWITCH", "switchId": serial, "templateInputs": inputs}


def loopback_interface(serial: str, loopback: dict) -> dict:
    return {"interfaces": [{"switchId": serial, "interfaceType": "loopback", "interfaceName": f"Loopback{loopback.get('id', 0)}", "configData": {
        "networkOS": {"networkOSType": "ios-xe", "policy": {"policyType": "iosXeLoopback", "adminState": True, "ip": loopback["ip"],
                                                            "description": loopback.get("description", "")}}}}]}
```

`Provisioner.phase_isn`:

```python
    def _policies(self, fabric: str, serial: str) -> list[dict]:
        return self.client.paged(f"/fabrics/{fabric}/policies", "policies", params={"switchId": serial})

    def _ensure_policy(self, fabric: str, serial: str, policy: dict) -> None:
        have = [p for p in self._policies(fabric, serial) if p.get("templateName") == policy["templateName"] and p.get("entityName") == policy["entityName"]]
        if not have:
            self._post(f"/fabrics/{fabric}/policies", {"policies": [policy]})

    def phase_isn(self) -> None:
        wan = self.topo.isn.wan
        if wan:
            fabric_obj = self.client.get(f"/fabrics/{wan.fabric}")
            if fabric_obj.get("management", {}).get("monitoredMode"):
                self._put(f"/fabrics/{wan.fabric}", merge_settings(fabric_obj, {"management": {"monitoredMode": False}}))
            wan_serial = self.serial(wan.hostname)
            loopbacks = self.client.get(f"/fabrics/{wan.fabric}/switches/{wan_serial}/interfaces") or {}
            names = {i.get("interfaceName") for i in loopbacks.get("interfaces", [])}
            if wan.loopback and f"Loopback{wan.loopback.get('id', 0)}" not in names:
                self._post(f"/fabrics/{wan.fabric}/switches/{wan_serial}/interfaces", loopback_interface(wan_serial, wan.loopback))
            if wan.bgp_router_id:
                self._ensure_policy(wan.fabric, wan_serial, router_id_policy(wan_serial, wan.bgp_router_id))
            self._ensure_policy(wan.fabric, wan_serial, cdp_run_policy(wan_serial))
            for intf in wan.cdp_interfaces:
                self._ensure_policy(wan.fabric, wan_serial, cdp_policy(wan_serial, intf))
        for link in self.topo.isn.links:
            have = self.client.paged("/links", "links", params={"fabricName": link.src_fabric})
            if any(h.get("srcSwitchName") == link.src and h.get("srcInterfaceName") == link.src_if for h in have):
                continue
            self._post("/links", link_payload(link, self.serial(link.src), self.serial(link.dst)))
        for name in sorted({item.dst_fabric for item in self.topo.isn.links} | ({wan.fabric} if wan else set())):
            self.config_deploy(name)
        if wan and not self.dry_run:
            time.sleep(30)
            left = self.pending(wan.fabric, wan_serial)
            print(f"{wan.hostname} pendingConfig after deploy: {len(left)} line(s)" + ("" if not left else " -- read /deploymentHistory"))
```

- [ ] **Step 3: Tests, lint, commit**

```bash
uv run pytest config/nd/provision/tests -q && flake8 config/nd/provision && mypy config/nd/provision/provision.py && black --check config/nd/provision
git add config/nd/provision && git commit -m "provision.py: ISN phase (WAN loopback/router-id/CDP, ebgpVrfLite links, deploy)"
```

---

### Task 12: `provision.py` - overlay and deploy phases

**Files:**

- Modify: `config/nd/provision/provision.py`, `tests/test_provision_payloads.py`

**Interfaces:**

- Produces: `attachment_payload(kind: str, att: dict, serial: str) -> dict` where kind is `vrf` or `network`.

- [ ] **Step 1: Failing test**

```python
from provision import attachment_payload


def test_network_attachment_payload():
    att = {"fabric": "SITE1", "network": "NET_2", "switch": "S1_TOR1", "vlan": 2, "interfaces": [{"mode": "access", "name": "Ethernet1/3"}]}
    assert attachment_payload("network", att, "SER") == {"attachments": [
        {"networkName": "NET_2", "switchId": "SER", "vlanId": 2, "interfaces": [{"mode": "access", "name": "Ethernet1/3"}], "attach": True}]}


def test_vrf_attachment_payload():
    body = attachment_payload("vrf", {"fabric": "SITE1", "vrf": "V1", "switch": "S1_LE1"}, "SER")
    assert body == {"attachments": [{"vrfName": "V1", "switchId": "SER", "attach": True}]}
```

- [ ] **Step 2: Implement**

```python
def attachment_payload(kind: str, att: dict, serial: str) -> dict:
    if kind == "vrf":
        return {"attachments": [{"vrfName": att["vrf"], "switchId": serial, "attach": True}]}
    return {"attachments": [{"networkName": att["network"], "switchId": serial, "vlanId": att["vlan"], "interfaces": att.get("interfaces", []), "attach": True}]}
```

```python
    def phase_overlay(self) -> None:
        for item in self.topo.overlay.vrfs:
            for fabric in item["fabrics"]:
                have = {v["vrfName"] for v in (self.client.get(f"/fabrics/{fabric}/vrfs") or {}).get("vrfs", [])} if not self.dry_run else set()
                if item["object"]["vrfName"] not in have:
                    self._post(f"/fabrics/{fabric}/vrfs", {"vrfs": [dict(item["object"], fabricName=fabric)]})
        for item in self.topo.overlay.networks:
            for fabric in item["fabrics"]:
                have = {n["networkName"] for n in (self.client.get(f"/fabrics/{fabric}/networks") or {}).get("networks", [])} if not self.dry_run else set()
                if item["object"]["networkName"] not in have:
                    self._post(f"/fabrics/{fabric}/networks", {"networks": [dict(item["object"], fabricName=fabric)]})
        touched: dict[str, set[str]] = {}
        for att in self.topo.overlay.vrf_attachments:
            serial = self.serial(att["switch"])
            self._post(f"/fabrics/{att['fabric']}/vrfAttachments", attachment_payload("vrf", att, serial))
            touched.setdefault(att["fabric"], set()).add(serial)
        for att in self.topo.overlay.network_attachments:
            serial = self.serial(att["switch"])
            self._post(f"/fabrics/{att['fabric']}/networkAttachments", attachment_payload("network", att, serial))
            touched.setdefault(att["fabric"], set()).add(serial)
        for fabric, serials in touched.items():
            self._post(f"/fabrics/{fabric}/vrfActions/deploy", {"switchIds": sorted(serials)})
            self._post(f"/fabrics/{fabric}/networkActions/deploy", {"switchIds": sorted(serials)})

    def phase_deploy(self) -> None:
        for fabric in self.topo.fabrics:
            self.config_deploy(fabric.name)
        if self.dry_run:
            return
        time.sleep(30)
        for fabric in self.topo.fabrics:
            for hostname, entry in self.fabric_switches(fabric.name).items():
                left = self.pending(fabric.name, entry["serialNumber"])
                print(f"{fabric.name}/{hostname}: pendingConfig {len(left)} line(s)")
```

(Attach calls are idempotent on ND: re-attaching an attached network is a no-op that returns 200.)

- [ ] **Step 3: Tests, lint, commit**

```bash
uv run pytest config/nd/provision/tests -q && flake8 config/nd/provision && mypy config/nd/provision/provision.py && black --check config/nd/provision
git add config/nd/provision && git commit -m "provision.py: overlay (VRF/network/attachments) and deploy phases"
```

---

### Task 13: Documentation and PR

**Files:**

- Create: `config/nd/provision/README.md`
- Modify: `README.md` (Topology section), `CLAUDE.md` (layout table + ND-config boundary note), `docs/nd4_fabrics_bringup.md` (pointer), `config/nexus9000v/README.md`

- [ ] **Step 1: `config/nd/provision/README.md`**

````markdown
# ND provisioning tool

Provisions one lab testbed (fabrics, MSD, switches, ISN links, overlay) into one Nexus Dashboard from a declarative
topology file, and snapshots/diffs ND state to prove two testbeds mirror each other. Replaces the ad-hoc REST steps that
used to live only in the `provision-isn` skill and `docs/nd4_fabrics_bringup.md`.

## Files

- `topology_nd421.yaml` / `topology_nd431.yaml` - the two testbeds (SITE1/SITE2/ISN/MSD on each controller); they differ only in hostnames and mgmt IPs
- `provision.py` - phased, idempotent, `--dry-run`
- `snapshot.py` - `dump` (read-only) and `diff` (normalized)
- `nd_client.py`, `topology.py` - library code; `tests/` - pytest for the pure parts

## Usage (on the lab host, prod env sourced)

```bash
source ~/repos/n9kv-kvm/env_prod/env.sh
cd ~/repos/n9kv-kvm
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase all --dry-run
uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20 --phase fabrics
# ... msd, switches (waits for discovery), isn, overlay, deploy
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421 --nd-ip 10.10.20.10
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431 --nd-ip 10.10.20.20
uv run config/nd/provision/snapshot.py diff ~/tmp/snap_nd421 ~/tmp/snap_nd431 \
  --map S1_BG1=S3_BG1 --map S1_SP1=S3_SP1 --map S1_LE1=S3_LE1 --map S1_LE2=S3_LE2 --map S1_LE3=S3_LE3 --map S1_LE4=S3_LE4 \
  --map S1_TOR1=S3_TOR1 --map S2_BG1=S4_BG1 --map S2_SP1=S4_SP1 --map S2_LE1=S4_LE1 --map WAN1=WAN2
```

## Gotchas carried over from ND 4.2.1

- External fabrics created via API come up with `management.monitoredMode: true`; the `isn` phase flips it, otherwise every deploy is silently a no-op.
- IOS-XE runs one BGP process: any stray `router bgp` on the WAN router other than the ISN ASN aborts the deploy mid-script.
- `GET /links` needs `fabricName`; policy lists page at 10 - the client always walks pages.
- ebgpVrfLite links put no IPs on parent interfaces; they appear on subinterfaces once a VRF is extended.
````

- [ ] **Step 2: `README.md` Topology section** - replace the "Three fabrics" bullets with two testbeds (ND 4.2.1: SITE1 = BG1, SP1, LE1-4, TOR1, H1; SITE2 = BG1,
  SP1, LE1, H1; ISN = WAN1; MSD. ND 4.3.1: the same with S3/S4/WAN2) and extend the mermaid graph with S1_LE2/S1_TOR1/S1_LE3/S1_LE4/WAN1 (already missing) plus a
  second `subgraph ND431` mirroring it. Run `pymarkdown scan README.md`.

- [ ] **Step 3: `CLAUDE.md`** - add rows for `config/8000v/` and `config/nd/provision/` to the layout table; in the "Architectural Notes" add:
  "**Two testbeds share one host and one mgmt segment.** SITE1/SITE2/WAN1/S1_H1/S2_H1 belong to ND 4.2.1 (10.10.20.10); SITE3/SITE4/WAN2/S3_H1/S4_H1 are their
  exact mirror under ND 4.3.1 (10.10.20.20, data on `BR_ND_DATA_14`), with identical fabric names, ASNs and pools. Only hostnames, sids and the
  third octet of the mgmt IPs (12 -> 14) differ. `9914-bridges.yaml` is the
  SITE3/SITE4 bridge set including their management bridge `BR_ND_DATA_14`." Update the `config/ansible/` row ("SITE1-SITE4") and the
  `config/nd/` row (mention provision/).

- [ ] **Step 4: `docs/nd4_fabrics_bringup.md`** - add under the title: "The steps below are now automated by `config/nd/provision/provision.py`
  (`--phase fabrics`, `msd`, `isn`); this page remains the GUI walk-through and the record of the API payloads."

- [ ] **Step 5: Lint, push, PR**

```bash
pymarkdown scan README.md CLAUDE.md docs/nd4_fabrics_bringup.md config/nd/provision/README.md
git add README.md CLAUDE.md docs/nd4_fabrics_bringup.md config/nd/provision/README.md config/nexus9000v/README.md
git commit -m "Document the ND 4.3.1 mirror testbed and the provisioning tool"
git push -u origin nd431-mirror-testbed
gh pr create --title "ND 4.3.1 mirror testbed (SITE3/SITE4 + WAN2) and ND provisioning tool" --fill
```

---

## Deployment runbook (manual, on glide-wired.laukapu.com; not part of the repo diff)

Order matters: bridges before VMs, ISOs before VMs, switches reachable before `--phase switches`, ISN links before the overlay.

- [ ] **R0. Re-instantiate ND 4.3.1 on `BR_ND_DATA_14`** (user decision 2026-09-08; the current instance on `BR_ND_DATA_12` was a throw-away)

```bash
virsh -c qemu:///system destroy nd.4.3.1.175.node1 && virsh -c qemu:///system undefine nd.4.3.1.175.node1
sudo rm -rf /iso2/nd/4.3.1.175            # disk1/disk2 of the throw-away instance (ND_INSTALL_DIR in the script)
cd ~/repos/n9kv-kvm/config/nd && ./nd-4-3-1-175-node1.sh && virsh -c qemu:///system console nd.4.3.1.175.node1
```

CLI bootstrap: mgmt 10.10.20.20/16 via 10.10.0.1 (unchanged). Web/`nd-bootstrap` phase: data network `192.168.14.14/24` (ND 4.2.1 is `192.168.12.14/24`),
gateway 192.168.14.1, persistent data IPs `192.168.14.30,192.168.14.31,192.168.14.32`, persistent mgmt IPs `10.10.20.60-.62`. Update
`~/repos/nd-bootstrap/nd_bootstrap_4.3.1.175.vnode1.yaml` accordingly (separate repo). Wait for the UI, then continue.

- [ ] **R1. Pre-flight**

```bash
cd ~/repos/n9kv-kvm && git checkout nd431-mirror-testbed && git pull
free -g | head -2                                   # need ~190 GB free for 11 n9kv + WAN2 + 2 containers; launch site by site otherwise
virsh -c qemu:///system domiflist nd.4.3.1.175.node1 | grep BR_ND_DATA_14      # R0 done: ND 4.3.1 data NIC is on BR_ND_DATA_14
ip -br addr show BR_ND_DATA_14                                                 # host is 192.168.14.2/24
ping -c1 -W2 192.168.14.14 >/dev/null && echo "ND 4.3.1 data IP up"                # ND 4.3.1 node data IP
for o in 131 132 141 142 151 152 153 154 155 161 171 172 112; do ping -c1 -W1 192.168.14.$o >/dev/null && echo "IN USE: .$o"; done; echo "sweep done"
```

- [ ] **R2. Bridges**

```bash
sudo cp config/bridges/netplan/9914-bridges.yaml /etc/netplan/9914-bridges.yaml && sudo chmod 600 /etc/netplan/9914-bridges.yaml
sudo netplan apply
sudo ./config/bridges/bridges_config_ovs.sh
sudo ovs-vsctl list-br | grep -E 'S3|S4|WAN_S3|WAN_S4' | wc -l          # expected 16
sudo ovs-vsctl list-br | grep -E 'S4_LE2|S4_LE3|LE._H2' ; echo "(expected: no output; if netplan left them, sudo ovs-vsctl del-br <name>)"
```

- [ ] **R3. Day-0 ISOs and VMs**

```bash
source env_prod/env.sh
cd config/nexus9000v && sudo -E python3 startup_config.py --all && bash site3.sh && bash site4.sh && cd -
cd config/8000v && sudo -E python3 startup_config.py WAN2.yaml && sudo python3 8000v.py --config WAN2.yaml && cd -
./config/nexus9000v/list_n9kv.sh | grep -c 'S3_\|S4_\|WAN2'          # expected 12
```

Wait for POAP (several minutes; `./config/nexus9000v/con_s3_sp1` to watch), then:

```bash
for o in 133 134 143 144 163 181 182 183 184 185 113; do ping -c1 -W2 192.168.12.$o >/dev/null && echo "up .$o" || echo "DOWN .$o"; done
```

- [ ] **R4. Containers**

```bash
cd config/containers
sudo python3 main.py --config container_configs_access_mode.yaml S3_H1
sudo python3 main.py --config container_configs_access_mode.yaml S4_H1
sudo virsh -c lxc:/// start S3_H1 && sudo virsh -c lxc:/// start S4_H1
ping -c2 192.168.14.171 && ping -c2 192.168.14.172; cd -
```

- [ ] **R5. Provision ND 4.3.1** (each phase, dry-run first)

```bash
P="uv run config/nd/provision/provision.py --topology config/nd/provision/topology_nd431.yaml --nd-ip 10.10.20.20"
$P --phase fabrics --dry-run && $P --phase fabrics
$P --phase msd
$P --phase switches            # waits for discovery; then Recalculate & Deploy per fabric
$P --phase isn
$P --phase overlay
$P --phase deploy              # every pendingConfig should print 0 line(s)
```

If `switches` times out: check `Preserve Config` semantics did not change on 4.3.1 (GUI Add Switches), and that each switch answers SSH as `admin`.
If a deploy "completes" but pending config remains: `GET /fabrics/ISN/deploymentHistory` for the per-command CLI responses (stray `router bgp`, monitored mode).

- [ ] **R6. Prove the mirror**

```bash
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd421 --nd-ip 10.10.20.10
uv run config/nd/provision/snapshot.py dump ~/tmp/snap_nd431 --nd-ip 10.10.20.20
uv run config/nd/provision/snapshot.py diff ~/tmp/snap_nd421 ~/tmp/snap_nd431 --map S1_BG1=S3_BG1 --map S1_SP1=S3_SP1 --map S1_LE1=S3_LE1 \
  --map S1_LE2=S3_LE2 --map S1_LE3=S3_LE3 --map S1_LE4=S3_LE4 --map S1_TOR1=S3_TOR1 --map S2_BG1=S4_BG1 --map S2_SP1=S4_SP1 --map S2_LE1=S4_LE1 --map WAN1=WAN2
# data plane: from S3_H1, ping S4_H1 across the overlay
ssh root@192.168.14.171 'ping -c3 192.0.1.172'
```

Expected: an empty diff apart from ND-version-specific fields (record any such field in `snapshot.VOLATILE_KEYS` with a comment), and 3 replies.

- [ ] **R7. Host housekeeping** - add `site3.sh`, `site4.sh`, `WAN2.yaml` and `S3_H1 S4_H1` to `~/lab_recover.sh`; update the `provision-isn` skill in `~/.claude`
  to point at `config/nd/provision/`.

## Follow-ups (out of scope, noted for later PRs)

- Delete `config/nexus9000v/cfg/` (stale generated configs with an embedded password; nothing produces or reads them).
- `S1_H1.netplan.yaml`/`S2_H1.netplan.yaml` carry IPv6 EUI-64 addresses derived from the pre-rename MACs (`41ff`, `52ff`); regenerate from `00:00:71`/`72`.
- `config/ansible/dynamic_inventory.py` defines `SITE3_FABRIC`/`SITE4_FABRIC` that are never exported; with spec D3 they are dead and can go.
