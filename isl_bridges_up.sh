#!/bin/bash

# Create bridges (inter-switch links)
ip link add name BR_ER_S1 type bridge stp_state 0
ip link add name BR_ER_S2 type bridge stp_state 0

ip link add name BR_S1_L1 type bridge stp_state 0
ip link add name BR_S2_L1 type bridge stp_state 0

# Set all bridges to MTU 9216 to match N9Kv interface configuration
for bridge in BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Setting $bridge MTU to 9216..."
        ip link set $bridge mtu 9216
    fi
done

# Set TAP interfaces to MTU 9216 to match
for tap in $(bridge link show | grep -E "(BR_ER_S1|BR_ER_S2|BR_S1_L1|BR_S2_L1)" | grep tap | cut -d: -f2 | cut -d' ' -f2); do
    if ip link show $tap >/dev/null 2>&1; then
        echo "Setting $tap MTU to 9216..."
        ip link set $tap mtu 9216
    fi
done

# Set ARP on bridges for better performance
ip link set dev BR_ER_S1 arp on
ip link set dev BR_ER_S2 arp on
ip link set dev BR_S1_L1 arp on
ip link set dev BR_S2_L1 arp on

# Set promiscuous mode on bridges to off
ip link set dev BR_ER_S1 promisc off
ip link set dev BR_ER_S2 promisc off
ip link set dev BR_S1_L1 promisc off
ip link set dev BR_S2_L1 promisc off

# Set multicast on bridges to allow multicast traffic
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
