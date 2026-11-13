# Replication-Mode Golden Baselines and `convert` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each testbed a golden definition for both multicast and ingress replication, and a `golden.py convert` command that moves a
testbed from one to the other and ends on a zero-drift check.

**Architecture:** Each topology file states the common fabric settings once and a per-mode delta under `replication_modes`; the loader merges
the chosen mode into `fabric.settings`, so the existing drift and provisioning code is unchanged below the loader. A new pure module
`replication.py` holds the mode constants, the ingress key stripping and the "which mode is this fabric really in" classification. A new
`golden_convert.py` runs the ordered teardown, mode change and rebuild, deciding every step from the live state so a stopped run resumes.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `requests`, PyYAML. Line length 169. Lint with `mypy`, `flake8`, `black --check`.

**Spec:** `docs/superpowers/specs/2026-11-13-replication-mode-golden-design.md`. Background: `docs/nd_replication_mode_change.md`.

## Global Constraints

- Work on branch `nd431-ingress-replication`; open a PR, never push to `main`. Never stage anything under `env_prod/`.
- Mode names are exactly `multicast` and `ingress`. Only `SITE1` and `SITE2` get modes; `CAMPUS1` is not touched.
- No silent default mode: a topology file that declares modes cannot be loaded without one.
- Multicast-only keys, exactly: `anycastRendezvousPointIpRange`, `multicastGroupSubnet`, `rendezvousPointLoopbackId`,
  `underlayMulticastGroupAddressLimit`, `autoGenerateMulticastGroupAddress`, `tenantRoutedMulticastIpv6`.
- Old-mode underlay policies: `base_multicast_11_1` and `base_pim_asm_v6` mark multicast; `ingress_rep_simulated` marks ingress.
- Exit codes: 0 ok, 1 drift, 2 refused or cancelled, 3 live read failed, 4 apply failed.
- Tasks 1 to 7 touch no controller. Only Task 8 writes to a testbed, and only to ND 4.2.1 (10.10.20.10). ND 4.3.1 (10.10.20.20) gets
  nothing but the read-only check in Task 9, and only after the user confirms the interface tests there have finished.
- Run all tests with `uv run pytest config/nd/provision/tests -q` from the repo root; every task ends with the whole suite green.
- A test file with no `replication_modes` section must keep loading exactly as today (the fixtures under `tests/fixtures/` are not edited).

## Review Focus

- A conversion that stopped after the mode `PUT` but before the deploy: the rerun must treat the fabric as mid-conversion and finish steps
  5 and 6, never start the rebuild. Pinned in Task 6.
- `restore` run with no mode flag against a mid-conversion testbed: must exit 2 and name `convert`, not pick a mode. Pinned in Task 4.
- A non-golden VRF, network or `ebgpVrfLite` link (test residue) in `SITE1`/`SITE2`: `convert` must list it before the prompt and remove
  it, because ND will not change mode around it. Pinned in Task 6.
- `provision.py --phase fabrics --replication-mode X` against a populated fabric in the other mode: must refuse, not `PUT`. Pinned in Task 2.
- A topology file with a typo in a mode name, or only one of the two modes: must fail at load with a message naming the fabric. Pinned in
  Task 1.

---

### Task 1: Mode-aware topology loader and the two shipped files

**Files:**

- Modify: `config/nd/provision/topology.py` (`Topology`, `load`, `_validate`)
- Modify: `config/nd/provision/topology_nd421.yaml`, `config/nd/provision/topology_nd431.yaml`
- Test: `config/nd/provision/tests/test_topology.py`

**Interfaces:**

- Produces: `load(path: Path, replication_mode: str | None = None) -> Topology`; `Topology.replication_mode: str | None`;
  `Topology.mode_fabrics: tuple[str, ...]` (names of fabrics that declared modes, in file order);
  `declared_mode_fabrics(path: Path) -> list[str]` (reads the yaml only, no validation, for callers that must detect the mode first);
  `REPLICATION_MODES = ("multicast", "ingress")`.

