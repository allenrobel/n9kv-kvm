# Catalyst 8000V (IOS-XE) Configuration Management

Launches Cisco Catalyst 8000V router VMs under QEMU/KVM with OVS TAP wiring,
mirroring the `config/nexus9000v/` pattern. The default image is the
Serial + EFI variant (`c8000v-universalk9_16G_serial_efi.17.15.05.qcow2`):
the VM boots via OVMF firmware and its console is on the serial port.

## Files

- `8000v.py` - the launcher (raw QEMU process, not libvirt; manage by PID)
- `startup_config.py` + `iosxe_startup_config.j2` - day-0 config / boot ISO generator
- `global_config.yaml` - global defaults (image paths, RAM, vCPUs, NIC type)
- `WAN1.yaml` - per-router config (cross-site WAN/ISN router)
- `con_wan1` / `ssh_wan1` - console / SSH one-liners

## Interface mapping

IOS-XE numbers NICs flatly in PCI order:

- `GigabitEthernet1` = management, attached to `mgmt_bridge` (vrf `MGMT` in day-0 config)
- `GigabitEthernet2..N+1` = one per `isl_bridges` entry (WAN/ISN links)

TAP names are `tap<sid>-<index>` (e.g. `tap9101-0`). Bridges are referenced,
not created - create them first via `config/bridges/`.

## Bringup

```bash
# 1. Build the day-0 boot ISO (password from $IOSXE_PASSWORD or $NXOS_PASSWORD)
sudo -E python3 startup_config.py WAN1.yaml

# 2. Launch the VM (copies the base qcow2, creates TAPs, starts QEMU)
sudo python3 8000v.py --config WAN1.yaml

# 3. Watch it boot (first boot takes several minutes; RSA keys generate ~60s after boot)
./con_wan1
```

## Other operations

```bash
python3 8000v.py --config WAN1.yaml --dry-run   # inspect the QEMU command
python3 8000v.py --list-routers                 # list router YAMLs
sudo python3 8000v.py --config WAN1.yaml --teardown  # remove TAPs after stopping the VM
python3 startup_config.py --print WAN1.yaml     # render day-0 config to STDOUT
```

## Day-0 behavior

`startup_config.py` renders `iosxe_config.txt` from the per-router YAML and
wraps it in `<cdrom_path>/<name>.iso`; the C8000V consumes it from the cdrom
on first boot. The rendered config puts `GigabitEthernet1` in vrf `MGMT` with
a vrf default route (the global table stays clean for WAN/ISN routing),
creates the `admin` user, enables SSH, and installs a one-shot EEM applet
that generates the RSA keypair 60 seconds after boot and then removes itself
(`crypto key generate rsa` is an exec command and cannot live in a config file).
