# Golden baselines for both replication modes, and a `convert` command

Date: 2026-11-13. Status: draft for approval.

## Intent

Each testbed (ND 4.2.1 at 10.10.20.10, ND 4.3.1 at 10.10.20.20) must be switchable between multicast and ingress replication on demand, so the
`cisco.nd` interface test suite can run against fabrics in either mode. Each mode needs its own golden definition, so `golden.py drift` and
`restore` are correct whichever mode a testbed is in, and the switch itself must be one repeatable command.

Background and the ND behaviour this builds on: `docs/nd_replication_mode_change.md`.

## Goals

- One golden definition per testbed and per replication mode, for `SITE1` and `SITE2`.
- `golden.py convert` takes a testbed from its current mode to the other and ends on a zero-drift check against the target mode's golden.
- `provision.py` can build a fresh testbed directly in either mode.
- `drift`, `restore` and `adopt` work in both modes without the operator having to remember which mode a testbed is in.
- Both directions proven in the lab on ND 4.2.1 before anyone relies on them.

## Non-goals

- `CAMPUS1` keeps its current replication mode. Only the two `vxlanIbgp` fabrics get modes.
- No mixed state as a supported target: `SITE1` and `SITE2` of one testbed are always converted together.
- No change to the generic `restore` operation order beyond the one described under "Gaps to close".
- The two testbeds do not have to be in the same mode as each other.

## Anti-goals

- Four near-identical topology files. Anything that is not mode-specific must exist once per testbed.
- A silent default mode. A tool must never push multicast settings at an ingress testbed (or the reverse) because a flag was left out.
- A `convert` that leaves a testbed half converted with no way forward other than manual REST calls.

## Constraints (from the 2026-11-13 lab run on ND 4.3.1)

- ND refuses the mode change at Recalculate while the fabric has any "overlay definition", which includes VRFs, networks, `ebgpVrfLite`
  links and, per ND's own message text, Multi-Site inter-fabric connections. The check fires per switch that still holds the old mode's
  underlay policy.
- A `PUT /fabrics/{f}` to `ingress` is rejected (HTTP 400) while the body still carries `anycastRendezvousPointIpRange`. After the change ND
  no longer returns the multicast-only keys.
- The first deploy after the mode change leaves pending lines; the existing `config_deploy` retry clears them.
- ND refuses a network attachment on a border gateway until the group's Recalculate and Deploy has generated the multisite links.
- A network created in `MSD` before its ingress fabrics are members gets `enableIr: false` on the member copies and a dead L2 VNI with
  nothing pending. Created after, ND sets `enableIr: true` itself. `enableIr` can be changed only on the member copies.
- `DELETE /links/{id}` on an `ebgpVrfLite` link leaves the discovered link under the same id; the existing `put_link` fix restores the policy
  and the pinned /30.
- Ingress to multicast has not been run. ND's template has the mirror check (keyed on the `ingress_rep_simulated` policy), so the same
  procedure is expected to work.

## Approaches

1. **One topology file per testbed with a per-mode settings overlay (chosen).** The two modes differ only in a handful of fabric settings, so
   the file states the common part once and the delta per mode. The hostname/IP mirror between the two testbed files is kept.
2. **Four full topology files.** No loader change, but about 95% of each file is duplicated and every later edit has to be made four times.
   Rejected: this is the duplication the mirror tests exist to prevent, doubled.

Chosen by the user on 2026-11-13, together with a `convert` command rather than a runbook.

## Design

### Topology file

A fabric may carry `replication_modes`, a map from mode name to a settings delta with the same shape as `settings`:

```yaml
fabrics:
  - name: SITE1
    type: vxlanIbgp
    asn: "65001"
    settings:                 # common to both modes
      management:
        bgpLoopbackIpRange: 10.11.0.0/22
        ...
    replication_modes:
      multicast:
        management:
          replicationMode: multicast
          anycastRendezvousPointIpRange: 10.13.0.0/24
      ingress:
        management:
          replicationMode: ingress
```

- `topology.load(path, replication_mode=None)` merges the chosen mode's delta over `settings` (same deep merge as `merge_settings`) and
  records the mode on the `Topology`. The rest of the code keeps reading `fabric.settings`.
- Validation at load: mode names are `multicast` or `ingress`; every fabric that declares modes declares both; each delta sets
  `management.replicationMode` to its own name; a key may not appear both in `settings` and in a mode delta.
- A file whose fabrics declare modes cannot be loaded without a mode (error naming the flag). A file with no `replication_modes` loads
  exactly as today, so the test fixtures and any private topology files keep working.
