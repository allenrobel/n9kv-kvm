#!/bin/bash

# Create bridges (inter-switch links)
ip link add name BR_ER_S1 type bridge stp_state 0
ip link add name BR_ER_S2 type bridge stp_state 0

ip link add name BR_S1_L1 type bridge stp_state 0
ip link add name BR_S2_L1 type bridge stp_state 0

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
