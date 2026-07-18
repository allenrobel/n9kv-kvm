# Manual VPC bringup for the SITE1 pair (S1_LE1 + S1_LE2) and S1_TOR1

This runbook brings up the SITE1 VPC pair and its dual-homed TOR **manually,
outside of Nexus Dashboard**. It's intended as a reference / regression
target for the in-development VPC pairing Ansible modules: with this config
applied by hand, you have a known-good data plane that the modules can
later reproduce (or diverge from) for comparison.

ND is intentionally not in the picture here — the configuration is typed
straight into each switch's NX-OS CLI over the console or SSH.

## Prerequisites

- S1_LE1, S1_LE2, S1_TOR1 are running and have completed first-boot
  POAP from their startup-config ISOs.
- Each switch's admin password has been set (the bootstrap config
  intentionally omits the password — set it on first console login).
- The four SITE1 data bridges exist on the lab host and are MTU 9216
  (created by netplan from `config/bridges/netplan/9912-bridges.yaml` and
  configured by `config/bridges/bridges_config_ovs.sh`):
  - `BR_S1_LE1_LE2_1` (peer-link)
  - `BR_S1_LE1_T1_1`  (S1_LE1 → S1_TOR1)
  - `BR_S1_LE2_T1_1`  (S1_LE2 → S1_TOR1)

## Topology

```text
                              S1_SP1
                             /       \
                            /         \
        S1_LE1 (Eth1/1) ---       --- (Eth1/1) S1_LE2
        S1_LE1 (Eth1/3) === peer-link === (Eth1/2) S1_LE2
        S1_LE1 (Eth1/4) ---\         /--- (Eth1/3) S1_LE2
                            \       /
                          S1_TOR1 (Eth1/1, Eth1/2)
```

| Switch   | Mgmt IP          | Interface | Faces                       | Bridge               |
|----------|------------------|-----------|-----------------------------|----------------------|
| S1_LE1   | 192.168.12.151   | Eth1/1    | S1_SP1                      | BR_S1_SP1_LE1_1      |
|          |                  | Eth1/2    | S1_H1 (host)                | BR_S1_LE1_H1_1       |
|          |                  | Eth1/3    | S1_LE2 (peer-link)          | BR_S1_LE1_LE2_1      |
|          |                  | Eth1/4    | S1_TOR1                     | BR_S1_LE1_T1_1       |
| S1_LE2   | 192.168.12.155   | Eth1/1    | S1_SP1                      | BR_S1_SP1_LE2_1      |
|          |                  | Eth1/2    | S1_LE1 (peer-link)          | BR_S1_LE1_LE2_1      |
|          |                  | Eth1/3    | S1_TOR1                     | BR_S1_LE2_T1_1       |
| S1_TOR1  | 192.168.12.161   | Eth1/1    | S1_LE1                      | BR_S1_LE1_T1_1       |
|          |                  | Eth1/2    | S1_LE2                      | BR_S1_LE2_T1_1       |

## Design choices

- **VPC domain ID** `1` — single pair in SITE1 today.
- **Roles**: S1_LE1 is primary (`role priority 100`), S1_LE2 is secondary
  (`role priority 200`). Lower wins; tie-breaker is system MAC.
- **Peer-link channel**: `port-channel 1`.
- **Peer-keepalive**: over `mgmt0` in the `management` VRF, targeting the
  other leaf's mgmt IP. Both leaves are reachable via `BR_ND_DATA_12`
  on `192.168.12.0/24`, so no dedicated keepalive link is needed.
- **TOR-facing channel**: `port-channel 10` on all three switches. Same
  channel-group number on each leaf so the `vpc 10` association is
  symmetric. TOR1 uses the same number, but it sees the pair as one
  ordinary LACP partner — TOR1 doesn't know VPC exists.
- **LACP** mode `active` on both sides of every channel.
- **Trunk VLANs**: `2-3` on the peer-link and TOR-facing channel.
  These VLANs carry the host container's test traffic. Easy to widen.
- **VPC best practices**: `peer-switch`, `peer-gateway`, `delay restore
  150`, `auto-recovery`, `ip arp synchronize`, `ipv6 nd synchronize`,
  and `spanning-tree port type network` on the peer-link.

## Apply order

The keepalive must reach the peer before the peer-link comes up;
otherwise the peer-link can land in suspended/split-brain state. To
avoid this, either:

- Configure both leaves through `vpc domain 1` (incl. `peer-keepalive`)
  before applying either leaf's peer-link block; or
- Fully configure S1_LE2 first, *then* S1_LE1.

## S1_LE1 (VPC primary, 192.168.12.151)

Reach the CLI via `con_s1_le1` (telnet to 9051) or `ssh_s1_le1`.