- [ ] **Step 1: Write the failing tests** in `test_topology.py`. Build small yaml strings in `tmp_path` in the style of
  `test_dangling_switch_reference_is_rejected`.

```python
MODES = (
    "    replication_modes:\n"
    "      multicast: {management: {replicationMode: multicast, anycastRendezvousPointIpRange: 10.13.0.0/24}}\n"
    "      ingress: {management: {replicationMode: ingress}}\n"
)

def test_mode_delta_is_merged_into_settings(tmp_path):
    topo = load(_file(tmp_path, MODES), replication_mode="multicast")
    assert topo.fabrics[0].settings["management"] == {"bgpLoopbackIpRange": "10.11.0.0/22", "replicationMode": "multicast", "anycastRendezvousPointIpRange": "10.13.0.0/24"}
    assert topo.replication_mode == "multicast" and topo.mode_fabrics == ("SITE1",)
    ingress = load(_file(tmp_path, MODES), replication_mode="ingress")
    assert "anycastRendezvousPointIpRange" not in ingress.fabrics[0].settings["management"]

def test_mode_bearing_file_needs_a_mode(tmp_path):
    with pytest.raises(ValueError, match="--replication-mode"):
        load(_file(tmp_path, MODES))

def test_modeless_file_loads_unchanged_and_rejects_a_mode(tmp_path):
    assert load(_file(tmp_path, "")).replication_mode is None
    with pytest.raises(ValueError, match="declares no replication_modes"):
        load(_file(tmp_path, ""), replication_mode="ingress")

@pytest.mark.parametrize("modes, message", [
    ("    replication_modes:\n      multicast: {management: {replicationMode: multicast}}\n", "SITE1.*both multicast and ingress"),
    (MODES.replace("ingress:", "ingres:"), "SITE1.*unknown replication mode 'ingres'"),
    (MODES.replace("replicationMode: ingress", "replicationMode: multicast"), "SITE1.*ingress.*replicationMode"),
    (MODES.replace("anycastRendezvousPointIpRange: 10.13.0.0/24", "bgpLoopbackIpRange: 10.99.0.0/22"), "SITE1.*bgpLoopbackIpRange.*both settings and replication_modes"),
])
def test_mode_section_validation(tmp_path, modes, message): ...

def test_declared_mode_fabrics_reads_names_only(tmp_path):
    assert declared_mode_fabrics(_file(tmp_path, MODES)) == ["SITE1"]
```

  `_file` writes one `SITE1` `vxlanIbgp` fabric with `settings: {management: {bgpLoopbackIpRange: 10.11.0.0/22}}` plus the given block.

- [ ] **Step 2: Run** `uv run pytest config/nd/provision/tests/test_topology.py -q`. Expected: the new tests FAIL (unexpected keyword
  `replication_mode`, `declared_mode_fabrics` undefined).

- [ ] **Step 3: Implement** in `topology.py`. Merge with the same deep-merge rule as `provision.merge_settings`; do not import `provision`
  from `topology` (it imports `topology`), so move `merge_settings` into `topology.py` and re-export it from `provision.py`.

- [ ] **Step 4: Reshape both shipped files.** In `SITE1` and `SITE2`, remove the mode-specific lines from `settings.management` and add:

```yaml
    replication_modes:
      multicast:
        management: {replicationMode: multicast, anycastRendezvousPointIpRange: 10.13.0.0/24}   # 10.23.0.0/24 in SITE2
      ingress:
        management: {replicationMode: ingress}
```

  In `topology_nd431.yaml` this replaces the uncommitted `replicationMode: ingress` lines. `CAMPUS1` keeps its `anycastRendezvousPointIpRange`
  in `settings`.

