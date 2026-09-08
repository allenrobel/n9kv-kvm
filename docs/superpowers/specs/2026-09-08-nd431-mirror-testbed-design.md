# ND 4.3.1 Mirror Testbed (SITE3/SITE4 + WAN2) Design

Date: 2026-09-08. Status: proposed, awaiting review.

## Goal

Run a second, independent copy of the ND 4.2.1 lab under ND 4.3.1.175, identical in every respect except device names and
management addresses, and formalize the ND-side provisioning (fabrics, MSD membership, switch onboarding, ISN links and
WAN policies, overlay VRF/network/attachments) that today lives only in session memory and the `provision-isn` skill.

The two testbeds share one host (glide-wired.laukapu.com) and nothing else: ND 4.2.1 and its devices manage over
`BR_ND_DATA_12` (192.168.12.0/24), ND 4.3.1 and its devices over `BR_ND_DATA_14` (192.168.14.0/24). Every data-plane
bridge is per-testbed too, so underlay/overlay address pools, ASNs, VNIs and fabric names can be byte-identical.

## Facts established (2026-09-08, read-only inspection of the host)

- `nd.4.2.1.10.node1` and `nd.4.3.1.175.node1` are both running, both with `outside` (mgmt) + `BR_ND_DATA_12` (data).
  The ND 4.3.1 placement on `BR_ND_DATA_12` (node data IP 192.168.12.15) was a quick verification install; the user will
  tear it down and re-instantiate it on `BR_ND_DATA_14` so that its node data IP and persistent IPs mirror ND 4.2.1's
  on 192.168.14.0/24: node data IP 192.168.14.14 (ND 4.2.1 is 192.168.12.14), persistent data IPs 192.168.14.30-.32,
  persistent mgmt IPs 10.10.20.60-.62, node mgmt IP 10.10.20.20/16 (unchanged).
  `config/nd/nd-4-3-1-175-node1.sh` still says `ND_DATA_NET=BR_ND_DATA_12` and must be changed before the re-install.
- The host still carries every bridge from `9914-bridges.yaml` (`BR_ND_DATA_14`, `BR_ISN_S3_S4_1`, `BR_S3_*`, `BR_S4_*`
  including the `S4_LE2/S4_LE3/H2` set) and from `9915-bridges.yaml`. No S3/S4 VMs, no WAN2, no S3/S4 containers exist.
- Running: S1_BG1, S1_SP1, S1_LE1-4, S1_TOR1, S2_BG1, S2_SP1, S2_LE1, WAN1. Containers S1_H1/S2_H1 are defined but shut off.
- The existing `S3_*.yaml`/`S4_*.yaml` describe a *different* topology (no LE2-4, no TOR, no WAN, an extra S4 leaf pair
  toward a non-existent `S4_H2`). Their management network (`BR_ND_DATA_14` / 192.168.14.x) is right; the topology is not.
  They must be rewritten.

## Decisions

### D1. Management network: `BR_ND_DATA_14`, 192.168.14.0/24, gateway 192.168.14.1

ND 4.3.1 is re-instantiated with its data interface on `BR_ND_DATA_14` (`Vlan14`, host address 192.168.14.2/24, already in
`9914-bridges.yaml` and live on the host). Every S3/S4 switch, WAN2 and the S3/S4 containers manage over it. Nothing else
changes on the host side: `9914-bridges.yaml` keeps `Vlan14`/`BR_ND_DATA_14` and gains the data-plane bridges of D4.

Alternative rejected (2026-09-08, user decision): keeping ND 4.3.1 on `BR_ND_DATA_12`. That forced a second address plan
on the shared segment and made "mirror" an exception rather than a substitution.

### D2. Management address plan: same last octet, third octet 12 -> 14

Every mirror device takes its counterpart's address with the third octet changed from 12 to 14, so the whole address plan
(`.13x` BG, `.14x` SP, `.15x` LE, `.16x` TOR, `.17x` hosts, `.11x` WAN) is reused unchanged and any address can be mapped
in one's head. ND 4.3.1's own node data IP (192.168.14.14) and persistent IPs (192.168.14.30-.32) follow the same rule.

