# Add vlans 2 and 3 to BR_L1_H1 and associated interfaces
VLANS=(2 3)
BRIDGE="BR_L1_H1"
TAPS=$(bridge link show | grep -E $BRIDGE | grep tap | cut -d: -f2 | cut -d' ' -f2)
VNETS=$(bridge link show | grep -E $BRIDGE | grep vnet | cut -d: -f2 | cut -d' ' -f2 | cut -d'@' -f1)

# Exit if bridge does not exist
if ! ip link show $BRIDGE >/dev/null 2>&1; then
    echo "Bridge $BRIDGE does not exist. Exiting..."
    exit 1
fi

# Add vlans to bridge
for vlan in "${VLANS[@]}"; do
    echo "Adding VLAN $vlan to $BRIDGE..."
    sudo bridge vlan add vid $vlan dev $BRIDGE
done

# Add vlans to associated TAP interfaces
for tap in $TAPS; do
    for vlan in "${VLANS[@]}"; do
        echo "Adding VLAN $vlan to $tap..."
        sudo bridge vlan add vid $vlan dev $tap
    done
done

# Add vlans to associated VNET interfaces
for vnet in $VNETS; do
    for vlan in "${VLANS[@]}"; do
        echo "Adding VLAN $vlan to $vnet..."
        sudo bridge vlan add vid $vlan dev $vnet
    done
done
