#!/bin/bash

# Bring down all TAP interfaces
ip link set tap_ER_E1_1 down
ip link set tap_ER_E1_2 down
ip link set tap_S1_E1_1 down
ip link set tap_S1_E1_2 down
ip link set tap_S2_E1_1 down
ip link set tap_S2_E1_2 down
ip link set tap_L1_E1_1 down
ip link set tap_L1_E1_2 down

ip link set tap_ER_MGMT down
ip link set tap_S1_MGMT down
ip link set tap_S2_MGMT down
ip link set tap_L1_MGMT down

# Remove TAP interfaces from bridges
# ER connections
ip link set tap_ER_E1_1 nomaster
ip link set tap_ER_E1_2 nomaster
ip link set tap_S1_E1_1 nomaster
ip link set tap_S2_E1_1 nomaster

# Spine-Leaf connections
ip link set tap_S1_E1_2 nomaster
ip link set tap_S2_E1_2 nomaster
ip link set tap_L1_E1_1 nomaster
ip link set tap_L1_E1_2 nomaster

# Remove management interfaces from BR_ND_DATA bridge
ip link set tap_ER_MGMT nomaster
ip link set tap_S1_MGMT nomaster
ip link set tap_S2_MGMT nomaster
ip link set tap_L1_MGMT nomaster

# Bring down all bridges
ip link set BR_ER_S1 down
ip link set BR_ER_S2 down
ip link set BR_S1_L1 down
ip link set BR_S2_L1 down
ip link set BR_L1_H1 down
ip link set BR_L2_H2 down

# Delete all bridges
ip link delete BR_ER_S1
ip link delete BR_ER_S2
ip link delete BR_S1_L1
ip link delete BR_S2_L1
ip link delete BR_L1_H1
ip link delete BR_L2_H2

# Delete all TAP interfaces
ip link delete tap_ER_MGMT
ip link delete tap_S1_MGMT
ip link delete tap_S2_MGMT
ip link delete tap_L1_MGMT

ip link delete tap_ER_E1_1
ip link delete tap_ER_E1_2
ip link delete tap_S1_E1_1
ip link delete tap_S1_E1_2
ip link delete tap_S2_E1_1
ip link delete tap_S2_E1_2
ip link delete tap_L1_E1_1
ip link delete tap_L1_E1_2

echo "All network interfaces torn down successfully"
