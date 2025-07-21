#!/bin/bash

# Create TAP interfaces
ip tuntap add dev tap_ER_MGMT mode tap
ip tuntap add dev tap_S1_MGMT mode tap
ip tuntap add dev tap_S2_MGMT mode tap
ip tuntap add dev tap_L1_MGMT mode tap

ip tuntap add dev tap_ER_E1_1 mode tap
ip tuntap add dev tap_ER_E1_2 mode tap

ip tuntap add dev tap_S1_E1_1 mode tap
ip tuntap add dev tap_S1_E1_2 mode tap

ip tuntap add dev tap_S2_E1_1 mode tap
ip tuntap add dev tap_S2_E1_2 mode tap

ip tuntap add dev tap_L1_E1_1 mode tap
ip tuntap add dev tap_L1_E1_2 mode tap

# Create bridges (inter-switch links)
ip link add name BR_ER_S1 type bridge stp_state 0
ip link add name BR_ER_S2 type bridge stp_state 0

ip link add name BR_S1_L1 type bridge stp_state 0
ip link add name BR_S2_L1 type bridge stp_state 0

# Add TAP interfaces to existing ndfc-mgmt bridge
ip link set tap_ER_MGMT master ndfc-mgmt
ip link set tap_S1_MGMT master ndfc-mgmt
ip link set tap_S2_MGMT master ndfc-mgmt
ip link set tap_L1_MGMT master ndfc-mgmt


# Connect n9kv interfaces to bridges
# ER-->S1
ip link set tap_ER_E1_1 master BR_ER_S1
# ER-->S2
ip link set tap_ER_E1_2 master BR_ER_S2
# S1-->ER
ip link set tap_S1_E1_1 master BR_ER_S1
# S2-->ER
ip link set tap_S2_E1_1 master BR_ER_S2

# S1-->L1
ip link set tap_S1_E1_2 master BR_S1_L1
# S2-->L1
ip link set tap_S2_E1_2 master BR_S2_L1
# L1-->S1
ip link set tap_L1_E1_1 master BR_S1_L1
# L1-->S2
ip link set tap_L1_E1_2 master BR_S2_L1

# Bring up all bridges
ip link set BR_ER_S1 up
ip link set BR_ER_S2 up

ip link set BR_S1_L1 up
ip link set BR_S2_L1 up

# Bring up all TAP interfaces
ip link set tap_ER_MGMT up
ip link set tap_S1_MGMT up
ip link set tap_S2_MGMT up
ip link set tap_L1_MGMT up

ip link set tap_ER_E1_1 up
ip link set tap_ER_E1_2 up
ip link set tap_S1_E1_1 up
ip link set tap_S1_E1_2 up
ip link set tap_S2_E1_1 up
ip link set tap_S2_E1_2 up

ip link set tap_L1_E1_1 up
ip link set tap_L1_E1_2 up

echo "All network interfaces created and brought up successfully using modern ip commands"


# You can also disable spanning-tree after the fact

# ip link set dev BR_ER_S1 type bridge stp_state 0
# ip link set dev BR_ER_S2 type bridge stp_state 0
# ip link set dev BR_S1_L1 type bridge stp_state 0
# ip link set dev BR_S2_L1 type bridge stp_state 0
