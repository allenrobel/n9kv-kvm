# Migrate LXC Host Containers to OVS — Design

Date: 2026-07-17
Status: Approved

## Purpose

The lab's switch VMs have transitioned to Open vSwitch, but the LXC
host-endpoint containers under `config/containers/` still attach to their
bridges the Linux way: libvirt `<interface type='bridge'>` with no OVS
virtualport, plus a host-side VLAN-filtering step (`bridge vlan` /
`vlan_filtering`). The container test bridges (`BR_S1_LE1_H1_1`,
`BR_S2_LE1_H1_1`) and the shared management bridge (`BR_ND_DATA_12`) are
already OVS bridges (they are created by `config/bridges/bridges_config_ovs.sh`),
so the host-side VLAN-filtering call cannot succeed against them today. This
migration attaches the containers to OVS and removes the now-dead host-side
VLAN path.

This is **Part 1** of a two-part effort. Part 2 (retiring the Linux-bridge
config files — `bridges_config_linux.sh`, the top-level Linux netplan YAMLs,
`bridge.conf` — and reconciling the bringup docs) is deliberately **out of
scope** here and will be a separate spec/plan/PR.

## Key insight

In trunk mode the container tags its own frames: `config_generators.py`
renders `ip link add link eth1 name eth1.<id> type vlan id <id>` inside the
container init script, so 802.1Q happens *inside* the container. On OVS, the
switch-side taps on the same bridge are attached trunk-all (nexus9000v.py sets
no VLAN), so tagged frames pass container → OVS → leaf transparently with no
host-side VLAN configuration. This is exactly how the switch VMs already
interoperate, so the host-side VLAN-filtering code is unnecessary on OVS and
is removed rather than reimplemented.

Access mode (container `eth1` untagged with a direct IP) also needs no
host-side config: an OVS port with no VLAN settings passes untagged frames.

## Scope of change

### Core — attach to OVS

- `config/containers/libvirt_manager.py` (interface blocks, currently lines
  49-58): add `<virtualport type='openvswitch'/>` to **both**
  `<interface type='bridge'>` elements — the management interface (on
  `BR_ND_DATA_12`) and the test interface (on `BR_S*_LE1_H1_1`). Both target
  OVS bridges, so both need the virtualport element.

### Remove the dead host-side VLAN path

- `config/containers/orchestrator.py`: delete `_setup_bridge_vlans` (lines
  74-77) and its call in `create_container` (line 50); remove the
  `bridge_manager` constructor parameter, the `self.bridge_manager` attribute,
  and the `from bridge import BridgeVLANManager` import. Reword the
  "Bridge VLAN Configuration" block in `_print_usage_info` (lines 110-117) so
  it states that VLANs are carried by the container and passed trunk-all by
  OVS, with no host-side bridge configuration.
- `config/containers/factory.py` (lines 8, 27): drop the `BridgeVLANManager`
  import and its instantiation/wiring into the orchestrator.
- `config/containers/bridge.py`: **delete** the file. `BridgeVLANManager` is
  its only class and `factory.py`/`orchestrator.py` are its only consumers.
- `config/bridges/add_vlans_BR_S1_LE1_H1_1.sh`,
  `config/bridges/add_vlans_BR_S2_LE1_H1_1.sh`,
  `config/bridges/vlans_del_BR_S1_LE1_H1_1.sh`,
  `config/bridges/vlans_del_BR_S2_LE1_H1_1.sh`: **delete** all four. These are
  manual Linux `bridge vlan` scripts for the host test bridges, made dead by
  dropping host-side VLAN filtering.

### Unchanged (important)

- `config/containers/models.py` keeps the `vlans` field — container-internal
  tagging still uses it.
- `config/containers/config_generators.py` is unchanged — the container still
  builds `eth1.<id>` subinterfaces; trunk mode still works, with the container
  doing the tagging.
- `container_configs_access_mode.yaml` / `container_configs_trunk_mode.yaml`
  are unchanged.

### Docs (container subsystem only)

- `config/containers/README.md` (the `vlan_filtering` instruction around line
  239): replace the Linux-bridge VLAN-filtering guidance with the OVS model
  (virtualport attachment; VLANs carried by the container and passed trunk-all
  by OVS; no host-side VLAN config). Remove references to the deleted
  `add_vlans_*` / `vlans_del_*` scripts.

## Error handling

No new error paths. Removing `_setup_bridge_vlans` removes a call that would
fail against an OVS bridge, so container creation becomes *more* robust on the
OVS host, not less. The libvirt define/undefine flow is unchanged.

## Validation

No test suite exists in this repo (deliberate — see CLAUDE.md). Validate with:

- `mypy` and `flake8` (169-char limit) clean on the changed Python
  (`orchestrator.py`, `factory.py`, `libvirt_manager.py`); `bridge.py` removed.
- A focused Jinja render check that renders the `libvirt_manager.py` interface
  XML for an access-mode spec and a trunk-mode spec and asserts **both**
  interfaces emit `<virtualport type='openvswitch'/>` with the correct source
  bridges.
- **Lab-host step (the decisive one):** define a container on the Ubuntu OVS
  host, confirm its libvirt-assigned vnet appears under the target bridge in
  `ovs-vsctl show`, and verify end-to-end reachability (mgmt ping, and a
  trunk-mode VLAN ping). This is where the one real assumption —
  **libvirt-LXC supports `<virtualport type='openvswitch'/>`** — is proven; it
  cannot be verified on the dev Mac (no libvirt/OVS).

## Assumptions and risks

- **libvirt-LXC + OVS virtualport.** libvirt's Open vSwitch integration lives
  at the generic interface layer and is expected to apply to `type='lxc'`
  domains, attaching the vnet via `ovs-vsctl add-port`. This is the migration's
  central assumption; it is verifiable only on the lab host (see Validation).
  If it does not hold on the host's libvirt version, the fallback is a
  post-define `ovs-vsctl add-port` step keyed off the libvirt-assigned target
  device — noted here so the risk is visible, but not built unless needed.

## Explicitly deferred to Part 2

`config/bridges/bridges_config_linux.sh`, the top-level Linux netplan YAMLs
(`config/bridges/9912-bridges.yaml`, `9914`, `9915`), `config/bridges/bridge.conf`,
and the bringup-doc reconciliation (`docs/bridges.md`,
`docs/manual_vpc_bringup_s1.md`) are **not** touched by this work.