- [ ] **Step 5: Update the shipped-file tests.** Every `load(HERE / "topology_nd4*.yaml")` in `tests/` gains a mode. Parametrize
  `test_shipped_topologies_load_and_mirror` and `test_shipped_topologies_differ_only_in_hostnames_and_mgmt_ips` over both modes; the
  others load with `replication_mode="multicast"`.

- [ ] **Step 6: Run the whole suite.** Expected: all pass, including the mirror test that currently fails on this branch.

- [ ] **Step 7: Commit** `topology: per-fabric replication_modes; both shipped files carry multicast and ingress`.

### Task 2: `replication.py`, the ingress settings body, and `provision.py --replication-mode`

**Files:**

- Create: `config/nd/provision/replication.py`
- Modify: `config/nd/provision/provision.py` (`phase_fabrics`, `main`)
- Test: `config/nd/provision/tests/test_replication.py` (new), `config/nd/provision/tests/test_provision_phases.py`

**Interfaces:**

- Consumes: `load(path, replication_mode)`, `Topology.replication_mode`, `Topology.mode_fabrics`, `merge_settings` (Task 1).
- Produces, in `replication.py` (pure, no I/O):
  - `MULTICAST_ONLY_KEYS: tuple[str, ...]`, `MODE_POLICIES: dict[str, tuple[str, ...]]`
    (`{"multicast": ("base_multicast_11_1", "base_pim_asm_v6"), "ingress": ("ingress_rep_simulated",)}`)
  - `settings_body(current: dict, settings: dict) -> dict`: `merge_settings(current, settings)`, then when the merged
    `management.replicationMode` is `ingress`, drop every `MULTICAST_ONLY_KEYS` key from `management`.
  - `live_mode(fabric_obj: dict) -> str | None`: `management.replicationMode` of a fabric GET body.

- [ ] **Step 1: Write the failing tests.**

```python
def test_ingress_body_drops_every_multicast_only_key():
    current = {"management": {"replicationMode": "multicast", "bgpLoopbackIpRange": "10.11.0.0/22", **{k: "x" for k in MULTICAST_ONLY_KEYS}}}
    body = settings_body(current, {"management": {"replicationMode": "ingress"}})
    assert body["management"] == {"replicationMode": "ingress", "bgpLoopbackIpRange": "10.11.0.0/22"}

def test_multicast_body_keeps_the_pinned_rp_range():
    body = settings_body({"management": {"replicationMode": "ingress"}}, {"management": {"replicationMode": "multicast", "anycastRendezvousPointIpRange": "10.13.0.0/24"}})
    assert body["management"]["anycastRendezvousPointIpRange"] == "10.13.0.0/24"

def test_modeless_settings_are_a_plain_merge():
    current = {"management": {"anycastRendezvousPointIpRange": "10.43.0.0/24"}}
    assert settings_body(current, {"management": {"fabricMtu": 8978}})["management"] == {"anycastRendezvousPointIpRange": "10.43.0.0/24", "fabricMtu": 8978}
```

  In `test_provision_phases.py`, with the existing `StubClient`:

```python
def test_phase_fabrics_refuses_a_mode_change_on_a_populated_fabric():
    # live SITE1: replicationMode multicast, one switch; topology loaded with replication_mode="ingress"
    with pytest.raises(SystemExit) as exc: prov.phase_fabrics()
    assert exc.value.code == 2 and "golden.py convert" in str(...)   # message captured from stdout
    assert not [c for c in client.calls if c[0] == "PUT"]

def test_phase_fabrics_sets_the_mode_on_an_empty_fabric():
    # same, no switches: one PUT whose body has replicationMode ingress and none of MULTICAST_ONLY_KEYS

def test_main_requires_the_flag_for_a_mode_bearing_topology(capsys):
    # main(["--topology", shipped nd431, "--phase", "fabrics", "--dry-run"]) exits 2 naming --replication-mode
```

