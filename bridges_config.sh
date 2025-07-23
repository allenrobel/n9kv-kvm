#!/bin/bash

BRIDGES=(BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1)

for bridge in "${BRIDGES[@]}"; do
    if ! ip link show $bridge >/dev/null 2>&1; then
        echo "Bridge $bridge does not exist. Creating..."
        ip link add name $bridge type bridge
        ip link set $bridge mtu 9216
        ip link set dev $bridge arp on
        ip link set dev $bridge promisc on
        ip link set dev $bridge multicast on
        ip link set dev $bridge type bridge stp_state 0
        ip link set $bridge up
    else
        echo "Bridge $bridge already exists."
    fi
done

# Join bridges with "|" to create a single string for grep below
SAVED_IFS="$IFS"  # Save the original IFS
IFS="|"
JOINED_BRIDGES="${BRIDGES[*]}"
IFS="$SAVED_IFS"
TAPS=$(bridge link show | grep -E "${JOINED_BRIDGES}" | grep tap | cut -d: -f2 | cut -d' ' -f2)

for tap in $TAPS; do
    echo "Configuring TAP interface $tap..."
    ip link set $tap mtu 9216
    ip link set dev $tap arp on
    ip link set dev $tap promisc on
    ip link set dev $tap multicast on
    ip link set $tap up
done