```text
configure terminal

! Features
feature lacp
feature vpc
feature lldp

! VLANs for test traffic (tagged by the host container)
vlan 2-3

! VPC domain
vpc domain 1
  role priority 100
  peer-switch
  peer-gateway
  peer-keepalive destination 192.168.12.155 source 192.168.12.151 vrf management
  delay restore 150
  auto-recovery
  ip arp synchronize
  ipv6 nd synchronize

! Peer-link: Eth1/3 -> S1_LE2 Eth1/2
interface Ethernet1/3
  description S1_LE2 peer-link
  switchport
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  channel-group 1 mode active
  no shutdown

interface port-channel1
  description vpc peer-link to S1_LE2
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  spanning-tree port type network
  vpc peer-link

! VPC member port-channel to S1_TOR1: Eth1/4
interface Ethernet1/4
  description S1_TOR1 vpc member
  switchport
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  channel-group 10 mode active
  no shutdown

interface port-channel10
  description vpc 10 to S1_TOR1
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  spanning-tree port type edge trunk
  vpc 10

end
copy running-config startup-config
```

## S1_LE2 (VPC secondary, 192.168.12.155)

Reach the CLI via `con_s1_le2` (telnet to 9055) or `ssh_s1_le2`.

```text
configure terminal

feature lacp
feature vpc
feature lldp

vlan 2-3

vpc domain 1
  role priority 200
  peer-switch
  peer-gateway
  peer-keepalive destination 192.168.12.151 source 192.168.12.155 vrf management
  delay restore 150
  auto-recovery
  ip arp synchronize
  ipv6 nd synchronize

! Peer-link: Eth1/2 -> S1_LE1 Eth1/3
interface Ethernet1/2
  description S1_LE1 peer-link
  switchport
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  channel-group 1 mode active
  no shutdown

interface port-channel1
  description vpc peer-link to S1_LE1
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  spanning-tree port type network
  vpc peer-link

! VPC member port-channel to S1_TOR1: Eth1/3
interface Ethernet1/3
  description S1_TOR1 vpc member
  switchport
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  channel-group 10 mode active
  no shutdown

interface port-channel10
  description vpc 10 to S1_TOR1
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  spanning-tree port type edge trunk
  vpc 10

end
copy running-config startup-config
```

## S1_TOR1 (no VPC awareness, 192.168.12.161)

Reach the CLI via `con_s1_tor1` (telnet to 9061) or `ssh_s1_tor1`.

```text
configure terminal

feature lacp
feature lldp

vlan 2-3

! Single LACP bundle facing the VPC pair (TOR sees them as one logical switch)
interface Ethernet1/1
  description S1_LE1 uplink
  switchport
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  channel-group 10 mode active
  no shutdown

interface Ethernet1/2
  description S1_LE2 uplink
  switchport
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  channel-group 10 mode active
  no shutdown

interface port-channel10
  description Uplink to S1_LE1/S1_LE2 (VPC pair, but TOR doesn't know that)
  switchport mode trunk
  switchport trunk allowed vlan 2-3
  spanning-tree port type edge trunk

end
copy running-config startup-config
```

## Verification

Run in sequence; each step should pass before the next.

### 1. Peer-keepalive reachability

Before the peer-link comes up, the leaves must be able to ping each
other in the management VRF. On S1_LE1:

```text
ping 192.168.12.155 vrf management count 3
```

And the symmetric ping on S1_LE2. Both must succeed.

### 2. VPC peer status

On either leaf:

```text
show vpc
```

Expect:

- `Peer status`: `peer adjacency formed ok`
- `vPC keep-alive status`: `peer is alive`
- `Configuration consistency status`: `success`
- `vPC role`: `primary` on S1_LE1, `secondary` on S1_LE2
- `vPC 10`: `Status: up`, local interface `port-channel10`

### 3. Port-channel formation

On all three switches:

```text
show port-channel summary
```

Expect:

- **S1_LE1**: `Po1(SU)` with `Eth1/3(P)`, `Po10(SU)` with `Eth1/4(P)`
- **S1_LE2**: `Po1(SU)` with `Eth1/2(P)`, `Po10(SU)` with `Eth1/3(P)`
- **S1_TOR1**: `Po10(SU)` with `Eth1/1(P)` and `Eth1/2(P)`

`SU` = L2 up, `P` = bundled. If TOR1's members show `I` (individual),
LACP isn't completing — usually a channel-group number mismatch or
inconsistent VLAN allowed-list between the leaves.

### 4. LACP / LLDP adjacency

On S1_TOR1:

```text
show lacp neighbor
show lldp neighbors
```

TOR1's `Po10` members should both see the **same LACP system-id** —
that's the VPC pair presenting a unified LACP identity via
`peer-switch`. Two different system-ids means `peer-switch` isn't
working, typically because the VLAN allowed-lists differ across
the pair.

### 5. End-to-end trunk (optional)

For an actual L3 reachability test, give TOR1 an SVI in VLAN 2 and
ping from somewhere on `S1_H1` or one of the leaves:

```text
configure terminal
interface vlan 2
  ip address 11.1.2.10/24
  no shutdown
end
```

The channel coming up `SU/P` in step 3 already proves the L2 path;
this step just sanity-checks the data plane.

## Out of scope

- ND fabric registration of S1_TOR1 — deliberately skipped.
- An Ansible playbook wrapper. If/when desired, a `cisco.nxos.nxos_config`
  playbook targeting `network_cli` could push these same blocks
  without going through ND.
- SVI / host-side traffic tests beyond the optional step 5.
