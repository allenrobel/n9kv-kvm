#!/bin/bash

# This script sets up the necessary bridges and TAP interfaces for the Nexus Dashboard environment.
# If you created the bridges with netplan (see 99-bridges.yaml), you still need to run this
# this script to ensure the TAP interfaces that are dynamically created for the nexus9000v
# are configured correctly.

# This script should be run with root privileges.
# Usage: sudo ./bridges_config.sh

BRIDGES=(BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1 BR_ND_MGMT BR_ND_DATA)

for bridge in "${BRIDGES[@]}"; do
    if ! ip link show $bridge >/dev/null 2>&1; then
        echo "Bridge $bridge does not exist. Creating..."
        ip link add name $bridge type bridge
    else
        echo "Bridge $bridge already exists."
    fi
done

for bridge in "${BRIDGES[@]}"; do
    echo "Configuring bridge $bridge..."
    ip link set dev $bridge mtu 9216
    ip link set dev $bridge arp on
    ip link set dev $bridge promisc off
    ip link set dev $bridge multicast on
    echo "Bringing up bridge $bridge..."
    ip link set $bridge up
done

# Join BRIDGES with "|" to create a single string for grep below
SAVED_IFS="$IFS"  # Save the original IFS
IFS="|"
JOINED_BRIDGES="${BRIDGES[*]}"
IFS="$SAVED_IFS"
TAPS=$(bridge link show | grep -E "${JOINED_BRIDGES}" | grep tap | cut -d: -f2 | cut -d' ' -f2)

for tap in $TAPS; do
    echo "Configuring TAP interface $tap..."
    ip link set $tap mtu 9216
    ip link set dev $tap arp on
    ip link set dev $tap promisc off
    ip link set dev $tap multicast on
    echo "Bringing up TAP interface $tap..."
    ip link set $tap up
done