# nexus9000v Configuration Management

## Global config

global_config.yaml for common settings

## Per-switch configs

Individual YAML files use the schema `S<site>_<role><idx>.yaml` (e.g., `S1_BG1.yaml`, `S2_SP1.yaml`, `S1_LE1.yaml`). Site membership is encoded in the
filename and the `name:` field; role indices are renumbered per-site starting at 1.

## Override capability

Switch-specific settings override global defaults

## CLI Interface

### Create sample configs

Writes a sample `global_config.yaml` and a small example topology (a
single-site Border Gateway → Spine → vPC leaf pair → TOR) into a `samples/`
subdirectory — never the working directory. Existing files are skipped unless
`--force` is given.

```bash
python3 nexus9000v.py --create-samples          # write to ./samples/, skip existing
python3 nexus9000v.py --create-samples --force  # overwrite existing samples
```

### List available switch configs

python3 nexus9000v.py --list-switches

### Dry run to see command

python3 nexus9000v.py --config S1_LE1.yaml --dry-run

### Actually start the switch

python3 nexus9000v.py --config S1_LE1.yaml

### Use custom global config

python3 nexus9000v.py --config S1_LE1.yaml --global-config my_global.yaml

## Sample global config

```yaml
image_path: /iso1/nxos
cdrom_path: /iso2/nxos/config
default_ram: 16384
default_vcpus: 4
base_mac: "52:54:00"
```

## Sample switch config

```yaml
name: S1_LE1
role: Leaf Switch
sid: 51
mgmt_bridge: BR_ND_DATA_12
neighbors: [S1_SP1, S1_LE2]
isl_bridges: [BR_S1_SP1_LE1_1, BR_S1_LE1_LE2_1]
# Optional overrides
ram: 20480
```

Bridge naming: `BR_S<site>_<upper>_<lower>_<n>` for intra-site links (upper = higher in topology BG > SP > LE > T; `TOR` is shortened to `T` in bridge names
only, to fit under Linux's 15-char IFNAMSIZ limit), `BR_ISN_S<a>_S<b>_<n>` for cross-site links. Link-index suffix `_<n>` always present.
