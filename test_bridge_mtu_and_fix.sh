#!/bin/bash

# MTU Fix and Connectivity Test

echo "=== MTU FIX AND CONNECTIVITY TEST ==="
echo ""

echo "1. Current MTU settings:"
echo "------------------------"
echo "Bridges:"
for bridge in BR_ER_S1 BR_ER_S2; do
    if ip link show $bridge >/dev/null 2>&1; then
        mtu=$(ip link show $bridge | grep -o 'mtu [0-9]*' | cut -d' ' -f2)
        echo "  $bridge: $mtu"
    fi
done

echo ""
echo "TAP interfaces:"
for tap in tap1 tap2 tap4 tap7; do
    if ip link show $tap >/dev/null 2>&1; then
        mtu=$(ip link show $tap | grep -o 'mtu [0-9]*' | cut -d' ' -f2)
        bridge=$(bridge link show dev $tap | grep -o 'master [^ ]*' | cut -d' ' -f2)
        echo "  $tap (master: $bridge): $mtu"
    fi
done

echo ""
echo "2. Fix MTU mismatch:"
echo "-------------------"

# Set bridge MTUs to 1500 to match TAP interfaces
for bridge in BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1; do
    if ip link show $bridge >/dev/null 2>&1; then
        echo "Setting $bridge MTU to 1500..."
        ip link set $bridge mtu 1500
    fi
done

echo ""
echo "3. Test bridge connectivity:"
echo "-----------------------------"

# Function to test ping from N9Kv to test interfaces
test_n9kv_connectivity() {
    echo "Testing N9Kv connectivity to test interfaces..."
    echo ""
    echo "Connect to N9Kv console: telnet localhost 9020"
    echo ""
    echo "Then try these ping tests:"
    echo "  ping 10.1.1.100   # Should reach BR_ER_S1 test interface"
    echo "  ping 10.2.2.100   # Should reach BR_ER_S2 test interface"
    echo ""
    
    # Start packet capture in background
    echo "Starting packet capture (will run for 60 seconds)..."
    timeout 60 tcpdump -i BR_ER_S1 -n icmp > /tmp/br_er_s1_capture.log 2>&1 &
    TCPDUMP_PID1=$!
    timeout 60 tcpdump -i BR_ER_S2 -n icmp > /tmp/br_er_s2_capture.log 2>&1 &
    TCPDUMP_PID2=$!
    
    echo "Packet capture started (PIDs: $TCPDUMP_PID1, $TCPDUMP_PID2)"
    echo ""
    echo "Now test ping from N9Kv, then check results below..."
    echo ""
}

test_n9kv_connectivity

echo "4. Check N9Kv interface status:"
echo "-------------------------------"
if pgrep -f "qemu.*ER" >/dev/null; then
    echo "N9Kv is running. Connect and check:"
    echo ""
    echo "telnet localhost 9020"
    echo ""
    echo "On N9Kv, run:"
    echo "  show ip interface brief"
    echo "  show interface ethernet1/1"
    echo "  show interface ethernet1/2"
    echo ""
    echo "Look for:"
    echo "  - Interfaces in 'up' state"
    echo "  - IP addresses assigned"
    echo "  - 'routed' mode (not switchport)"
else
    echo "N9Kv VM is not running"
fi

echo ""
echo "5. Manual connectivity test:"
echo "----------------------------"

# Wait a bit for user to test
echo "Waiting 30 seconds for manual ping tests..."
sleep 30

echo ""
echo "6. Check packet capture results:"
echo "--------------------------------"

if [ -f /tmp/br_er_s1_capture.log ]; then
    echo "BR_ER_S1 capture results:"
    if [ -s /tmp/br_er_s1_capture.log ]; then
        tail -10 /tmp/br_er_s1_capture.log
    else
        echo "  No packets captured on BR_ER_S1"
    fi
    echo ""
fi

if [ -f /tmp/br_er_s2_capture.log ]; then
    echo "BR_ER_S2 capture results:"
    if [ -s /tmp/br_er_s2_capture.log ]; then
        tail -10 /tmp/br_er_s2_capture.log
    else
        echo "  No packets captured on BR_ER_S2"
    fi
fi

echo ""
echo "7. Advanced troubleshooting:"
echo "----------------------------"

# Check if packets are being sent from N9Kv interfaces
echo "Check N9Kv interface statistics:"
echo "On N9Kv console:"
echo "  show interface ethernet1/1 counters"
echo "  show interface ethernet1/2 counters"
echo ""
echo "Look for increasing TX packets when you ping"

echo ""
echo "8. Alternative QEMU network configuration:"
echo "-----------------------------------------"
echo "If connectivity still fails, try modifying your QEMU command:"
echo ""
echo "Replace:"
echo "  -netdev bridge,id=ER_S1,br=BR_ER_S1"
echo "  -device e1000,netdev=ER_S1,mac=00:00:11:00:00:02"
echo ""
echo "With:"
echo "  -netdev bridge,id=ER_S1,br=BR_ER_S1,helper=/usr/lib/qemu/qemu-bridge-helper"
echo "  -device virtio-net-pci,netdev=ER_S1,mac=00:00:11:00:00:02"
echo ""
echo "Or use TAP explicitly:"
echo "  -netdev tap,id=ER_S1,ifname=tap_er_s1,script=no,downscript=no"
echo "  -device virtio-net-pci,netdev=ER_S1,mac=00:00:11:00:00:02"
echo "Then manually: ip link set tap_er_s1 master BR_ER_S1"

echo ""
echo "=== SUMMARY ==="
echo "MTU has been fixed to 1500 on all bridges"
echo "Test interfaces created: 10.1.1.100 (BR_ER_S1), 10.2.2.100 (BR_ER_S2)"
echo "Run ping tests from N9Kv console and check the packet capture results"

# Cleanup function
cleanup_test() {
    echo ""
    echo "To clean up test interfaces:"
    echo "  ip netns del test_BR_ER_S1"
    echo "  ip netns del test_BR_ER_S2"
    echo "  ip link del veth_BR_ER_S1_0"
    echo "  ip link del veth_BR_ER_S2_0"
}

cleanup_test
