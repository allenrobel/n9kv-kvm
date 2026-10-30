# Golden baseline: drift report and confirmed restore for the ND testbeds

Date: 2026-10-30. Status: draft for review.

## Intent

After the 2026-10-30 power outage both testbeds came back with every switch "in sync, 0 pending" on both controllers,
yet no host could cross the fabric: the SITE1 spine links, the ToR host port and the BGW DCI link had lost their intent
in ND (interface integration tests had rewritten them). ND's own compliance view cannot see that, because it compares
the switch against ND's intent, and the intent itself was wrong.

The user wants the lab's intended state to be a thing the repo owns ("golden"), and a single command that, against
one controller:

1. prints every way the live ND differs from golden, and
2. only after an explicit confirmation, pushes the lab back to golden, asking per extra object whether to adopt it
   into golden or delete it from the lab.

The current state of both testbeds (after the 2026-10-30 restore) is the first golden.

## Goals

- `drift`: read-only, exit 1 when anything differs, output a human can act on in under a minute.
- `restore`: drift, then confirm, then push; idempotent (a second run reports no drift and writes nothing).
- Extras (in ND, not in golden) are a three-way choice per item: adopt into golden, delete from the lab, skip.
  Adopting rewrites the topology file in place so the repo diff is the audit trail.
- Non-interactive operation (Claude over ssh, scripts) with explicit flags, never silent defaults.
- Reuse the provision package: `topology.py` models, `nd_client.py`, the `Provisioner` phases and `config_deploy()`.
- Run on the lab host exactly like `provision.py` (`uv run`, `env_prod` sourced, `--nd-ip`).

## Non-goals

- Detecting whether a test is running. The user runs this only after testing is complete; the skill states that.
- Dataplane verification (OSPF/BGP/NVE/pings). That stays in the `restore-lab-topologies` skill.
- Host-side state (VMs, OVS). Covered by the skill and the launchers.
- Fighting ND over objects ND generates itself (vPC peer-link port-channels, ToR port-channels, MSD multisite
  links, campus `iosXeNumbered` links, discovered links without a policy). These are reported, never deleted.
- A GUI. Terminal only.

## Anti-goals (what would make this a failure even if it ran)

- Pushing anything without the user having seen the exact list first.
- Deleting an object the user did not individually (or via an explicit `--extras delete`) choose to delete.
- Touching the other controller: one invocation targets one `--nd-ip`.
- A golden file that cannot be read back by humans (comments lost, ordering scrambled) after an adopt.
- A drift report that lists ND-generated noise as drift every run.

## Constraints

- Python 3.13, line length 169, black/flake8/mypy/pytest as in `CLAUDE.md`; PR workflow.
- `env_prod/` is never committed; credentials come from the environment via `NDCredentials.from_env`.
- ND behaviours already learned (keep them, they are tested by the lab):
  - Recalculate & Deploy is `actions/configSave` then `actions/deploy` (`Provisioner.config_deploy`), MSD after its members.
  - ND refuses an interface policy-type change on a port that has a network attached, and refuses
    `DELETE /interfaces/...` outright. Detach, change policy, re-attach (the attach/detach results list the vPC leaf
    pair, not the ToR; that is normal). `_ensure_access_port` already does the forward direction.
  - Link `PUT` with `configData.policyType: numbered` regenerates the fabric link intent; descriptions:
    `srcInterfaceDescription` names the *source* side (ND places it on the destination interface).
  - MSD group deploy regenerates `multisiteUnderlay` links when `autoMultisiteUnderlayInterConnect` is on.
  - `GET /links` needs `fabricName`; a fabric's list includes links whose other end is in another fabric.
  - Interface GETs on 4.3.1 need `%2F` in the interface name; attachments are queried with the `/query` POSTs.

## What golden covers (object classes), in priority order

