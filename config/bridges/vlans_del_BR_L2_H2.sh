# Remove vlans 2 and 3 from BR_L2_H2 and associated interfaces
VLANS=(2 3)
BRIDGE="BR_L2_H2"
TAPS=$(bridge link show | grep -E $BRIDGE | grep tap | cut -d: -f2 | cut -d' ' -f2)
VNETS=$(bridge link show | grep -E $BRIDGE | grep vnet | cut -d: -f2 | cut -d' ' -f2 | cut -d'@' -f1)

# Exit if bridge does not exist
if ! ip link show $BRIDGE >/dev/null 2>&1; then
    echo "Bridge $BRIDGE does not exist. Exiting..."
    exit 1
fi

# Remove vlans from bridge
for vlan in "${VLANS[@]}"; do
    echo "Removing VLAN $vlan from $BRIDGE..."
    echo "sudo bridge vlan del vid $vlan dev $BRIDGE self"
    sudo bridge vlan del vid $vlan dev $BRIDGE self
done

# Remove vlans from associated TAP interfaces
for tap in $TAPS; do
    for vlan in "${VLANS[@]}"; do
        echo "Removing VLAN $vlan from $tap..."
        echo "sudo bridge vlan del vid $vlan dev $tap"
        sudo bridge vlan del vid $vlan dev $tap
    done
done

# Remove vlans from associated VNET interfaces
for vnet in $VNETS; do
    for vlan in "${VLANS[@]}"; do
        echo "Removing VLAN $vlan from $vnet..."
        echo "sudo bridge vlan del vid $vlan dev $vnet"
        sudo bridge vlan del vid $vlan dev $vnet
    done
done