| Device  | Mirror of | sid  | mgmt IP         | console port | Test-net IP (hosts) |
|---------|-----------|------|-----------------|--------------|---------------------|
| S3_BG1  | S1_BG1    | 3301 | 192.168.14.131  | 13301        |                     |
| S3_SP1  | S1_SP1    | 3401 | 192.168.14.141  | 13401        |                     |
| S3_LE1  | S1_LE1    | 3501 | 192.168.14.151  | 13501        |                     |
| S3_LE2  | S1_LE2    | 3502 | 192.168.14.152  | 13502        |                     |
| S3_LE3  | S1_LE3    | 3503 | 192.168.14.154  | 13503        |                     |
| S3_LE4  | S1_LE4    | 3504 | 192.168.14.155  | 13504        |                     |
| S3_TOR1 | S1_TOR1   | 3601 | 192.168.14.161  | 13601        |                     |
| S3_H1   | S1_H1     | n/a  | 192.168.14.171  | n/a          | 192.0.1.171         |
| S4_BG1  | S2_BG1    | 4301 | 192.168.14.132  | 14301        |                     |
| S4_SP1  | S2_SP1    | 4401 | 192.168.14.142  | 14401        |                     |
| S4_LE1  | S2_LE1    | 4501 | 192.168.14.153  | 14501        |                     |
| S4_H1   | S2_H1     | n/a  | 192.168.14.172  | n/a          | 192.0.1.172         |
| WAN2    | WAN1      | 9102 | 192.168.14.112  | 19102        |                     |

Console port = 10000 + sid, QEMU monitor = 20000 + sid, MACs derive from sid (unchanged launcher behaviour). Host
container test-network addresses are identical to their counterparts (192.0.1.171/.172): the overlay is a separate L2/L3
domain per testbed. The one deliberate non-mirror is the container MACs, `00:00:73:...` / `00:00:74:...` instead of
`00:00:71/72`, so that the upstream `eno6` trunk never learns one MAC on two VLANs.

Pre-flight before first launch: 192.168.14.0/24 carries only the host (`.2`) and ND 4.3.1 today, so the sweep is a sanity
check that ND 4.3.1's node data IP (`.14`) and persistent `.30-.32` do not overlap the device plan (they do not: `.1xx`).

### D3. Fabric names, ASNs, pools, VNIs are identical on ND 4.3.1 (confirmed by the user 2026-09-08)

