# Golden Drift and Restore Implementation Plan

<!-- pyml disable line-length,blanks-around-fences,fenced-code-language -->

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `golden.py drift|restore|adopt` compares one ND controller against its topology file, prints the drift, and after confirmation pushes the lab back (adopting or deleting extras per item).

**Architecture:** The topology yaml gains four sections (`links`, `generated_links`, `interfaces`, `defaults`) and stays the only golden. New flat modules next to `provision.py`: `golden_live.py` reads ND into per-fabric structures, `golden_drift.py` turns golden + live into a list of `Drift` records (pure, fully unit-tested against the committed snapshot dumps), `golden_apply.py` executes the chosen operations through `Provisioner` and deploys, `golden_adopt.py` writes adoptions back into the yaml with comments preserved, `golden.py` is the CLI and the prompts.

**Tech Stack:** Python 3.13, `requests` via `nd_client.NDClient`, `ruamel.yaml` (new) for round-trip yaml, pytest with the existing `StubClient` pattern, black/flake8/mypy at line length 169.

**Spec:** `docs/superpowers/specs/2026-10-30-golden-drift-design.md`

## Global Constraints

- Line length 169 for black, flake8, pylint; `pymarkdown` clean on touched Markdown; mypy clean on new modules.
- Flat package: modules in `config/nd/provision/`, imported by bare name (tests add the dir to `sys.path` via `tests/conftest.py`).
- Never commit `env_prod/`; credentials only via `NDCredentials.from_env`.
- One invocation targets one `--nd-ip`; nothing is written to ND before the user's confirmation (or `--yes`).
- ND-generated links are never `PUT` and never deleted; a switch is never removed from a fabric; external-fabric switches (`coreRouter`) are out of scope for interface classes.
- Recalculate & Deploy = `Provisioner.config_deploy()` (configSave then deploy); groups after their member fabrics.
- The two topology files must still differ only in hostnames and management IPs after bootstrap.
- PR workflow on branch `golden-drift`; commit per task.

## Review Focus

1. ND answering HTTP 500 "Error communicating with fabric controller" or an empty fabric list while booting: `drift` must exit 3 with that message, not report every object as missing (Task 2 test `test_read_live_fails_loud_when_fabric_controller_is_down`).
2. A cross-fabric link (BGW DCI, ISN) appears in both fabrics' `/links` lists: it must be counted once (Task 3 test `test_cross_fabric_link_is_reported_once`).
3. `restore --yes` with extras present and no `--extras`: exit 2 and no write at all (Task 8 test `test_yes_without_extras_flag_refuses_when_extras_exist`).
4. An interface policy-type change refused by ND while a network is attached: apply detaches, re-PUTs, re-attaches, and the 207 per-item results are checked (Task 6 test `test_put_interface_retries_through_detach_on_policy_type_refusal`).
5. Interface names in URLs: `Ethernet1/3` must be sent as `Ethernet1%2F3` (Task 2 test `test_interface_paths_encode_the_slash`).

---

### Task 0: Branch, dependency, committed golden snapshots

**Files:**

- Modify: `pyproject.toml` (dependencies)
- Create: `config/nd/provision/golden/nd421/*.json`, `config/nd/provision/golden/nd431/*.json`
- Modify: `.gitignore` only if it excludes `*.json` (it does not today)