<!-- pyml disable-num-lines 12 line-length -->
| # | Class | Golden source | Drift kinds | Push | Extras |
|---|---|---|---|---|---|
| 1a | Tool-owned fabric links (intra-fabric `numbered`, ISN `ebgpVrfLite`) | new `fabrics[].links:` + existing `isn.links` | missing policy, different policy/inputs | `PUT /links/{id}` | a link in ND with a tool-ownable policy that golden does not list: adopt (write it) or delete (= `PUT` the link back with `configData: null`, which is the state the tests left; never an ND `DELETE`) |
| 1b | ND-generated links (`multisiteUnderlay`, `multisiteOverlay`, campus `iosXeNumbered`, vPC peer-link and ToR port-channel `ethisl` rows, any discovered link with no policy) | new `fabrics[].generated_links:` for the ones that matter (today: the BGW DCI link per controller); everything else in this class is ignored | listed link missing or without its policy | Recalculate & Deploy of the owner (`owner: MSD` → group deploy; `owner: CAMPUS1` → fabric deploy) — never a link `PUT` | never extras; never deleted |
| 2 | Interface policies on physical ports | new `fabrics[].interfaces:` (explicit ports) + rule: every other *free* port on a golden switch is at the role default | explicit port differs; free port not at default | `PUT /interfaces/...` (with the detach/re-attach dance when a type change is refused) | free non-default port: adopt (write the port) or delete (= `PUT` the full role-default policy body) |
| 2b | Logical interfaces (port-channel, vPC, subinterface, SVI) | `fabrics[].interfaces:` entries with `type:` (today: none beyond what ND generates) | listed one missing/different; unlisted one present | `PUT`/`POST` the interface | extra = any unlisted logical interface ND did not generate (generated: `port-channel500` peer-links, ToR `port-channel1`, link subinterfaces); adopt or real `DELETE` (the ND refusal in the constraints was an Ethernet port; vPC/port-channel deletes are what the tests do routinely) |
| 3 | Network/VRF attachments | existing `overlay.*_attachments` | missing, different interfaces/vlan | existing `phase_overlay` logic | extra attachment: adopt or detach |
| 4 | VRFs / networks | existing `overlay.vrfs/networks` | missing, different | existing | extra: adopt or delete (detach everywhere first) |
| 5 | vPC pairs, ToR pairs | existing `vpc_pairs`, `tor_pairs` | missing | existing phases | extra pair: adopt or unpair |
| 6 | Switch membership and role | existing `fabrics[].switches` | missing, wrong role, wrong fabric | existing `phase_switches` / role change | extra switch: adopt or report only (removing a switch is never automatic) |
| 7 | Fabric and group settings | existing `settings:` | key differs | existing merge + PUT | keys ND has that golden does not: ignored (golden settings are a subset by design) |

**Free port** (class 2): a physical port on a golden switch that is not an endpoint of any link in ND's link list for
that fabric (any policy, including discovered links with none), not a member of a port-channel (`operData.portChannelId`
is -1), and not the management port. Underlay members, peer-link members, vPC members and ToR uplinks are therefore
never "extra"; a wrong rule here would reset an underlay member and take a fabric down, so the builder tests it against
the committed snapshot dumps before anything live.

**Comparison** (classes 2/2b): `policyType` plus a fixed subset of inputs — `adminState`, `mode`, `accessVlan`,
`allowedVlans`, `nativeVlan`, `description`, `mtu` (test residue is usually a description or `allowedVlans` on an
otherwise default policy). Other keys are ignored. The reset body is the full role-default policy, not just a type.

**Role defaults** are golden data, not code: a `defaults:` map per fabric (`spine`/`borderGateway`: `routedHost`,
admin down; `leaf`/`tor`: `trunkHost`, allowed none; campus `leaf`/`spine`: ND's campus defaults, which the CAMPUS1
`Gi1/0/1-7` must keep for the IOS-XE tests), captured by `adopt` at bootstrap from a known-free port of each role and
confirmed by the user in the diff. Switches in external fabrics (WAN1, `coreRouter`, preserveConfig) are out of scope for
classes 2/2b; management ports and loopbacks are out of scope everywhere.

## Golden file additions

Extend both topology files (they stay the only golden; they must keep differing only in hostnames/IPs):

```yaml
fabrics:
  - name: SITE1
    links:                      # fabric links that must carry a policy; discovered links not listed here are ignored
      - {src: S1_SP1, src_if: Ethernet1/1, dst: S1_BG1, dst_if: Ethernet1/2, policy: numbered, src_ip: 10.14.0.1, dst_ip: 10.14.0.2}
      - {src: S1_SP1, src_if: Ethernet1/2, dst: S1_LE1, dst_if: Ethernet1/1, policy: numbered, src_ip: 10.14.0.5, dst_ip: 10.14.0.6}
      # ... Ethernet1/3-5 -> LE2/LE3/LE4 on 10.14.0.8/.12/.16
    interfaces:                 # explicit per-port intent; every other port on these switches must be at its role default
      - {switch: S1_TOR1, interface: Ethernet1/3, policy: accessHost, description: S1_H1 host port}
      - {switch: S2_LE1,  interface: Ethernet1/2, policy: accessHost, description: S2_H1 host port}
```

Template inputs the tool fills for `numbered`: mtu 9216, speed/fec auto, admin up, descriptions `connected-to-<self>-<if>`,
the four bfd/dhcp flags false, empty v6. Anything else a link needs goes in an optional `inputs:` map that overrides.

**Link IPs are pinned golden intent**, required and compared. The two files must carry identical link IPs (the
"differ only in hostnames and management IPs" rule means *management* IPs; underlay /30s are shared by design, like
the fabric pools). ND allocated SITE2's /30s identically on both controllers (10.24.0.0/30, 10.24.0.4/30) and the
2026-10-30 SITE1 re-provisioning chose identical ones by hand, so bootstrap records what is live; if a later ND
allocation ever differs between controllers, `drift` reports it and `restore` re-addresses the link (an OSPF flap on a
lab link is acceptable).