ND 4.3.1 gets fabrics `SITE1`, `SITE2`, `ISN`, fabric group `MSD`, ASNs 65001/65002/65535, the same Resources-tab pools
(`10.1x`/`10.2x`), the same ISN /30s (10.15.0.0/30 and 10.25.0.0/30, inside each site's VRF-Lite pool), the same WAN
Loopback0 (10.35.0.1/32), the same WAN router role (`coreRouter`), and the same
overlay VRF/network/VNI/VLAN. Only the member device hostnames (S3_*/S4_*/WAN2) and their mgmt IPs differ.

Rationale: the fabrics live on separate controllers and separate bridges, so there is no collision; the user's `env_prod`
already keys everything on `ND_FABRIC_SITE1`/`SITE2`/`ISN`/`MSD` with `ND_IP4` selecting the controller, so the
ansible-nd test suite runs unchanged against either ND. Device names must differ only because both testbeds share one host
(unique QEMU names, TAP names, YAML files, container domains).

Alternative (not chosen): name the fabrics `SITE3`/`SITE4` and override `ND_FABRIC_SITE1=SITE3` in the env. It buys
nothing and makes the "mirror" a naming exception.

### D4. Exact link mirror (S1 -> S3, S2 -> S4)

| Bridge (new unless noted) | A side               | B side              | Mirror of         |
|---------------------------|----------------------|---------------------|-------------------|
| BR_ISN_S3_S4_1 (exists)   | S3_BG1 Eth1/1        | S4_BG1 Eth1/1       | BR_ISN_S1_S2_1    |
| BR_S3_BG1_SP1_1 (exists)  | S3_BG1 Eth1/2        | S3_SP1 Eth1/1       | BR_S1_BG1_SP1_1   |
| BR_ISN_WAN_S3_1           | WAN2 Gi2             | S3_BG1 Eth1/3       | BR_ISN_WAN_S1_1   |
| BR_S3_SP1_LE1_1 (exists)  | S3_SP1 Eth1/2        | S3_LE1 Eth1/1       | BR_S1_SP1_LE1_1   |
| BR_S3_SP1_LE2_1           | S3_SP1 Eth1/3        | S3_LE2 Eth1/1       | BR_S1_SP1_LE2_1   |
| BR_S3_SP1_LE3_1           | S3_SP1 Eth1/4        | S3_LE3 Eth1/1       | BR_S1_SP1_LE3_1   |
| BR_S3_SP1_LE4_1           | S3_SP1 Eth1/5        | S3_LE4 Eth1/1       | BR_S1_SP1_LE4_1   |
| BR_S3_LE1_LE2_1           | S3_LE1 Eth1/2        | S3_LE2 Eth1/2       | BR_S1_LE1_LE2_1   |
| BR_S3_LE1_T1_1            | S3_LE1 Eth1/3        | S3_TOR1 Eth1/1      | BR_S1_LE1_T1_1    |
| BR_S3_LE2_T1_1            | S3_LE2 Eth1/3        | S3_TOR1 Eth1/2      | BR_S1_LE2_T1_1    |
| BR_S3_T1_H1_1             | S3_TOR1 Eth1/3       | S3_H1 eth1          | BR_S1_T1_H1_1     |
| BR_S3_LE3_LE4_1           | S3_LE3 Eth1/2        | S3_LE4 Eth1/2       | BR_S1_LE3_LE4_1   |
| BR_S4_BG1_SP1_1 (exists)  | S4_BG1 Eth1/2        | S4_SP1 Eth1/1       | BR_S2_BG1_SP1_1   |
| BR_ISN_WAN_S4_1           | WAN2 Gi3             | S4_BG1 Eth1/3       | BR_ISN_WAN_S2_1   |
| BR_S4_SP1_LE1_1 (exists)  | S4_SP1 Eth1/2        | S4_LE1 Eth1/1       | BR_S2_SP1_LE1_1   |
| BR_S4_LE1_H1_1 (exists)   | S4_LE1 Eth1/2        | S4_H1 eth1          | BR_S2_LE1_H1_1    |

Removed (not in the ND 4.2.1 topology): `BR_S4_SP1_LE2_1`, `BR_S4_SP1_LE3_1`, `BR_S4_LE2_H2_1`, `BR_S4_LE3_H2_1`,
`S4_LE2.yaml`, `S4_LE3.yaml`, `BR_S3_LE1_H1_1` (S3_H1 hangs off the TOR, like S1_H1). Every name is <= 15 chars.

The `isl_bridges` order in each YAML is what fixes `Ethernet1/N`; it is copied position-for-position from the S1/S2 file it
mirrors. Interface numbering on the ND side (links, attachments) is therefore also identical.

### D5. Provisioning is a Python REST tool in this repo, driven by a declarative topology file

`config/nd/provision/` gains a small package (`nd_client.py`, `topology.py`, `snapshot.py`, `provision.py`) plus two data
files, `topology_nd421.yaml` and `topology_nd431.yaml`. The tool is idempotent per phase (`fabrics`, `msd`, `switches`,
`isn`, `overlay`, `deploy`), has `--dry-run`, reads `ND_IP4`/`ND_USERNAME`/`ND_PASSWORD`/`ND_DOMAIN`/`NXOS_PASSWORD`/
`IOSXE_PASSWORD` from the environment, and resolves switch serial numbers at run time by hostname (serials change on every
VM rebuild). `snapshot.py` dumps an ND's fabric state read-only and can diff two dumps while ignoring hostnames, mgmt IPs
and serials, which is the mechanical proof that the two testbeds mirror each other.

Why Python and not `cisco.nd` playbooks: this lab exists to develop those modules, so bringup must not depend on them; the
REST payloads are already captured in `docs/nd4_fabrics_bringup.md` and the `provision-isn` skill; the repo's other tooling
is Python-plus-YAML. The `/api/v1/manage` paths used (`/fabrics`, `/fabrics/{f}/switches`, `switchActions/changeRoles`,
`/links`, `/fabrics/{f}/policies`, `/vrfs`, `/networks`, `vrfAttachments`, `networkAttachments`, `actions/configDeploy`,
`vrfActions/deploy`, `networkActions/deploy`, `switchActions/rediscover`, `inventory/switchActions/showCommands`) exist
unchanged in both the 4.2.1 and 4.3.1 OpenAPI schemas.

The overlay definition (VRF name/ID, network name/ID, VLAN, gateway, attachment ports) is captured from the live ND 4.2.1
with `snapshot.py` and transcribed into `topology_nd421.yaml`; `topology_nd431.yaml` is a copy with only the hostname/IP
substitutions. The 2026-09-08 snapshot of ND 4.2.1 shows NO VRFs, networks or attachments in SITE1/SITE2 (the VLAN-2 /
192.0.1.1 overlay noted in older session memory was not re-created after the 2026-08 rebuild), so both topology files ship
with an empty `overlay:` section; the schema and the `overlay` phase remain so the section can be filled in later.
The snapshot also showed that fabric groups are listed only by `GET /fabrics?category=fabricGroup`, and that the live ISN
links use 10.15.0.1/30 and 10.25.0.1/30 (not the 10.33.0.x of the earlier lab), with WAN1 in role `coreRouter`.

### D6. Scope boundaries

In scope: switch/router/container definitions, bridges, helper scripts, launch scripts, inventory, provisioning tool and
topology files, docs. Also the deployment runbook for the host (netplan, ISOs, launches, provisioning order, verification).

Out of scope (follow-ups, listed in the plan): deleting the stale generated `config/nexus9000v/cfg/` directory (it embeds a
password and is no longer produced by any tool); the stale IPv6 EUI-64 addresses in `S1_H1/S2_H1.netplan.yaml`; updating
`~/lab_recover.sh` on the host (not in the repo) to include site3/site4/WAN2/containers; the `provision-isn` skill (lives in
`~/.claude`, will be pointed at the new tool once it lands).

## Risks

- **Address collisions.** None possible with SITE1/SITE2: the testbeds are on different VLANs. Within 192.168.14.0/24 the
  device plan (`.1xx`) is disjoint from the host (`.2`) and ND 4.3.1 (`.14`, `.30-.32`).
- **ND 4.3.1 re-instantiation.** Its libvirt domain must be destroyed/undefined and disks removed before re-running the
  install script with `ND_DATA_NET=BR_ND_DATA_14`; the CLI bootstrap and the nd-bootstrap YAML (separate repo) must use
  the 192.168.14.x addresses. Until that is done nothing in SITE3/SITE4 can be onboarded.
- **ND 4.3.1 behavioural differences** (e.g. fabric create defaults, monitored-mode default on external fabrics). The tool
  asserts `management.monitoredMode: false` on ISN after create and treats every deploy as "verify `pendingConfig` empty",
  the same guards that were learned on 4.2.1.
- **Host resources.** Eleven more n9kv (16 GB RAM, 4 vCPU each by default) plus one C8000V (8 GB) and two containers add
  ~186 GB RAM and 48 vCPUs. The plan's runbook checks free memory before launching and launches site by site.
- **netplan apply removing bridges with live ports.** The four removed `S4_*` bridges have no ports today, so removal is safe.
