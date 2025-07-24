#!/bin/bash

# Fix Topology Connectivity Issues

echo "=== TOPOLOGY CONNECTIVITY FIX ==="
echo ""
echo "Expected topology:"
echo "ER.Eth1/1.10.33.0.6 --- BR_ER_S1 --- 10.33.0.5.Eth1/1.S1"
echo "ER.Eth1/2.10.33.0.10 --- BR_ER_S2 --- 10.33.0.9.Eth1/1.S2"
echo ""

echo "1. Fix MTU mismatch:"
echo "-------------------"

# Set all bridges to MTU 9216 to match N9Kv interface configuration
for bridge in BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Setting $bridge MTU to 9216..."
        ip link set $bridge mtu 9216
    fi
done

# Set TAP interfaces to MTU 9216 to match
for tap in $(bridge link show | grep -E "(BR_ER_S1|BR_ER_S2)" | grep tap | cut -d: -f2 | cut -d' ' -f1); do
    if ip link show $tap >/dev/null 2>&1; then
        echo "Setting $tap MTU to 9216..."
        ip link set $tap mtu 9216
    fi
done

echo ""
echo "2. Verify MTU settings:"
echo "----------------------"
echo "Bridges:"
for bridge in BR_ER_S1 BR_ER_S2; do
    if ip link show $bridge >/dev/null 2>&1; then
        mtu=$(ip link show $bridge | grep -o 'mtu [0-9]*' | cut -d' ' -f2)
        echo "  $bridge: $mtu"
    fi
done

echo ""
echo "TAP interfaces on data bridges:"
for tap in $(bridge link show | grep -E "(BR_ER_S1|BR_ER_S2)" | grep tap | cut -d: -f2 | cut -d' ' -f1); do
    if ip link show $tap >/dev/null 2>&1; then
        mtu=$(ip link show $tap | grep -o 'mtu [0-9]*' | cut -d' ' -f2)
        bridge=$(bridge link show dev $tap | grep -o 'master [^ ]*' | cut -d' ' -f2)
        echo "  $tap (master: $bridge): $mtu"
    fi
done

echo ""
echo "3. Create test neighbors to simulate S1 and S2:"
echo "-----------------------------------------------"

# Function to create simulated neighbor
create_neighbor() {
    local bridge=$1
    local neighbor_ip=$2
    local neighbor_name=$3
    local ns_name="sim_${neighbor_name}"
    
    echo "Creating simulated $neighbor_name at $neighbor_ip on $bridge..."
    
    # Cleanup any existing
    ip netns del $ns_name 2>/dev/null
    ip link del veth_${neighbor_name}_0 2>/dev/null
    
    # Create veth pair
    ip link add veth_${neighbor_name}_0 type veth peer name veth_${neighbor_name}_1
    
    # Create namespace and move one end
    ip netns add $ns_name
    ip link set veth_${neighbor_name}_1 netns $ns_name
    
    # Add to bridge with correct MTU
    ip link set veth_${neighbor_name}_0 master $bridge
    ip link set veth_${neighbor_name}_0 mtu 9216 up
    
    # Configure in namespace
    ip netns exec $ns_name ip link set veth_${neighbor_name}_1 mtu 9216 up
    ip netns exec $ns_name ip addr add ${neighbor_ip}/30 dev veth_${neighbor_name}_1
    ip netns exec $ns_name ip link set lo up
    
    echo "  ✓ $neighbor_name created: $neighbor_ip/30"
    
    # Enable ICMP responses
    ip netns exec $ns_name sysctl -w net.ipv4.icmp_echo_ignore_all=0 >/dev/null 2>&1
    
    echo "  Cleanup command: ip netns del $ns_name; ip link del veth_${neighbor_name}_0"
}

# Create simulated S1 and S2
create_neighbor "BR_ER_S1" "10.33.0.5" "S1"
create_neighbor "BR_ER_S2" "10.33.0.9" "S2"

echo ""
echo "4. Test connectivity from ER:"
echo "-----------------------------"
if pgrep -f "qemu.*ER" >/dev/null; then
    echo "ER (N9Kv) is running. Test connectivity:"
    echo ""
    echo "Connect to ER console: telnet localhost 9020"
    echo ""
    echo "Test commands:"
    echo "  ping 10.33.0.5    # Should reach simulated S1"
    echo "  ping 10.33.0.9    # Should reach simulated S2"
    echo ""
    echo "Check interface status:"
    echo "  show ip interface brief"
    echo "  show interface ethernet1/1"
    echo "  show interface ethernet1/2"
    echo ""
    echo "Check routing:"
    echo "  show ip route"
    echo "  show arp"
else
    echo "ER VM is not running"
fi

echo ""
echo "5. Packet capture for troubleshooting:"
echo "--------------------------------------"
echo "Monitor traffic (run in separate terminals):"
echo "  tcpdump -i BR_ER_S1 -n host 10.33.0.5 or host 10.33.0.6"
echo "  tcpdump -i BR_ER_S2 -n host 10.33.0.9 or host 10.33.0.10"
echo ""
echo "Monitor from neighbor perspective:"
echo "  ip netns exec sim_S1 tcpdump -i veth_S1_1 -n"
echo "  ip netns exec sim_S2 tcpdump -i veth_S2_1 -n"

echo ""
echo "6. Start real S1 and S2 VMs:"
echo "----------------------------"
echo "Once connectivity works with simulated neighbors, start your real S1 and S2 VMs:"
echo ""
echo "Make sure S1 and S2 are configured with:"
echo "  S1 Eth1/1: ip address 10.33.0.5/30"
echo "  S2 Eth1/1: ip address 10.33.0.9/30"  
echo "  MTU 9216 on both interfaces"
echo ""
echo "Then remove the simulated neighbors:"
echo "  ip netns del sim_S1"
echo "  ip netns del sim_S2"
echo "  ip link del veth_S1_0"
echo "  ip link del veth_S2_0"

echo ""
echo "7. Check bridge learning:"
echo "------------------------"
echo "After ping tests, check bridge MAC learning:"
for bridge in BR_ER_S1 BR_ER_S2; do
    echo "$bridge learned MACs:"
    bridge fdb show br $bridge | grep -v permanent
done

echo ""
echo "=== SUMMARY ==="
echo "✓ MTU set to 9216 on all bridges and TAP interfaces"
echo "✓ Simulated S1 (10.33.0.5) and S2 (10.33.0.9) created"
echo "✓ Ready to test ping from ER console"
echo ""
echo "Next: Connect to ER and test ping 10.33.0.5 and ping 10.33.0.9"