- [ ] **Step 1: Branch** `git checkout -b golden-drift` from `main` (after PR #47's merge).
- [ ] **Step 2: Add `ruamel.yaml>=0.18.6` to `[project].dependencies`** in `pyproject.toml`; run `uv lock` and `uv run python -c "import ruamel.yaml"` → no error.
- [ ] **Step 3: Dump both controllers** on glide (read-only):
  `uv run config/nd/provision/snapshot.py dump ~/tmp/golden_nd421 --nd-ip 10.10.20.10` and `... golden_nd431 --nd-ip 10.10.20.20`; `scp -r` both to `config/nd/provision/golden/`.
- [ ] **Step 4: Verify no secrets:** `grep -rl -i -E "passw|secret|token" config/nd/provision/golden/` → no files. If any, strip the key in `snapshot.VOLATILE_KEYS` and redump.
- [ ] **Step 5: Verify the dumps describe the restored lab:** `python3 -c` over `golden/nd421/links_SITE1.json` → exactly 5 links with `configData.policyType == "numbered"` whose endpoints include `S1_SP1`; `golden/nd421/links_MSD.json` → one `multisiteUnderlay`. Same counts for `nd431` with `S3_SP1`.
- [ ] **Step 6: Commit** `git add pyproject.toml uv.lock config/nd/provision/golden && git commit -m "golden: ruamel.yaml dependency and the 2026-10-30 reference snapshots of both controllers"`.

### Task 1: Topology schema for golden

**Files:**

- Modify: `config/nd/provision/topology.py` (dataclasses at 13-30, `load()` at 178-192, `_validate()` at 131)
- Test: `config/nd/provision/tests/test_topology.py`

**Interfaces:**

- Produces:

  ```python
  @dataclass(frozen=True)
  class FabricLink:  src: str; src_if: str; dst: str; dst_if: str; policy: str; src_ip: str; dst_ip: str; inputs: dict = field(default_factory=dict)
  @dataclass(frozen=True)
  class GeneratedLink:  src: str; src_if: str; dst: str; dst_if: str; policy: str; owner: str
  @dataclass(frozen=True)
  class InterfaceIntent:  switch: str; interface: str; policy: str; type: str = "ethernet"; description: str = ""; inputs: dict = field(default_factory=dict)
  class Fabric:  # new fields, all default-empty
      links: list[FabricLink]; generated_links: list[GeneratedLink]; interfaces: list[InterfaceIntent]; defaults: dict[str, dict]
  TOOL_LINK_POLICIES = {"numbered", "unnumbered", "ebgpVrfLite"}
  GENERATED_LINK_POLICIES = {"multisiteUnderlay", "multisiteOverlay", "iosXeNumbered"}
  def endpoint_key(a: str, a_if: str, b: str, b_if: str) -> tuple[tuple[str, str], tuple[str, str]]  # sorted pair, direction-free
  ```

- [ ] **Step 1: Write the failing tests** in `tests/test_topology.py`:

```python
  def test_load_reads_links_generated_links_interfaces_and_defaults(tmp_path):
      # yaml with one SITE1 fabric: links [S1_SP1 Ethernet1/2 <-> S1_LE1 Ethernet1/1 numbered 10.14.0.5/10.14.0.6],
      # generated_links [S1_BG1 Ethernet1/1 <-> S2_BG1 Ethernet1/1 multisiteUnderlay owner MSD],
      # interfaces [S1_TOR1 Ethernet1/3 accessHost "S1_H1 host port"], defaults {spine: {policyType: routedHost, adminState: false}}
      topo = load(path)
      f = topo.fabrics[0]
      assert f.links[0] == FabricLink("S1_SP1", "Ethernet1/2", "S1_LE1", "Ethernet1/1", "numbered", "10.14.0.5", "10.14.0.6")
      assert f.generated_links[0].owner == "MSD" and f.interfaces[0].type == "ethernet" and f.defaults["spine"]["policyType"] == "routedHost"
  def test_shipped_files_load_with_empty_golden_sections():  # until Task 9 bootstraps them
      assert load(HERE / "topology_nd421.yaml").fabrics[0].links == []
  def test_validate_rejects_unknown_link_policy_and_unknown_endpoint(tmp_path):  # policy "foo" -> ValueError mentioning "policy"; dst "S9_X" -> ValueError mentioning "S9_X"
  def test_validate_requires_link_ips_for_numbered(tmp_path):  # missing src_ip -> ValueError
  def test_endpoint_key_is_direction_free():
      assert endpoint_key("S1_LE1", "Ethernet1/1", "S1_SP1", "Ethernet1/2") == endpoint_key("S1_SP1", "Ethernet1/2", "S1_LE1", "Ethernet1/1")
  ```

- [ ] **Step 2: Run** `uv run pytest config/nd/provision/tests/test_topology.py -q` → the new tests fail on import/attribute errors.
- [ ] **Step 3: Implement** the dataclasses, the two policy sets, `endpoint_key`, the four new `Fabric` fields, their parsing in `load()` (`FabricLink(**item)` etc.), and in `_validate()`: link/interface endpoints must be golden switches (generated-link endpoints may be in any golden fabric), `policy` of a `FabricLink` in `TOOL_LINK_POLICIES`, of a `GeneratedLink` in `GENERATED_LINK_POLICIES`, `owner` a golden fabric or group name, `src_ip`/`dst_ip` non-empty for `numbered`.
- [ ] **Step 4: Run** the file → PASS; `uv run pytest config/nd/provision/tests -q` → all green.
- [ ] **Step 5: Commit** `git add config/nd/provision/topology.py config/nd/provision/tests/test_topology.py && git commit -m "topology: links, generated_links, interfaces and defaults sections for the golden baseline"`.

### Task 2: Live-state reader

**Files:**

- Create: `config/nd/provision/golden_live.py`
- Test: `config/nd/provision/tests/test_golden_live.py`

**Interfaces:**

- Consumes: `NDClient.get/post/paged` (`nd_client.py`), `Topology`.
- Produces:

```python
  @dataclass
  class LiveFabric:
      name: str; category: str                      # "fabric" | "fabricGroup"
      settings: dict                                # the GET /fabrics/{name} body
      switches: dict[str, dict]                     # hostname -> switch object (serialNumber, switchRole, ...)
      links: list[dict]                             # GET /links?fabricName=
      interfaces: dict[str, list[dict]]             # hostname -> GET /fabrics/{f}/switches/{sn}/interfaces
      vrfs: list[dict]; networks: list[dict]
      vrf_attachments: list[dict]; network_attachments: list[dict]   # the /query POST results, attach==True only
      vpc_pairs: list[dict]; tor_associations: list[dict]
  class LiveReadError(RuntimeError): ...
  def read_live(client: NDClient, topo: Topology) -> dict[str, LiveFabric]   # keyed by name; every golden fabric and group
  def read_live_from_snapshot(snapshot_dir: Path, topo: Topology) -> dict[str, LiveFabric]   # same shape from a snapshot.py dump (tests, offline drift)
  def free_ports(live: LiveFabric, hostname: str, all_links: list[dict]) -> list[dict]
  def interface_path(fabric: str, serial: str, interface: str) -> str   # "/fabrics/{f}/switches/{sn}/interfaces/Ethernet1%2F3"
  ```

`free_ports`: physical interfaces (`interfaceType == "ethernet"`, name not starting with `mgmt`) whose `(hostname, interfaceName)` is not an endpoint of any link in `all_links` and whose `operData.portChannelId` is -1.

- [ ] **Step 1: Write the failing tests** (data from `config/nd/provision/golden/nd421/`):

  ```python
  def test_read_live_from_snapshot_loads_every_golden_fabric_and_group():
      live = read_live_from_snapshot(GOLDEN / "nd421", load(HERE / "topology_nd421.yaml"))
      assert set(live) == {"SITE1", "SITE2", "ISN", "CAMPUS1", "MSD"} and live["MSD"].category == "fabricGroup"
      assert live["SITE1"].switches["S1_SP1"]["switchRole"] == "spine" and len(live["SITE1"].interfaces["S1_SP1"]) > 40
  def test_free_ports_exclude_link_endpoints_and_port_channel_members():
      # S1_SP1 Ethernet1/1-5 are numbered-link endpoints; S1_LE1 Ethernet1/2 is a Po500 member, Ethernet1/3 a Po1 member
      names = {p["interfaceName"] for p in free_ports(live["SITE1"], "S1_SP1", all_links)}
      assert "Ethernet1/1" not in names and "Ethernet1/6" in names
      assert not {"Ethernet1/1", "Ethernet1/2", "Ethernet1/3"} & {p["interfaceName"] for p in free_ports(live["SITE1"], "S1_LE1", all_links)}
  def test_interface_paths_encode_the_slash():
      assert interface_path("SITE1", "SN1", "Ethernet1/3") == "/fabrics/SITE1/switches/SN1/interfaces/Ethernet1%2F3"
  def test_read_live_fails_loud_when_fabric_controller_is_down():
      # StubClient.get("/fabrics") raises RuntimeError("HTTP 500 Error communicating with fabric controller")
      with pytest.raises(LiveReadError, match="fabric controller"): read_live(client, topo)
  def test_read_live_fails_loud_when_a_golden_fabric_is_missing():  # /fabrics answers [] -> LiveReadError naming SITE1
  ```

- [ ] **Step 2: Run** → ImportError.
- [ ] **Step 3: Implement** `golden_live.py`: `read_live` issues the same reads as `snapshot.dump` (reuse its endpoint list; `_fetch`-style tolerance is NOT wanted here — any HTTP error raises `LiveReadError` with the ND message), `read_live_from_snapshot` maps the dump file names (`links_{f}.json`, `interfaces_{f}_{host}.json`, …) to the same structure.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `"golden: live-state reader (ND and snapshot-backed)"`.

### Task 3: Drift model and link classes

**Files:**

- Create: `config/nd/provision/golden_drift.py`
- Test: `config/nd/provision/tests/test_golden_drift.py`

**Interfaces:**

- Produces:

  ```python
  Kind = Literal["missing", "different", "extra"]
  @dataclass(frozen=True)
  class Op:  action: str; fabric: str; method: str; path: str; body: Any   # action in {"put_link","clear_link","put_interface","reset_interface","delete_interface","attach","detach","create_vrf","create_network","delete_vrf","delete_network","pair_vpc","unpair_vpc","pair_tor","unpair_tor","add_switch","set_role","put_settings","deploy_owner"}
  @dataclass(frozen=True)
  class Adoption:  section: tuple[str, ...]; entry: dict      # e.g. ("fabrics", "SITE1", "links"), {src:..., ...}
  @dataclass(frozen=True)
  class Drift:  cls: str; fabric: str; kind: Kind; subject: str; golden: str; live: str; fix: Op | None; delete: Op | None; adopt: Adoption | None
  def numbered_link_body(link_obj: dict, golden: FabricLink) -> dict      # the PUT body (8 base fields + configData), descriptions name their own side
  def drift_links(fabric: Fabric, live: dict[str, LiveFabric], seen: set) -> list[Drift]
  def drift_generated_links(fabric: Fabric, live: dict[str, LiveFabric]) -> list[Drift]
  def format_report(drifts: list[Drift]) -> str    # "SITE1 links      MISSING policy  S1_SP1 Ethernet1/2 <-> S1_LE1 Ethernet1/1   golden=numbered 10.14.0.5/.6  live=none"
  ```

  Link matching is by `endpoint_key`; `seen` carries keys already reported so a cross-fabric link is reported once. `fix` for a missing/different tool link = `Op("put_link", fabric, "PUT", f"/links/{linkId}", numbered_link_body(...))`; `delete` for an extra tool-ownable link = `Op("clear_link", ..., "PUT", f"/links/{linkId}", {8 base fields, "configData": None})`; `adopt` = `Adoption(("fabrics", f, "links"), {...})`. Generated links: `fix = Op("deploy_owner", owner, "", "", None)`, never `delete`, never `adopt` via extras.

- [ ] **Step 1: Write the failing tests** (golden snapshot as live; a copy with mutations):

```python
  def test_no_link_drift_on_the_golden_lab():          # topology with the 5 SITE1 links == snapshot -> []
  def test_missing_policy_yields_put_link_with_numbered_body():   # set configData None on LINK-UUID-6000 -> one MISSING; fix.path == "/links/LINK-UUID-6000"; body["configData"]["templateInputs"]["srcIp"] == "10.14.0.5"; srcInterfaceDescription == "connected-to-S1_SP1-Ethernet1/2"
  def test_different_ip_yields_different():            # live srcIp 10.14.0.9 -> kind "different", golden/live strings contain both IPs
  def test_extra_tool_link_offers_adopt_and_clear():    # live ebgpVrfLite on S1_LE3 Eth1/4 not in golden -> extra; delete.body["configData"] is None; adopt.section == ("fabrics","SITE1","links")
  def test_cross_fabric_link_is_reported_once():        # BGW DCI link listed in SITE1 and SITE2 -> len == 1 across both fabrics
  def test_generated_link_missing_policy_fixes_via_owner_deploy():   # strip multisiteUnderlay -> fix.action == "deploy_owner", fix.fabric == "MSD", delete is None
  def test_discovered_links_without_policy_are_not_extras():          # peer-link / ToR port-channel rows -> not reported
  def test_format_report_lines_are_stable_and_hostname_based():       # exact line from the spec
  ```

- [ ] **Step 2: Run** → ImportError. **Step 3: Implement** the module. **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"golden: drift model, link and generated-link classes"`.

### Task 4: Interface classes (physical free ports and logical interfaces)

**Files:**

- Modify: `config/nd/provision/golden_drift.py`
- Test: `config/nd/provision/tests/test_golden_drift.py`

**Interfaces:**

- Produces:

  ```python
  COMPARED_INPUTS = ("adminState", "mode", "accessVlan", "allowedVlans", "nativeVlan", "description", "mtu")
  GENERATED_LOGICAL = {"port-channel500", "port-channel1"}     # plus any interface whose name matches r"Ethernet\d+/\d+\.\d+" (link subinterfaces)
  def interface_body(serial: str, intent: InterfaceIntent, fabric_defaults: dict) -> dict     # PUT body as in Provisioner._ensure_access_port
  def default_body(serial: str, interface: str, role_default: dict) -> dict
  def drift_interfaces(fabric: Fabric, live: dict[str, LiveFabric], all_links: list[dict]) -> list[Drift]
  ```

  Rules: explicit `interfaces:` entries → missing/different by `policyType` + `COMPARED_INPUTS` subset (`fix` = `put_interface`). Free physical ports (Task 2 `free_ports`) not matching the role default (same comparison) → `extra` with `delete` = `reset_interface` (PUT `default_body`) and `adopt` into `("fabrics", f, "interfaces")`. Logical interfaces (`interfaceType` in `{"portChannel", "vpc", "subInterface", "svi"}`) not in golden and not in `GENERATED_LOGICAL` → `extra` with `delete` = `delete_interface` (DELETE `interface_path`) and `adopt`. Switches whose golden role is `coreRouter` are skipped.

- [ ] **Step 1: Write the failing tests:**

```python
  def test_no_interface_drift_on_the_golden_lab():                 # with the S1_TOR1/S2_LE1 host ports in golden and the captured defaults
  def test_explicit_port_different_reports_compared_inputs_only():  # live S1_TOR1 Eth1/3 trunkHost allowedVlans none -> "different", live string contains "trunkHost" and "allowedVlans=none"; a differing "ptp" key alone -> no drift
  def test_free_port_with_description_residue_is_extra_with_reset():  # S1_BG1 Ethernet1/5 description "test" -> extra; delete.body policyType == "routedHost"; adopt.entry == {switch:"S1_BG1", interface:"Ethernet1/5", policy:"routedHost", description:"test"}
  def test_link_endpoints_and_port_channel_members_are_never_extra():  # mutate S1_SP1 Eth1/2 and S1_LE1 Eth1/2 descriptions -> no interface drift
  def test_extra_vpc_offers_real_delete():                          # add an interface {interfaceName:"vpc200", interfaceType:"vpc"} on S1_LE1 -> extra; delete.method == "DELETE"; path ends "/interfaces/vpc200"
  def test_generated_logical_interfaces_are_ignored():              # port-channel500, port-channel1, Ethernet1/3.2 -> no drift
  def test_core_router_switches_are_skipped():                      # WAN1 interfaces never produce drift
  ```

- [ ] **Step 2: Run** → fail. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"golden: interface drift (free physical ports, logical interfaces)"`.

### Task 5: Overlay, pairs, switches and settings classes; `compute()`

**Files:**

- Modify: `config/nd/provision/golden_drift.py`
- Test: `config/nd/provision/tests/test_golden_drift.py`

**Interfaces:**

- Produces:

  ```python
  def drift_overlay(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]     # vrfs, networks, vrf/network attachments
  def drift_pairs(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]       # vpc_pairs, tor_pairs
  def drift_switches(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]    # membership and role; extra switch has delete None
  def drift_settings(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]    # golden subset vs live; fix = put_settings with merge_settings()
  def compute(topo: Topology, live: dict[str, LiveFabric]) -> list[Drift]           # all classes, stable order: settings, switches, links, generated_links, interfaces, vrfs, networks, attachments, pairs
  ```

  Attachments compare `attach`, `vlanId` and the `interfaces` list; VRF/network objects compare the golden `object` keys only; MSD-propagated VRF/network copies in SITE1/SITE2 are not extras. Fix/delete bodies reuse `provision.attachment_payload`, `vpc_pair_payload`, `tor_associate_payload` and the POST paths `phase_overlay`/`phase_vpc`/`phase_tor` use today.

- [ ] **Step 1: Write the failing tests:** `test_no_overlay_pair_switch_or_settings_drift_on_the_golden_lab`, `test_missing_tor_attachment_fixes_with_attach_payload_including_interfaces`, `test_extra_network_offers_adopt_or_delete_after_detach` (delete op list: detach everywhere, then DELETE network), `test_msd_propagated_network_in_site1_is_not_extra`, `test_wrong_switch_role_fixes_with_set_role`, `test_extra_switch_is_reported_with_no_delete`, `test_settings_key_outside_golden_is_not_drift`, `test_compute_orders_classes_stably`.
- [ ] **Step 2: Run** → fail. **Step 3: Implement.** **Step 4: Run** → PASS; also `test_no_*` tests all pass together on both `golden/nd421` and `golden/nd431` (parametrize).
- [ ] **Step 5: Commit** `"golden: overlay, pairing, switch and settings drift; compute()"`.

### Task 6: Applier

**Files:**

- Create: `config/nd/provision/golden_apply.py`
- Test: `config/nd/provision/tests/test_golden_apply.py`

**Interfaces:**

- Consumes: `Provisioner._put/_post/_read_one/_query/config_deploy`, `NDClient.delete`, `Op`.
- Produces:

```python
  class ApplyError(RuntimeError): ...
  class Applier:
      def __init__(self, prov: Provisioner) -> None
      def apply(self, ops: list[Op]) -> set[str]            # returns touched fabric/group names; raises ApplyError on the first failed op (HTTP error or a 207 item with status != "success")
      def deploy(self, touched: set[str], topo: Topology) -> None   # config_deploy every touched fabric in topology order, then every touched group; "deploy_owner" ops only add to touched
  ```

Ordering inside `apply`: settings, switches, links, interfaces, vrfs, networks, attachments, pairs; deletes before creates within a class. `put_interface` whose PUT fails with a message containing "Policy type change" → detach every network attached on that port (`networkAttachments` with `attach: false`, then `networkActions/deploy`), retry the PUT, re-attach with the original interfaces list, `networkActions/deploy`.

- [ ] **Step 1: Write the failing tests** (StubClient recording calls; `monkeypatch` `time.sleep`):
  `test_apply_runs_ops_in_class_order_and_returns_touched`, `test_apply_stops_at_first_failure_with_apply_error` (207 with a failed item), `test_put_interface_retries_through_detach_on_policy_type_refusal` (first PUT raises RuntimeError("HTTP 400 Policy type change ..."); assert the call sequence detach → deploy → PUT → attach → deploy), `test_deploy_orders_members_before_groups` (touched {"MSD","SITE1"} → SITE1 configSave/deploy before MSD), `test_dry_run_writes_nothing` (Provisioner(dry_run=True) → no POST/PUT/DELETE on the client).
- [ ] **Step 2: Run** → fail. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"golden: applier with ordered ops, policy-type retry and member-before-group deploy"`.

### Task 7: Adopt writer

**Files:**

- Create: `config/nd/provision/golden_adopt.py`
- Test: `config/nd/provision/tests/test_golden_adopt.py`

**Interfaces:**

- Produces:

  ```python
  def write_adoptions(path: Path, adoptions: list[Adoption]) -> int     # returns entries written; ruamel round-trip; creates the section if absent; dedupes by endpoint_key / (switch, interface) / object name
  def bootstrap_adoptions(topo: Topology, live: dict[str, LiveFabric], drifts: list[Drift]) -> list[Adoption]
  ```

  `bootstrap_adoptions` = every `Drift.adopt` plus, per fabric: `generated_links` entries for live links whose policy is in `GENERATED_LINK_POLICIES` (owner: the group containing the fabric for `multisite*`, the fabric for `iosXeNumbered`), and a `defaults` map built from the first free port of each golden role (`policyType` + `COMPARED_INPUTS`).

- [ ] **Step 1: Write the failing tests:** `test_write_adoptions_preserves_comments_and_appends_entries` (copy `topology_nd421.yaml` to tmp; write one link + one interface; the file still contains the comment `# merged into the fabric object` and `yaml.safe_load` shows the entries; a second identical call returns 0), `test_write_adoptions_creates_missing_sections`, `test_bootstrap_adoptions_capture_generated_links_and_defaults` (from `golden/nd421`: one `generated_links` entry with policy `multisiteUnderlay`, owner `MSD`; `defaults["spine"]["policyType"] == "routedHost"`, `defaults["leaf"]["policyType"] == "trunkHost"`).
- [ ] **Step 2: Run** → fail. **Step 3: Implement** with `ruamel.yaml.YAML()` (`preserve_quotes=True`, `indent(mapping=2, sequence=4, offset=2)`), flow-style entries like the existing file.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `"golden: adopt writer (round-trip yaml) and bootstrap adoptions"`.

### Task 8: CLI `golden.py`

**Files:**

- Create: `config/nd/provision/golden.py`
- Test: `config/nd/provision/tests/test_golden_cli.py`

**Interfaces:**

- Produces:

  ```python
  def run_drift(topo: Topology, live: dict[str, LiveFabric], out: Callable[[str], None]) -> list[Drift]
  def choose_extras(drifts: list[Drift], mode: str | None, ask: Callable[[str], str]) -> tuple[list[Adoption], list[Op]]   # mode in {None,"adopt","delete","skip"}; prompt "[a]dopt / [d]elete / [s]kip / [A]ll adopt / [D]ll delete"
  def run_restore(args, topo, live, prov, ask, out) -> int
  def main(argv: list[str] | None = None) -> int     # exit codes: 0 ok / no drift, 1 drift (drift cmd), 2 refused (bad flags, user said no), 3 live read failed, 4 apply failed
  ```

  Subcommands and flags exactly as the spec: `drift|restore|adopt --topology --nd-ip`, `restore [--yes] [--extras adopt|delete|skip] [--no-deploy]`, `adopt [--classes ...]`, plus `--snapshot <dir>` on `drift` for offline use. Confirmation text: `Apply {n} create/overwrite operation(s) to {nd_ip}? [y/N]`. Final line: `restore: {n_ops} applied, {n_adopt} adopted, {n_del} deleted; deployed {fabrics}. Now run the restore-lab-topologies Step 4.6 fabric checks and container pings.`

- [ ] **Step 1: Write the failing tests** (inject `ask`/`out`, stub Provisioner):
  `test_drift_exits_1_with_report_and_0_when_clean`, `test_restore_without_yes_asks_and_applies_nothing_on_no`, `test_restore_prompts_per_extra_and_honours_answers`, `test_yes_without_extras_flag_refuses_when_extras_exist` (exit 2, no PUT/POST), `test_extras_delete_flag_takes_every_delete_op`, `test_adoptions_are_written_before_any_push` (call order on a recording stub), `test_live_read_error_exits_3`, `test_no_deploy_skips_config_deploy`.
- [ ] **Step 2: Run** → fail. **Step 3: Implement** (`argparse`, `input()` as the default `ask`, `print` as `out`).
- [ ] **Step 4: Run** → PASS; `uv run black --check config/nd/provision && uv run flake8 config/nd/provision && uv run mypy config/nd/provision/golden*.py` clean.
- [ ] **Step 5: Commit** `"golden: drift/restore/adopt CLI"`.

### Task 9: Bootstrap golden on both controllers and lock the mirror

**Files:**

- Modify: `config/nd/provision/topology_nd421.yaml`, `config/nd/provision/topology_nd431.yaml`
- Test: `config/nd/provision/tests/test_topology.py` (mirror test)

- [ ] **Step 1: Offline first:** `uv run config/nd/provision/golden.py adopt --topology config/nd/provision/topology_nd421.yaml --snapshot config/nd/provision/golden/nd421` (add `--snapshot` to `adopt` if Task 8 did not; same for nd431). Review `git diff`: 5 `links`, 1 `generated_links`, 2 `interfaces`, `defaults` per VXLAN fabric; no residue you do not recognise. Anything unexpected is a question for the user before committing.
- [ ] **Step 2: Write the mirror test** `test_shipped_topologies_differ_only_in_hostnames_and_mgmt_ips`: load both, replace `S1_→S3_`, `S2_→S4_`, `WAN1→WAN2`, `C1_→C3_`, `192.168.12.`→`192.168.14.` in a dump of nd421, assert equal to nd431 as plain dicts. Run → PASS (fix the files if not).
- [ ] **Step 3: On glide, prod env sourced:** `golden.py drift` against 10.10.20.10 and 10.10.20.20 → both exit 0. If not, the report says what the snapshot and the live lab disagree on; resolve with the user.
- [ ] **Step 4: Deliberate drift proof (4.2.1 only, with the user present):** flip `S1_TOR1 Ethernet1/3` to trunkHost via the detach/PUT path the applier uses, run `drift` (one DIFFERENT line), run `restore` (confirm y), then `drift` → 0, and the S1_H1 → 192.0.1.1 ping from the skill's Step 4.5 succeeds.
- [ ] **Step 5: Commit** `"golden: bootstrap both topology files from the 2026-10-30 lab state; mirror test"`.

### Task 10: README, skill and PR

**Files:**

- Modify: `config/nd/provision/README.md`, `CLAUDE.md` (table row for `config/nd/provision/`)
- Modify: `~/.claude/skills/restore-lab-topologies/SKILL.md` (not in repo)

- [ ] **Step 1: README:** a "Golden baseline" section: the three subcommands with the usage lines, exit codes, the extras rule, "ND-generated links are never deleted", "removing a switch is never automatic", "run only when no tests are running", and that `golden/` holds reference snapshots the tool does not read. `pymarkdown scan` clean.
- [ ] **Step 2: Skill:** Step 4 gets item 7: `golden.py drift` on both controllers is the last check; the Step 4.6 manual recipes become "background; `golden.py restore` does this"; precondition line "only when no tests are running". Remove the `~/tmp/site1_links.py` reference and delete that file on glide.
- [ ] **Step 3: Full verification:** `uv run pytest config/nd/provision/tests -q` green; black/flake8/mypy clean; `git diff main --stat` reviewed.
- [ ] **Step 4: PR** `gh pr create --base main --head golden-drift` with the spec link, the bootstrap diff summary, the drift-proof transcript, and the session attribution lines.