- [ ] **Step 2: Run** the two test files. Expected: FAIL (module `replication` missing).
- [ ] **Step 3: Implement** `replication.py`, then switch `phase_fabrics` from `merge_settings` to `settings_body`, add the guard (live mode
  differs from the topology's and `GET /fabrics/{f}/switches` is non-empty), and add `--replication-mode` (`choices=REPLICATION_MODES`) to
  `main`, passed to `load`. `main` takes an optional `argv` so the test can call it.
- [ ] **Step 4: Run the whole suite.** Expected: PASS.
- [ ] **Step 5: Commit** `provision: --replication-mode, ingress settings body, refuse a mode change on a populated fabric`.

### Task 3: Live read of group members and underlay policies, and the mode classification

**Files:**

- Modify: `config/nd/provision/golden_live.py` (`LiveFabric`, `read_live`, `read_live_from_snapshot`)
- Modify: `config/nd/provision/replication.py`
- Test: `config/nd/provision/tests/test_golden_live.py`, `config/nd/provision/tests/test_replication.py`

**Interfaces:**

- Consumes: `MODE_POLICIES`, `live_mode` (Task 2); `Topology.mode_fabrics` (Task 1).
- Produces:
  - `LiveFabric.members: list[str]` (groups only, from `GET /fabrics/{group}/members`, key `fabrics`, each `name`; snapshot: `members_<group>.json`).
  - `LiveFabric.mode_policies: dict[str, set[str]] | None`: hostname to the subset of all `MODE_POLICIES` template names that switch holds,
    read for `topo.mode_fabrics` only with one paged `GET /fabrics/{f}/policies` (key `policies`, fields `switchId`, `templateName`);
    `None` for other fabrics and for every snapshot read.
  - `LiveFabric.pending: dict[str, int] | None`: hostname to pending line count, for `topo.mode_fabrics` only
    (`GET /fabrics/{f}/switches/{serial}/pendingConfig`, key `pendingConfigs`); `None` otherwise.
  - In `replication.py`: `fabric_state(live: LiveFabric) -> str` returning `"multicast"`, `"ingress"` or `"mid"`.
    Rule: let `m = live_mode(live.settings)`. Return `m` when no switch holds a policy of the other mode and no switch has pending config;
    otherwise `"mid"`. When `mode_policies` is `None` (snapshot) return `m`.
  - `testbed_state(topo: Topology, live: dict[str, LiveFabric]) -> str`: the common `fabric_state` of all `topo.mode_fabrics`, else `"mid"`.

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize("setting, policies, pending, expected", [
    ("multicast", {"S1_SP1": {"base_multicast_11_1"}}, {"S1_SP1": 0}, "multicast"),
    ("ingress", {"S1_SP1": {"ingress_rep_simulated"}}, {"S1_SP1": 0}, "ingress"),
    ("ingress", {"S1_SP1": set()}, {"S1_SP1": 0}, "ingress"),                           # ToR-like switch, no mode policy at all
    ("ingress", {"S1_SP1": {"base_multicast_11_1"}}, {"S1_SP1": 0}, "mid"),              # setting saved, never deployed
    ("ingress", {"S1_SP1": set()}, {"S1_SP1": 9}, "mid"),                                # recalculated, deploy not finished
    ("multicast", {"S1_SP1": {"ingress_rep_simulated"}}, {"S1_SP1": 0}, "mid"),
])
def test_fabric_state(setting, policies, pending, expected): ...

def test_fabric_state_from_a_snapshot_uses_the_setting_alone():      # mode_policies None -> "ingress"
def test_testbed_state_is_mid_when_fabrics_disagree():               # SITE1 ingress, SITE2 multicast -> "mid"
```

  In `test_golden_live.py`: `read_live` fills `members` for `MSD`, fills `mode_policies` and `pending` for a mode fabric and leaves them
  `None` for `ISN`; a policy list carrying another switch's rows (ND 4.3.1 ignores the filter) is grouped by `switchId`; a failing
  policies GET raises `LiveReadError`.

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole suite.** Expected: PASS.
- [ ] **Step 5: Commit** `golden: read group members, mode policies and pending counts; classify a fabric's real replication mode`.

### Task 4: Mode selection in `golden.py drift | restore | adopt`

**Files:**

- Modify: `config/nd/provision/golden.py` (`_parser`, `main`)
- Test: `config/nd/provision/tests/test_golden_cli.py`

**Interfaces:**

- Consumes: `declared_mode_fabrics`, `load(path, replication_mode)` (Task 1); `live_mode` (Task 2); `testbed_state` (Task 3).
- Produces: `resolve_mode(args, client_or_snapshot, out) -> str | None` in `golden.py`, returning the mode to load with, or raising
  `Refused(message)` (new exception, mapped to exit 2).

Behaviour:

1. File declares no modes: `None`; an explicit flag is a `Refused`.
2. Flag omitted: read `GET /fabrics/{f}` (or `fabric_<f>.json` from the snapshot) for each declared mode fabric; if they agree, use it and
   print `replication mode: <mode> (detected)`; if they disagree, `Refused` naming `convert`.
3. After `read_live`: when not a snapshot and `testbed_state` is `"mid"`, exit 2 with
   `testbed is mid-conversion; run golden.py convert --replication-mode <mode>`. This applies to `drift`, `restore` and `adopt`.
4. `restore` with an explicit flag that differs from the detected setting: exit 2 naming `convert`. `drift` with such a flag is allowed
   (it reports the settings as `DIFFERENT`).

- [ ] **Step 1: Write the failing tests**, one per numbered behaviour plus: the detected line is printed once; `--snapshot` detection
  reads the dump and never classifies as mid. Assert exit codes and that no write call was recorded.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole suite.** Expected: PASS.
- [ ] **Step 5: Commit** `golden: --replication-mode, detected from the live ND when omitted; refuse a mid-conversion testbed`.

### Task 5: Membership and `enableIr` drift classes, and the settings fix body

**Files:**

- Modify: `config/nd/provision/golden_drift.py` (`drift_settings`, `compute`, new `drift_members`, `_overlay_object_drifts`)
- Modify: `config/nd/provision/golden_apply.py` (`RANK`, `Applier.apply`)
- Test: `config/nd/provision/tests/test_golden_drift.py`, `config/nd/provision/tests/test_golden_apply.py`

**Interfaces:**

- Consumes: `settings_body` (Task 2); `LiveFabric.members` (Task 3); `Topology.replication_mode`, `Topology.mode_fabrics` (Task 1).
- Produces:
  - `drift_settings` builds its `put_settings` body with `settings_body`.
  - Drift class `"members"`: per golden group, a golden member absent from `live[group].members` is `missing`, subject the member name,
    fix `Op("add_member", group, "POST", f"/fabrics/{group}/actions/addMembers", {"members": [{"name": member}]})`; a live member not in
    golden is `extra` with `fix`, `delete` and `adopt` all `None`. `compute` places `members` after `switches`.
  - In ingress mode only (`topo.replication_mode == "ingress"`): for each golden network, each copy in a `topo.mode_fabrics` fabric whose
    `l2Data.fabricData.enableIr` is not true is a `different` drift of class `networks`, fabric the member fabric, with fix
    `[Op("put_network_ir", fabric, "PUT", f"/fabrics/{fabric}/networks/{name}", <live copy with enableIr true, networkStatus removed>),
    Op("deploy_overlay", fabric, "POST", f"/fabrics/{fabric}/networkActions/deploy", {"networkNames": [name], "switchIds": <attached serials>})]`.
    `Drift.fix` becomes `Op | list[Op] | None`; `golden._fix_ops` flattens it.
  - `RANK`: `add_member` at 3 (after `set_role`, before `clear_link`); `put_network_ir` at 13 with `attach`; shift nothing else's
    relative order.
  - `Applier.apply`: when the ops contain an `add_member`, after the last `put_link` op and before the first op of rank 8 or above, call
    `prov.config_deploy` for every fabric of `topo.mode_fabrics` that is a member of a touched group, then for the group. `Applier`
    gains `topo: Topology` in its constructor for this.

- [ ] **Step 1: Write the failing tests.**

```python
def test_missing_group_member_is_a_drift_with_an_add_member_fix(): ...
def test_extra_group_member_is_reported_only(): ...
def test_ingress_member_copy_without_enable_ir_is_different_with_a_put_and_deploy_fix(): ...
def test_enable_ir_is_not_compared_in_multicast_mode(): ...
def test_put_settings_fix_for_ingress_carries_no_multicast_only_key(): ...
def test_apply_with_add_member_deploys_fabrics_then_group_before_any_overlay_op():
    # ops: add_member SITE1, put_link, create_network, attach -> recorded order:
    # addMembers, PUT /links/..., configSave+deploy SITE1, configSave+deploy MSD, POST networks, POST networkAttachments
def test_apply_without_add_member_keeps_today's_order(): ...
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Update the `Applier(prov)` call sites (`golden.py`, tests) to pass `topo`.
- [ ] **Step 4: Run the whole suite.** Expected: PASS.
- [ ] **Step 5: Commit** `golden: group membership and ingress enableIr drift; deploy after a member add before overlay ops`.

### Task 6: `golden.py convert`

**Files:**

- Create: `config/nd/provision/golden_convert.py`
- Modify: `config/nd/provision/golden.py` (`_parser`, `main`: new `convert` subcommand with `--replication-mode` required, `--yes`,
  `--extras`, `--dry-run`)
- Test: `config/nd/provision/tests/test_golden_convert.py` (new)

**Interfaces:**

- Consumes: `fabric_state`, `testbed_state`, `settings_body` (Tasks 2, 3); `read_live`; `_extra_overlay_drift` op sequences
  (`golden_drift`); `Applier` (Task 5); `Provisioner.config_deploy`; `run_restore` (`golden.py`).
- Produces:
  - `@dataclass ConvertPlan`: `target: str`, `states: dict[str, str]` (fabric to `fabric_state`), `overlay_ops: list[Op]`,
    `leave: list[tuple[str, str]]` (group, member), `link_ids: list[tuple[str, str, str]]` (fabric, linkId, description),
    `convert: list[str]` (fabrics not yet in the target mode), `intact_source: bool`.
  - `plan(topo_target: Topology, live: dict[str, LiveFabric]) -> ConvertPlan` (pure).
  - `describe(plan: ConvertPlan) -> str` (the text shown before the prompt and by `--dry-run`).
  - `run(args, topo_target: Topology, prov: Provisioner, ask, out) -> int`.

`plan` rules, all from the live state:

- `overlay_ops`: for every VRF and network found in the group and in each mode fabric, golden or not, the detach, deploy, delete sequence;
  networks before VRFs. Empty when none exist.
- `leave`: each mode fabric that is in `live[group].members`.
- `link_ids`: every live link of a mode fabric whose policy is `ebgpVrfLite`.
- `convert`: mode fabrics whose `fabric_state` is not `target`.
- `intact_source`: every mode fabric's `fabric_state` is the other mode's name, `leave` covers all of them, and every golden `isn.links`
  entry is live as `ebgpVrfLite`.

`run` order: refuse (exit 2) when `intact_source` and any `LiveFabric.pending` count is non-zero. Print `describe`; prompt unless `--yes`
(with `--yes` and no `--extras`, exit 2 as `restore` does). When `convert` is non-empty: apply `overlay_ops`; `removeMembers` for `leave`
then `config_deploy` each left fabric; `DELETE /links/{id}` for `link_ids`; `PUT /fabrics/{f}` with `settings_body` then `config_deploy`
for each fabric in `convert`; re-read and fail with exit 4 if any is still not in the target mode. Then the rebuild: re-read live and call
`run_restore` with the target topology (Task 5 makes one pass add members, restore links, deploy, then create the overlay). Finish with a
re-read: exit 0 only on zero drift and zero pending, else 4. Any `ApplyError` or read error exits 4 or 3 with the step named.

`removeMembers` body: `{"members": [{"name": member}]}`, the mirror of `addMembers`. Confirm against
`mcp__nd-openapi__get_endpoint` for both 4.2.1 and 4.3.1 before coding it.

`--dry-run`: print `describe` and the exact calls of the first step that has work; send nothing; exit 0.

- [ ] **Step 1: Write the failing tests** for `plan`, building `LiveFabric` objects by hand (helper `_testbed(mode, *, overlay=True,
  members=True, links=True, policies=None, pending=0)`).

```python
def test_plan_from_an_intact_multicast_testbed():
    p = plan(topo("ingress"), _testbed("multicast"))
    assert p.intact_source and p.convert == ["SITE1", "SITE2"] and p.leave == [("MSD", "SITE1"), ("MSD", "SITE2")]
    assert [o.action for o in p.overlay_ops][-2:] == ["delete_network", "delete_vrf"] and len(p.link_ids) == 2

def test_plan_from_an_intact_ingress_testbed_to_multicast(): ...          # the mirror
def test_plan_includes_non_golden_overlay_and_links(): ...                # extra network TEST_NET + extra ebgpVrfLite link appear
def test_plan_resumes_with_no_overlay(): ...                              # overlay_ops == [], rest unchanged
def test_plan_resumes_out_of_group_with_links_deleted(): ...              # leave == [], link_ids == []
def test_plan_treats_a_saved_but_undeployed_setting_as_not_converted():   # setting ingress, base_multicast_11_1 still present
    assert plan(topo("ingress"), _testbed("ingress", policies={"base_multicast_11_1"}, overlay=False, members=False, links=False)).convert == ["SITE1", "SITE2"]
def test_plan_for_a_converted_but_unrebuilt_testbed_has_nothing_to_convert(): ...   # convert == [], not intact_source
def test_plan_for_a_finished_testbed_is_empty(): ...
```

- [ ] **Step 2: Write the failing tests** for `run` with the recording `StubClient` and a stub `run_restore`:
  the full ordered call list for multicast to ingress; refusal with pending config only when `intact_source`; `--dry-run` records no
  write; `--yes` without `--extras` exits 2; a fabric still not in the target mode after the deploy exits 4 and `run_restore` is not
  called; an `ApplyError` in the teardown exits 4.
- [ ] **Step 3: Run.** Expected: FAIL (module missing).
- [ ] **Step 4: Implement** `golden_convert.py` and the subcommand. `main` loads the topology with the target mode for `convert`
  without going through `resolve_mode`.
- [ ] **Step 5: Run the whole suite, then** `uv run mypy config/nd/provision/golden_convert.py config/nd/provision/replication.py`,
  `uv run flake8 config/nd/provision/`, `uv run black --check config/nd/provision/`. Expected: all clean.
- [ ] **Step 6: Commit** `golden: convert a testbed between multicast and ingress replication`.

### Task 7: Documentation and the reference snapshot layout

**Files:**

- Modify: `config/nd/provision/README.md`, `CLAUDE.md`, `docs/nd_replication_mode_change.md`
- Move: `config/nd/provision/golden/nd421/*` to `golden/nd421/multicast/`, `golden/nd431/*` to `golden/nd431/multicast/` (`git mv`)

- [ ] **Step 1:** `git mv` the two dump directories; fix any path in `README.md`, `CLAUDE.md` and tests that names them
  (`grep -rn "golden/nd4" --include='*.py' --include='*.md' .`).
- [ ] **Step 2:** README: add `--replication-mode` to every usage line, a "Replication modes" section (the `replication_modes` yaml
  shape, detection, the mid-conversion refusal, `convert` with its steps, resume by rerun, what `--dry-run` prints), and the two new
  drift classes under "Rules". CLAUDE.md: one sentence in the golden-baseline note and the `provision.py` row. The mode-change doc: point
  the procedure at `convert`.
- [ ] **Step 3:** `uv run pymarkdown scan` on each edited Markdown file; run the whole suite. Expected: clean.
- [ ] **Step 4: Commit** `docs: replication modes and golden.py convert; per-mode reference snapshots`.

### Task 8: Lab validation on ND 4.2.1

Writes to ND 4.2.1 (10.10.20.10) only. Run on the lab host or from the Mac with `env_prod/env.sh` sourced. Each conversion takes 20 to 30
minutes. Record every observation in `docs/nd_replication_mode_change.md`. Host pings need root on the lab host: ask the user to run them.

- [ ] **Step 1:** `golden.py drift --topology topology_nd421.yaml --nd-ip 10.10.20.10`. Expected: `replication mode: multicast (detected)`.
  Resolve any drift with the user before continuing.
- [ ] **Step 2:** `golden.py convert ... --replication-mode ingress --dry-run`. Review the printed plan with the user.
- [ ] **Step 3:** Multicast to ingress: `convert --replication-mode ingress --yes --extras delete`. Expected: exit 0. Then check
  `show nve vni` on `S1_LE1` and `S2_LE1` (VNI 30001 `UnicastBGP`, Up) and ask for the `S1_H1` to 192.0.1.172 ping.
- [ ] **Step 4:** `snapshot.py dump config/nd/provision/golden/nd421/ingress --nd-ip 10.10.20.10`; scrub credential hashes as the
  existing dumps are.
- [ ] **Step 5:** Ingress to multicast: `convert --replication-mode multicast --yes --extras delete`. Expected: exit 0; `show nve vni`
  shows the multicast group, `show ip pim neighbor` and `show ip pim rp` are populated, host ping works. If ND rejects the settings `PUT`
  for a missing multicast key, add that key with its value from `golden/nd421/multicast/fabric_SITE1.json` to the multicast delta in both
  topology files, rerun, and record it.
- [ ] **Step 6:** Diff a fresh dump against `golden/nd421/multicast/` with `snapshot.py diff`. Record whether the anycast RP address,
  loopback 254 and the vPC and ToR pairings came back identical; re-take the reference dump if anything ND-allocated moved.
- [ ] **Step 7:** Start multicast to ingress again and interrupt it (Ctrl-C) once the log shows the `removeMembers` call; rerun the same
  command. Expected: it continues and exits 0.
- [ ] **Step 8:** Convert back to multicast, then start multicast to ingress and interrupt it right after the `PUT /fabrics/SITE1`
  settings call; run `golden.py drift` (expected: exit 2, mid-conversion, names `convert`); rerun `convert`. Expected: exit 0. ND 4.2.1
  is now in ingress mode, the state the test suite wants.
- [ ] **Step 9:** Answer the spec's four open questions in the mode-change doc from what was seen. If step 3 of `convert` (leave the
  group) proved unnecessary, leave it in: it is known to work.
- [ ] **Step 10: Commit** `golden: ND 4.2.1 validated in both replication modes; ingress reference snapshot`.

### Task 9: ND 4.3.1 check and the pull request

- [ ] **Step 1:** Ask the user whether the interface tests on ND 4.3.1 have finished. Do not contact 10.10.20.20 before that.
- [ ] **Step 2:** `golden.py drift --topology topology_nd431.yaml --nd-ip 10.10.20.20` (read-only). Expected:
  `replication mode: ingress (detected)`; any drift is test residue for the user to decide on.
- [ ] **Step 3:** With the user's go-ahead and zero drift, `snapshot.py dump config/nd/provision/golden/nd431/ingress --nd-ip 10.10.20.20`
  (read-only), scrub, commit.
- [ ] **Step 4:** Push the branch and open the PR against `main` with the attribution lines the session specifies.
