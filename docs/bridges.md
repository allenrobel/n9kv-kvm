# Setup Bridges

The lab's data-plane bridges are Open vSwitch (OVS) bridges. The VM launchers
(`config/nexus9000v/nexus9000v.py` and `config/8000v/8000v.py`) attach each
VM's TAP interfaces to these bridges with `ovs-vsctl`, so the bridges must be
OVS bridges, not Linux bridges.

Two layers create and configure them:

- **netplan** (`config/bridges/netplan/9912-bridges.yaml`) creates the bridges
  declaratively and persists them across reboot (MTU 9216, `stp: false`).
- **`bridges_config_ovs.sh`** asserts the OVS settings netplan does not set —
  notably `other-config:forward-bpdu=true`, which LACP / vPC peer-links need,
  plus the jumbo `mtu_request` — and creates any bridge that is missing.

## Configure netplan

Inspect and edit the OVS bridge definitions to match your host:

<!-- pyml disable-next-line commands-show-output -->
```text
$HOME/repos/n9kv-kvm/config/bridges/netplan/9912-bridges.yaml
```

In particular, verify that:

- The physical interface exists. Change the interface name (`eno6` in the file)
  to match your host — see the `link` parameter for `Vlan12`. Check your
  interfaces with `ip link show`.
- Vlan 12 is not already associated with your interface (the `id` parameter for
  `Vlan12`).
- The bridge names (e.g. `BR_ND_DATA_12`, `BR_S1_BG1_SP1_1`) don't conflict with
  existing bridges on your host.
- The IP address (`192.168.12.2/24` on `BR_ND_DATA_12`) doesn't conflict with
  other addresses on your host or network.

## Copy the bridges configuration into /etc/netplan

```bash
cd $HOME/repos/n9kv-kvm/config/bridges/netplan
sudo cp ./9912-bridges.yaml /etc/netplan
sudo chmod 600 /etc/netplan/9912-bridges.yaml
```

## Apply the bridges configuration

```bash
sudo netplan try
sudo netplan apply
```

`netplan try` may warn that reverting custom parameters for bridges is not
supported; proceed with `netplan apply` directly. If netplan warns that
`/etc/netplan/*` permissions are too open, tighten them and re-apply:

```bash
sudo chown root /etc/netplan/*
sudo chmod 600 /etc/netplan/*
```

## Assert the OVS settings

Run the OVS config script to set `forward-bpdu`, the jumbo MTU, and create any
bridge netplan did not. It is idempotent, so it is safe to re-run.

```bash
cd $HOME/repos/n9kv-kvm/config/bridges
sudo ./bridges_config_ovs.sh
```

## Verify

```bash
# List the OVS bridges
sudo ovs-vsctl list-br | grep BR_

# Full OVS state (bridges, ports, MTU)
sudo ovs-vsctl show
```

The bridges have no ports until you bring up the VMs; each launcher creates the
VM's TAP interfaces and attaches them to their bridges at launch.