- Both shipped files gain the section for `SITE1` and `SITE2`. The uncommitted edit on branch `nd431-ingress-replication` is replaced by it.

### What "in a mode" means

The saved fabric setting is not enough: ND accepts the `PUT` at once and converts only at the following Recalculate and Deploy. A fabric
is **in** a mode when all three hold: `management.replicationMode` equals it, no switch of the fabric holds the other mode's underlay
policy (`base_multicast_11_1` or `base_pim_asm_v6` for a fabric going to ingress, `ingress_rep_simulated` for one going to multicast; the
same policies ND's own check reads), and no switch has pending config. A fabric whose setting and policies disagree is **mid-conversion**.
`golden_live` reads the per-switch policy template names for the mode-bearing fabrics to decide this.

### Choosing the mode

- `provision.py --replication-mode multicast|ingress`: required when the topology declares modes.
- `golden.py drift|restore|adopt --replication-mode ...`: optional. When omitted the tool reads `management.replicationMode` of the
  mode-bearing fabrics from the live ND (or the snapshot) and uses that, printing `replication mode: ingress (detected)`. If the fabrics
  disagree with each other, or any is mid-conversion, it exits 2 and points at `convert`. A snapshot holds no policy dump, so there the
  setting alone decides.
- `restore` with an explicit mode that differs from the live mode exits 2 and points at `convert`. A settings `PUT` cannot perform the change.
- `provision.py --phase fabrics` refuses (exit 2, pointing at `convert`) to `PUT` a `replicationMode` that differs from the live one onto a
  fabric that already has switches. On a new or empty fabric it sets the mode directly.
- `golden.py convert --replication-mode ...`: required; it is the target.

### Settings push in ingress mode

`provision.py` owns a constant list of the multicast-only keys ND rejects or drops in ingress mode (`anycastRendezvousPointIpRange`,
`multicastGroupSubnet`, `rendezvousPointLoopbackId`, `underlayMulticastGroupAddressLimit`, `autoGenerateMulticastGroupAddress`,
`tenantRoutedMulticastIpv6`). Every fabric settings `PUT` built for a target of `ingress` removes them from the merged body. This applies to
`phase_fabrics`, the `put_settings` fix and `convert`.

### `golden.py convert`

```text
golden.py convert --topology T.yaml --nd-ip IP --replication-mode ingress [--yes] [--extras adopt|delete|skip] [--dry-run]
```

It prints the plan (current mode, target mode, every object it will remove), asks for confirmation unless `--yes`, then runs:

1. **Preflight.** Read live and classify each mode-bearing fabric as in the source mode, mid-conversion, or in the target mode. If all are
   in the target mode, skip to step 7. If the testbed is intact in the source mode (overlay, group members and VRF-Lite links all as
   golden) and a switch has pending config, refuse (exit 2) so a conversion starts from a deployed state. In any other state pending
   config is expected and is not a reason to refuse.
2. **Remove the overlay.** Detach, deploy and delete every network, then every VRF, found live in the mode-bearing fabrics and their group,
   golden or not. This reuses the op sequence `restore --extras delete` already builds for an extra VRF or network.
3. **Leave the group.** Remove the mode-bearing fabrics from their fabric group (`POST /fabrics/{group}/actions/removeMembers`), then
   Recalculate and Deploy those fabrics so the multisite configuration is withdrawn.
4. **Delete the VRF-Lite links.** Every live `ebgpVrfLite` link of those fabrics, golden or not. Step 7 restores the golden ones; a
   non-golden one stays a bare discovered link.
5. **Change the mode.** `PUT` the target mode's settings per fabric, with the ingress key stripping where it applies.
6. **Recalculate and Deploy** each converted fabric with `config_deploy`. Verify the live `replicationMode` and that nothing is pending.
7. **Rebuild.** Re-add group members, restore the VRF-Lite links, Recalculate and Deploy the fabrics and then the group, then run the normal
   `restore` against the target mode's golden (`--extras` is passed through and has the same rules as `restore`).
8. **Verify.** Re-read, print remaining drift and pending counts. Exit 0 only on zero drift and nothing pending.

Every step decides what to do from the live state, never from a record of earlier steps. A run that stops part way (exit 4) is continued
by running the same command again: each of steps 2 to 4 skips what is already gone, and steps 5 and 6 run for every fabric that is not yet
in the target mode by the definition above. A fabric whose setting was saved but never deployed is therefore mid-conversion, not converted,
and the rebuild never starts while one exists. A testbed that is in the target mode but missing members, links or overlay is finished by
the rebuild.

`--dry-run` sends nothing. It prints the classification of each fabric, the exact calls of the first step that has work to do, and for
the later steps the objects each will act on as far as the current live state shows them (networks and VRFs to remove, members to remove,
links to delete, fabrics to convert, golden objects to rebuild). It does not simulate ND state between steps.

The removed overlay and links are printed before confirmation because they can include objects that are not in the golden file (test
residue). They are deleted, not adopted: ND will not change the mode around them.

### Gaps to close in `golden.py`

- **Group membership** becomes a drift class: a golden member missing from the live group is `MISSING` with an `add_member` fix; a live
  member not in golden is reported only. `add_member` ranks before link and overlay ops, and when an apply contains one the `Applier`
  finishes the link ops and then Recalculates and Deploys the member fabrics and the group before it sends any overlay op. That is the one
  order change to `restore`: without it a single pass would create networks and attach border gateways before the multisite links exist.
  Networks are created after the member add, so ND sets `enableIr` itself; the fix below is the backstop for a testbed found in that state.
- **`enableIr` on member copies.** In ingress mode, a member-fabric copy of a golden network with `enableIr: false` is `DIFFERENT`, with a fix
  that `PUT`s the member copy and deploys the network there. In multicast mode the flag is not compared.
- **Multicast-only keys** are stripped as described above.

### Reference snapshots

`golden/nd421/` and `golden/nd431/` (not read by any tool) become `golden/<nd>/<mode>/`. The existing dumps move to `multicast/`; an
`ingress/` dump is taken from each testbed the first time it is in that mode with zero drift.

### Tests

- Loader: delta merge, each validation rule, a mode-less file unchanged, a mode-bearing file refused without a mode.
- The two mirror tests in `test_topology.py` run once per mode.
- Key stripping: an ingress `PUT` body never carries the multicast-only keys; a multicast body carries the pinned RP range.
- Mode detection: detected, explicit, fabrics disagreeing, explicit mode differing from live on `restore`.
- `convert`: the ordered call list from a fully provisioned multicast testbed; the same for ingress to multicast; resume from each
  intermediate state (no overlay, out of group, links deleted, setting saved but not deployed, converted but not rebuilt); the pending
  config refusal only in the intact source state; `--dry-run` sends nothing. These use the recording fake client the existing
  `test_golden_apply.py` and `test_provision_phases.py` use.
- Membership and `enableIr` drift classes and their fixes.

### Documentation

`config/nd/provision/README.md` (usage, the new flag, `convert`), `CLAUDE.md` (the golden-baseline note), and
`docs/nd_replication_mode_change.md` (procedure section points at `convert`; the reverse direction is recorded once proven).

## Lab validation

On ND 4.2.1 only, which is not in use. ND 4.3.1 is not touched while the interface tests run there; it is already in ingress mode and only
needs a read-only `drift` against the reshaped file once it is free.

1. `convert --replication-mode ingress --dry-run`, review the call list.
2. Multicast to ingress. Check zero drift, `show nve vni` reports `UnicastBGP`, host ping `S1_H1` to `S2_H1`.
3. Ingress to multicast. Check zero drift, `show nve vni` reports the multicast group, PIM neighbours and RP are back, host ping.
4. Interrupt one conversion after step 3 and one between steps 5 and 6, rerun, confirm it completes.
5. Multicast to ingress again, leaving ND 4.2.1 in ingress mode, which is the state the test suite wants.

The host pings need root on the lab host and are run by the user.

Each conversion is expected to take 20 to 30 minutes, most of it ND's synchronous Recalculate and Deploy calls.

## Open questions the lab run answers

- Whether step 3 is required, and whether removing members alone withdraws the multisite configuration or a group deploy is also needed.
- Which multicast keys ND requires in the body when going back to multicast. If it needs more than `replicationMode` and the RP range, the
  multicast delta in both topology files gains those keys with the values in `golden/*/multicast/fabric_SITE*.json`.
- Whether ND re-allocates the same anycast RP address, loopback 254 and RP loopback addresses when multicast returns. If not, the reference
  snapshot is re-taken; no golden-file entry pins them today.
- Whether vPC and ToR pairings survive both directions untouched (they did for multicast to ingress on ND 4.3.1).

## Left to the builder

Module placement of `convert` (a new `golden_convert.py` beside the other `golden_*` modules is the expected shape), names of helpers, and
the exact wording of messages. Exit codes follow the existing table: 0 ok, 2 refused or cancelled, 3 live read failed, 4 apply failed.
