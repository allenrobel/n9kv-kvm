# Catalyst 9000v (Cat9kv) Configuration Management

Launches Cisco Catalyst 9000v switch VMs under QEMU/KVM with OVS TAP wiring, mirroring the
`config/8000v/` pattern. The image is the UADP flavor from the CML 2.9 reference platform
(`cat9kv_prd.17.15.03.qcow2`, IOS-XE 17.15.03): a **beta with no TAC support**, about 250 kbps of
dataplane, and it may crash under traffic load. It is fine for what the lab needs: an ND-managed
Catalyst leaf for the `cisco.nd` IOS-XE interface integration tests.

Design: `docs/superpowers/specs/2026-09-11-cat9kv-campus-leaf-design.md`.

## Files

- `cat9kv.py` - the launcher (raw QEMU process, not libvirt; manage by PID)
- `startup_config.py` + `iosxe_startup_config.j2` + `vswitch.xml` - day-0 config / boot ISO generator
- `global_config.yaml` - global defaults (image paths, RAM, vCPUs, NIC type, minimum NIC count)
- `C1_LE1.yaml`, `C3_LE1.yaml` - per-switch configs (ND 4.2.1 and ND 4.3.1 campus leaves)
- `C1_SP1.yaml`, `C3_SP1.yaml` - per-switch configs (ND 4.2.1 and ND 4.3.1 campus spines, one leaf-spine link each)
- `con_c1_le1` / `ssh_c1_le1`, `con_c3_le1` / `ssh_c3_le1` - console / SSH one-liners (leaves)
- `con_c1_sp1` / `ssh_c1_sp1`, `con_c3_sp1` / `ssh_c3_sp1` - console / SSH one-liners (spines)
- `tests/` - pytest for the pure parts (`uv run pytest config/cat9kv/tests`)

## Launch parameters (from the CML node definition)

4 vCPU, 18432 MB (less does not boot), `e1000` NICs, IDE boot disk, BIOS boot (`-machine pc`, no OVMF),
two serial ports with the console on the first (`telnet localhost 10000+sid`). Boot takes up to 600 s and
is done when the console shows `Press RETURN to get started!` or `%SSH-5-ENABLED:`.

## Interface mapping

IOS-XE numbers the NICs in PCI order:

- `GigabitEthernet0/0` = management, attached to `mgmt_bridge` (vrf `Mgmt-vrf` in the day-0 config)
- `GigabitEthernet1/0/1..N` = one per `isl_bridges` entry (front-panel ports)
- `GigabitEthernet1/0/N+1..8` = padding: the image refuses to boot with fewer than nine NICs
  (`min_nics` in `global_config.yaml`), so the launcher creates TAPs for them but attaches them to no bridge

The campus leaves carry one fabric link, to the campus spine, on `GigabitEthernet1/0/8` (`isl_ports: [8]`), so
`GigabitEthernet1/0/1..7` stay free for the cisco.nd IOS-XE interface tests. `isl_ports` is parallel to
`isl_bridges` (same length, same order): it gives the front-panel port number for each ISL, defaulting to `1..N`
when omitted, and lets a link land on a non-contiguous port instead of the first N; the NIC count (padding)
grows to cover the highest port named in it.

TAP names are `tap<sid>-<index>` (e.g. `tap1701-0`). Bridges are referenced, not created - create them first
via `config/bridges/`.

## Day-0 behavior

`startup_config.py` renders `iosxe_startup_config.j2` into `iosxe_config.txt`, substitutes the switch serial
(`CAT9KV<sid>`) into `vswitch.xml`, and wraps both in `<cdrom_path>/<name>.iso` with volume label `CDROM`
(`genisoimage -V CDROM -r -J`). The image reads `iosxe_config.txt` as its startup config and
`conf/vswitch.xml` as the ASIC selector (`board_id 20612` = UADP; `port_count 24` is left as Cisco ships it
regardless of NIC count). Pinning the serial keeps ND's switch identity stable across reloads.

The rendered config puts `GigabitEthernet0/0` in `Mgmt-vrf` with a vrf default route, creates the `admin`
user, enables SSH, and installs a one-shot EEM applet that generates the RSA keypair 60 seconds after boot
and then removes itself.

## Bringup

```bash
# 1. Build the day-0 boot ISO (password from $IOSXE_PASSWORD or $NXOS_PASSWORD)
sudo -E python3 startup_config.py C1_LE1.yaml

# 2. Launch the VM (copies the base qcow2, creates TAPs, starts QEMU)
sudo python3 cat9kv.py --config C1_LE1.yaml

# 3. Watch it boot (up to 10 minutes; RSA keys generate ~60 s after boot)
./con_c1_le1
```

## Other operations

```bash
python3 cat9kv.py --config C1_LE1.yaml --dry-run    # inspect the QEMU command
python3 cat9kv.py --config C1_LE1.yaml --debug      # launch with QEMU output + status checks
python3 cat9kv.py --list-switches                   # list switch YAMLs
python3 cat9kv.py --create-samples                  # write samples to ./samples/ (skip existing)
sudo python3 cat9kv.py --config C1_LE1.yaml --teardown  # remove TAPs after stopping the VM
sudo python3 cat9kv.py --config C1_LE1.yaml --attach    # attach a running switch's existing TAPs to their bridges (re-cable live, no reload)
python3 startup_config.py --print C1_LE1.yaml       # render day-0 config to STDOUT
sudo -E python3 startup_config.py --all             # build day-0 ISOs for every switch YAML
```

## ND placement

Each `CAMPUS1` (ND 4.2.1: `C1_LE1`/`C1_SP1`; ND 4.3.1: `C3_LE1`/`C3_SP1`) holds a leaf and a spine joined by
one intra-fabric link, which ND stamps as an `iosXeNumbered` link policy at Recalculate; `config/nd/provision/`
creates the fabric and adds both switches. The link exists so the fabric-link ownership guard (PR #558) has a
corruptible, rebuildable endpoint to test against, without touching the leaf's `GigabitEthernet1/0/1..7`, which
the cisco.nd IOS-XE interface tests need free. Catalyst switches cannot join the NX-OS `vxlanIbgp` fabrics
(SITE1/SITE2).