```yaml
    generated_links:            # ND makes these; golden only asserts they exist with this policy, and repairs via the owner's deploy
      - {src: S1_BG1, src_if: Ethernet1/1, dst: S2_BG1, dst_if: Ethernet1/1, policy: multisiteUnderlay, owner: MSD}
    defaults:                   # role -> full default interface policy for free ports (captured at bootstrap)
      spine: {policyType: routedHost, adminState: false, mtu: 9216, speed: auto}
      leaf:  {policyType: trunkHost, adminState: true, allowedVlans: none, mtu: jumbo, ...}
```

## Command

One new entry point, `config/nd/provision/golden.py`, next to `provision.py`:

```text
golden.py drift   --topology <yaml> --nd-ip <ip>                      # read-only; exit 1 on drift
golden.py restore --topology <yaml> --nd-ip <ip> [--yes] [--extras adopt|delete|skip] [--no-deploy]
golden.py adopt   --topology <yaml> --nd-ip <ip> [--classes links,interfaces,...]   # write ND state into golden (bootstrap)
```

`restore` flow: compute drift → print the report → if nothing to do, exit 0 → ask "Apply N create/overwrite
operations to `<nd-ip>`? [y/N]" (skipped with `--yes`) → for each extra, prompt `[a]dopt / [d]elete / [s]kip` (or take
`--extras`) → apply in dependency order (settings, switches, links, interfaces, vrfs/networks, attachments, pairs) →
Recalculate & Deploy every touched fabric, then touched groups → final pending check per switch → print a one-line
summary and the verification reminder ("run the skill's Step 4.6 fabric checks and container pings").
Adoptions are written to the topology file before any push, so a failed push still leaves golden updated.

Report format (per class, stable order, one line per item, hostnames not serials):

```text
SITE1 links      MISSING policy  S1_SP1 Ethernet1/2 <-> S1_LE1 Ethernet1/1   golden=numbered 10.14.0.5/.6  live=none
SITE1 interfaces DIFFERENT       S1_TOR1 Ethernet1/3   golden=accessHost  live=trunkHost allowedVlans=none
SITE1 interfaces EXTRA           S1_BG1 Ethernet1/5    live=trunkHost (role default routedHost)
MSD   settings   DIFFERENT       management.multisiteDelayRestore  golden=300 live=120
```

## Bootstrap (part of this work)

1. Implement `adopt` first; run it against both controllers; review the diff of the two topology files (they must still
   differ only in hostnames/IPs); commit. This is the first golden and the live-vs-file alignment the user asked for.
2. Commit `snapshot.py dump` output for both controllers under `config/nd/provision/golden/{nd421,nd431}/` as a
   frozen reference for `snapshot.py diff` (after confirming the dumps carry no credentials; `normalize()` already strips
   `PASSWORD_ENCRYPT`). The tool does not read these.
3. `drift` on both controllers must then exit 0.

## Skill and docs

- `restore-lab-topologies` skill: Step 4 ends with `golden.py drift` on both controllers; Step 4.6 becomes "if drift,
  run `golden.py restore`", keeping the manual recipes as background. Precondition line: "only when no tests are running".
- `config/nd/provision/README.md`: usage, the three-way extras rule, the "ND-generated links are never deleted" rule.
- Retire `~/tmp/site1_links.py` on glide once `restore` covers it.

## Testing

- Pure drift computation: stub client (as in `tests/test_provision_phases.py`) with canned ND responses for each class;
  assert the report lines and the planned operations, including "no drift" on a golden lab.
- Adopt writer: round-trips a topology file with comments unchanged except the added entries (property test on the
  two shipped files).
- Prompt logic: inject answers; assert nothing is applied on "N", extras honoured per answer, flags override.
- No lab run in tests. Live proof is the bootstrap on both controllers and one deliberate drift (e.g. flip the ToR port
  back to trunkHost) that `drift` reports and `restore` repairs.

## Left to the builder

- Module layout inside the package (one `golden.py` or `golden/` with a module per class); keep `provision.py` phases
  as the write primitives where they exist.
- YAML round-trip library (`ruamel.yaml` is the obvious choice for comment preservation; add it to `pyproject.toml`).
- Exact dependency order and how a refused policy-type change is retried.
- How many extras to prompt before offering "same answer for the rest of this class".

## Decisions I made that the user did not state (please check)

- Golden is the topology yaml, not the snapshot dumps; dumps are committed as a reference only.
- ND-generated links (peer-link/ToR port-channels, multisite, campus) are never deleted by the tool.
- Removing a switch from a fabric is never automatic.
- Fabric settings in golden are a subset; ND keys outside it are not drift.
- "Delete" for an unlisted non-default physical port means "reset to the role default", not an ND DELETE (ND refuses it);
  for logical interfaces it is a real DELETE.
- ND-generated links are a class of their own (`generated_links`, repaired by the owner's deploy); the tool never `PUT`s
  them and never lists them as extras.
- Logical interfaces (vPC, port-channel, subinterface, SVI) are in scope, because the integration tests that caused the
  2026-10-30 damage create and delete exactly those.
- Link /30s are pinned in golden and identical across the two files.
- Free-port detection comes from ND's own link list and port-channel membership, not from a hardcoded port list.
