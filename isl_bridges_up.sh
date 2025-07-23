#!/bin/bash

# Create bridges (inter-switch links)
ip link add name BR_ER_S1 type bridge stp_state 0
ip link add name BR_ER_S2 type bridge stp_state 0

ip link add name BR_S1_L1 type bridge stp_state 0
ip link add name BR_S2_L1 type bridge stp_state 0

# Set MTU for bridges for routing protocols
ip link set dev BR_ER_S1 mtu 9216
ip link set dev BR_ER_S2 mtu 9216
ip link set dev BR_S1_L1 mtu 9216
ip link set dev BR_S2_L1 mtu 9216

# Set MTU for bridges for routing protocols
ip link set dev BR_ER_S1 arp on
ip link set dev BR_ER_S2 arp on
ip link set dev BR_S1_L1 arp on
ip link set dev BR_S2_L1 arp on

# Set MTU for bridges for routing protocols
ip link set dev BR_ER_S1 multicast on
ip link set dev BR_ER_S2 multicast on
ip link set dev BR_S1_L1 multicast on
ip link set dev BR_S2_L1 multicast on

# Bring up all bridges
ip link set BR_ER_S1 up
ip link set BR_ER_S2 up
ip link set BR_S1_L1 up
ip link set BR_S2_L1 up

echo "All ISL bridges brought up successfully"

# You can also disable spanning-tree after the fact

# ip link set dev BR_ER_S1 type bridge stp_state 0
# ip link set dev BR_ER_S2 type bridge stp_state 0
# ip link set dev BR_S1_L1 type bridge stp_state 0
# ip link set dev BR_S2_L1 type bridge stp_state 0
