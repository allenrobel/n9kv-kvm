# Safe `--create-samples` + Refreshed Samples — Design

Date: 2026-07-17
Status: Approved

## Purpose

`--create-samples` in both VM launchers (`config/nexus9000v/nexus9000v.py` and
`config/8000v/8000v.py`) is a footgun: `create_sample_configs()` writes bare
relative paths (`open("S1_BG1.yaml", "w")`) into the current working directory
with no existence check, no backup, and no confirmation. Run from
`config/nexus9000v/`, it silently overwrites the real per-switch YAMLs — with
stale samples that lack fields the current flow requires. This caused a
lab-host failure: the overwritten switch YAMLs lost `mgmt_ip`/`mgmt_gw` and the
overwritten `global_config.yaml` lost `nxos_boot_image`, so `startup_config.py`
then failed with `KeyError` while building the day-0 ISOs.

This change makes `--create-samples` safe and refreshes the sample content to
the current schema.

## Root cause (verified)

- `nexus9000v.py:700,767` and `8000v.py:609,634` open sample files by bare
  relative name in mode `"w"` — cwd-relative, unconditional overwrite.
- The nexus sample switches (`nexus9000v.py:706-763`) carry only `name`, `role`,
  `sid`, `mgmt_bridge`, `neighbors`, `isl_bridges` — **no** `mgmt_ip`/`mgmt_gw`,
  which `startup_config.py:51,59` require (`switch["mgmt_ip"]`,
  `switch["mgmt_gw"]`).
- The nexus sample global (`nexus9000v.py:686-698`) omits `nxos_boot_image`,
  which `startup_config.py:109` requires (`gcfg["nxos_boot_image"]`).

## Requirements

### 1. Safety mechanics — both launchers

- Samples are written into a **`samples/` subdirectory** of the current working
  directory (`Path("samples")`), created with `mkdir(parents=True,
  exist_ok=True)`. Never write to the working files.
- **Skip existing unless `--force`.** For each target file: if it exists and
  `--force` was not given, print
  `Skipping existing samples/<name> (use --force to overwrite)` and continue;
  otherwise write it and print `Created samples/<name>`.
- Add a `--force` flag (argparse, `action="store_true"`). `main()` passes it to
  `create_sample_configs(force=args.force)`.
- `--list-switches` / `--list-routers` are unchanged and unaffected: they glob
  only the top level of the cwd (`Path.cwd().glob("*.yaml")`), so `samples/` is
  invisible to them (verified).

### 2. Content refresh

**nexus9000v** — replace the 6 stale switches with a self-contained single-site
working topology (Border Gateway → Spine → vPC leaf pair → dual-homed TOR).
Each switch sample carries the full schema, including `mgmt_ip`/`mgmt_gw`.
Every ISL bridge referenced is internal to the sample set:

| Switch | sid | mgmt_ip | neighbors | isl_bridges |
|--------|-----|---------|-----------|-------------|
| S1_BG1 | 1301 | 192.168.12.131/24 | [S1_SP1] | [BR_S1_BG1_SP1_1] |
| S1_SP1 | 1401 | 192.168.12.141/24 | [S1_BG1, S1_LE1, S1_LE2] | [BR_S1_BG1_SP1_1, BR_S1_SP1_LE1_1, BR_S1_SP1_LE2_1] |
| S1_LE1 | 1501 | 192.168.12.151/24 | [S1_SP1, S1_LE2, S1_TOR1] | [BR_S1_SP1_LE1_1, BR_S1_LE1_LE2_1, BR_S1_LE1_T1_1] |
| S1_LE2 | 1502 | 192.168.12.152/24 | [S1_SP1, S1_LE1, S1_TOR1] | [BR_S1_SP1_LE2_1, BR_S1_LE1_LE2_1, BR_S1_LE2_T1_1] |
| S1_TOR1 | 1601 | 192.168.12.161/24 | [S1_LE1, S1_LE2] | [BR_S1_LE1_T1_1, BR_S1_LE2_T1_1] |

All use `mgmt_bridge: BR_ND_DATA_12` and `mgmt_gw: 192.168.12.1`. The BG is
deliberately simplified to a single spine uplink — no cross-site (ISN) or WAN
links — so the sample topology is self-contained and every bridge is a
point-to-point link within the set. The global sample gains
`nxos_boot_image: nxos64-cs.10.6.2.F.bin` (matching the committed
`global_config.yaml`).

**8000v** — the `WAN1` sample already includes `mgmt_ip`/`mgmt_gw`, so its
content is unchanged; it receives the safety mechanics only.

### 3. Docs

Update `config/nexus9000v/README.md` and `config/8000v/README.md` where they
document `--create-samples` to state that it writes to `samples/`, skips
existing files, and accepts `--force`.

## Non-goals

- Not changing how the launchers load or consume configs (`--config`,
  `--global-config` unchanged).
- Not emitting samples for all 16 real switches — samples teach the schema with
  a minimal working topology, they do not mirror the whole lab.
- Not touching `startup_config.py` (its `gcfg["nxos_boot_image"]` subscript is
  intentional fail-fast and stays).

## Error handling

Writing into `samples/` plus skip-existing means the destructive failure mode
(overwriting live config) is structurally impossible: even without `--force`,
samples never land on the working files because they are one directory level
down. `--force` governs only re-overwriting previously generated sample files.

## Validation (no test suite)

- In a scratch directory, place a sentinel `S1_BG1.yaml` alongside, run
  `--create-samples`, and assert: (a) files were written under `samples/`,
  (b) the sentinel top-level `S1_BG1.yaml` is byte-for-byte untouched,
  (c) a second run without `--force` prints skip messages and changes nothing,
  (d) a run with `--force` rewrites them.
- `yaml.safe_load` each generated sample and assert the previously-missing keys
  are present: `mgmt_ip` and `mgmt_gw` in every switch sample, `nxos_boot_image`
  in the global sample — directly proving the `KeyError` bug is closed.
- `mypy` and `flake8` (169 line length) clean on both launchers.
