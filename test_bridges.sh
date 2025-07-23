#!/bin/bash

# Modern Bridge Network Diagnostics (using ip commands)

echo "=== MODERN BRIDGE NETWORK DIAGNOSTICS ==="
echo ""

echo "1. Bridge interfaces and their ports:"
echo "------------------------------------"
for bridge in ndfc-mgmt BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Bridge: $bridge"
        echo "  Status: $(ip link show $bridge | head -1)"
        echo "  Ports:"
        bridge link show br $bridge 2>/dev/null | sed 's/^/    /'
        echo "  MAC addresses learned:"
        bridge fdb show br $bridge 2>/dev/null | grep -v permanent | sed 's/^/    /'
        echo ""
    else
        echo "Bridge $bridge does not exist"
    fi
done

echo "2. QEMU TAP/VNET interfaces:"
echo "----------------------------"
ip link show | grep -E "tap|vnet" || echo "No TAP/VNET interfaces found"

echo ""
echo "3. Bridge port assignments:"
echo "---------------------------"
bridge link show 2>/dev/null

echo ""
echo "4. Check QEMU VM network status:"
echo "--------------------------------"
if pgrep -f "qemu.*ER" >/dev/null; then
    echo "QEMU VM is running. Checking network devices..."
    timeout 10 bash -c "
        echo 'info network' | telnet localhost 4444 2>/dev/null
    " | grep -E "(VLAN|net|Bridge|tap|vnet)" || echo "Could not get QEMU network info"
    
    echo ""
    echo "QEMU process network arguments:"
    ps aux | grep qemu | grep -o -- '-netdev [^-]*' | head -5
else
    echo "No QEMU VM running"
fi

echo ""
echo "5. Test bridge connectivity with ip commands:"
echo "---------------------------------------------"

test_bridge_modern() {
    local bridge_name=$1
    local test_ip=$2
    local ns_name="test_${bridge_name}"
    
    echo "Testing bridge: $bridge_name with IP $test_ip"
    
    # Cleanup any existing test setup
    ip netns del $ns_name 2>/dev/null
    ip link del veth_${bridge_name}_0 2>/dev/null
    
    if ip link show $bridge_name >/dev/null 2>&1; then
        # Create veth pair
        ip link add veth_${bridge_name}_0 type veth peer name veth_${bridge_name}_1
        
        # Create namespace and move one end
        ip netns add $ns_name
        ip link set veth_${bridge_name}_1 netns $ns_name
        
        # Add veth to bridge using ip command
        ip link set veth_${bridge_name}_0 master $bridge_name
        ip link set veth_${bridge_name}_0 up
        
        # Configure namespace interface
        ip netns exec $ns_name ip link set veth_${bridge_name}_1 up
        ip netns exec $ns_name ip addr add ${test_ip}/24 dev veth_${bridge_name}_1
        ip netns exec $ns_name ip link set lo up
        
        echo "  ✓ Test interface created: ${test_ip}/24"
        echo "  Bridge $bridge_name now has ports:"
        bridge link show br $bridge_name | sed 's/^/    /'
        
        echo "  To test from N9Kv console (telnet localhost 9020):"
        echo "    ping ${test_ip}"
        echo ""
        echo "  To cleanup this test:"
        echo "    ip netns del $ns_name"
        echo "    ip link del veth_${bridge_name}_0"
        echo ""
    else
        echo "  ✗ Bridge $bridge_name does not exist"
        ip netns del $ns_name 2>/dev/null
    fi
}

# Test the data bridges
test_bridge_modern "BR_ER_S1" "10.1.1.100"
test_bridge_modern "BR_ER_S2" "10.2.2.100"

echo "6. Check N9Kv interface configuration:"
echo "--------------------------------------"
if pgrep -f "qemu.*ER" >/dev/null; then
    echo "Connect to N9Kv: telnet localhost 9020"
    echo ""
    echo "Verify interface configuration:"
    echo "  show interface brief"
    echo "  show ip interface brief"
    echo "  show interface ethernet1/1"
    echo "  show interface ethernet1/2"
    echo ""
    echo "Expected configuration (if NDFC configured correctly):"
    echo "  - Interfaces should be 'no switchport' (routed mode)"
    echo "  - Should have IP addresses assigned"
    echo "  - Should show 'up' status"
else
    echo "VM not running"
fi

echo ""
echo "7. Packet capture commands:"
echo "---------------------------"
echo "Monitor traffic on bridges:"
echo "  tcpdump -i BR_ER_S1 -n icmp"
echo "  tcpdump -i BR_ER_S2 -n icmp"
echo ""
echo "Monitor specific interface in namespace:"
echo "  ip netns exec test_BR_ER_S1 tcpdump -i veth_BR_ER_S1_1 -n"

echo ""
echo "8. Bridge learning and forwarding status:"
echo "----------------------------------------"
for bridge in BR_ER_S1 BR_ER_S2; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Bridge $bridge:"
        echo "  Learning: $(cat /sys/class/net/$bridge/bridge/learning 2>/dev/null || echo 'unknown')"
        echo "  Forwarding: $(cat /sys/class/net/$bridge/bridge/forward_delay 2>/dev/null || echo 'unknown')"
        echo "  STP: $(cat /sys/class/net/$bridge/bridge/stp_state 2>/dev/null || echo 'unknown')"
    fi
done

echo ""
echo "9. QEMU bridge helper check:"
echo "----------------------------"
if [ -f /usr/lib/qemu/qemu-bridge-helper ]; then
    echo "✓ qemu-bridge-helper exists"
    ls -la /usr/lib/qemu/qemu-bridge-helper
    if [ -f /etc/qemu/bridge.conf ]; then
        echo "✓ bridge.conf exists:"
        cat /etc/qemu/bridge.conf
    else
        echo "✗ /etc/qemu/bridge.conf missing"
        echo "  Create with: echo 'allow all' > /etc/qemu/bridge.conf"
    fi
else
    echo "✗ qemu-bridge-helper not found"
    echo "  Install with: apt install qemu-system-common"
fi

echo ""
echo "=== NEXT STEPS ==="
echo "1. Run the test bridge setup above"
echo "2. From N9Kv console, try: ping 10.1.1.100"
echo "3. Run tcpdump to see if packets are flowing"
echo "4. Check QEMU network device type (virtio vs e1000)"
