# nexus9000v Configuration Management

## Global config

global_config.yaml for common settings

## Per-switch configs

Individual YAML files (e.g., ER1.yaml, BG1.yaml)

## Override capability

Switch-specific settings override global defaults

## CLI Interface

### Display sample configs

```bash
python3 nexus9000v.py --create-samples
```

### List available switch configs

python3 nexus9000v.py --list-switches

### Dry run to see command

python3 nexus9000v.py --config ER1.yaml --dry-run

### Actually start the switch

python3 nexus9000v.py --config ER1.yaml

### Use custom global config

python3 nexus9000v.py --config ER1.yaml --global-config my_global.yaml

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
name: ER1
role: Edge Router
sid: 21
mgmt_bridge: BR_ND_DATA
neighbors: [BG1, BG2, CR1]
isl_bridges: [BR_ER1_BG1, BR_ER1_BG2, BR_CR1_ER1]
# Optional overrides
ram: 20480  # More RAM for edge router
```
