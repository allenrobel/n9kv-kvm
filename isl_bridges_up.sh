#!/bin/bash

# Create bridges (inter-switch links)
ip link add name BR_ER_S1 type bridge stp_state 0
ip link add name BR_ER_S2 type bridge stp_state 0

ip link add name BR_S1_L1 type bridge stp_state 0
ip link add name BR_S2_L1 type bridge stp_state 0

# Set bridge interfaces MTU 9216
for bridge in BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Setting $bridge MTU 9216..."
        ip link set $bridge mtu 9216
    fi
done

# Set tap interfaces MTU 9216
for tap in $(bridge link show | grep -E "(BR_ER_S1|BR_ER_S2|BR_S1_L1|BR_S2_L1)" | grep tap | cut -d: -f2 | cut -d' ' -f2); do
    if ip link show $tap >/dev/null 2>&1; then
        echo "Setting $tap MTU 9216..."
        ip link set $tap mtu 9216
    fi
done

# Set bridge interfaces arp on
for bridge in BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Setting $bridge arp on..."
        ip link set dev $bridge arp on
    fi
done

# Set TAP interfaces arp on
for tap in $(bridge link show | grep -E "(BR_ER_S1|BR_ER_S2|BR_S1_L1|BR_S2_L1)" | grep tap | cut -d: -f2 | cut -d' ' -f2); do
    if ip link show $tap >/dev/null 2>&1; then
        echo "Setting $tap arp on..."
        ip link set dev $tap arp on
    fi
done

# Set bridge interfaces promiscuous mode on
for bridge in BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Setting $bridge promisc on..."
        ip link set dev $bridge promisc on
    fi
done

# Set TAP interfaces promiscuous mode on
for tap in $(bridge link show | grep -E "(BR_ER_S1|BR_ER_S2|BR_S1_L1|BR_S2_L1)" | grep tap | cut -d: -f2 | cut -d' ' -f2); do
    if ip link show $tap >/dev/null 2>&1; then
        echo "Setting $tap promisc on..."
        ip link set dev $tap promisc on
    fi
done

# Set bridge interfaces multicast on
for bridge in BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Setting $bridge multicast on..."
        ip link set dev $bridge multicast on
    fi
done

# Set TAP interfaces promiscuous mode on
for tap in $(bridge link show | grep -E "(BR_ER_S1|BR_ER_S2|BR_S1_L1|BR_S2_L1)" | grep tap | cut -d: -f2 | cut -d' ' -f2); do
    if ip link show $tap >/dev/null 2>&1; then
        echo "Setting $tap multicast on..."
        ip link set dev $tap multicast on
    fi
done


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
