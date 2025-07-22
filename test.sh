#!/bin/bash

# N9Kv CD-ROM Timeout Workaround - Let it hang, then auto-fix

IMAGE_PATH=/iso/nxos
N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v.10.1.2.qcow2
BIOS_FILE=$IMAGE_PATH/bios.bin

DISK_SIZE=32G
RAM=8192
VCPUS=2
MODEL=e1000
MGMT_BRIDGE=ndfc-mgmt
TELNET_PORT=9020
MONITOR_PORT=4444

ER_IMAGE=$IMAGE_PATH/ER.qcow2
VM_NAME=ER

# Create disk image
cp $N9KV_SHARED_IMAGE $ER_IMAGE
qemu-img resize $ER_IMAGE $DISK_SIZE

echo "Starting N9Kv with automatic CD-ROM hang fix..."

# SOLUTION: Use IDE (for bootflash detection) + automatic intervention
qemu-system-x86_64 \
    -enable-kvm \
    -machine type=q35,accel=kvm,kernel-irqchip=on \
    -cpu qemu64,+ssse3,+sse4.1,+sse4.2,-smep,-smap,-spec-ctrl \
    -smp $VCPUS,sockets=1,cores=$VCPUS,threads=1 \
    -m $RAM \
    -object memory-backend-ram,id=ram-node0,size=${RAM}M \
    -numa node,nodeid=0,cpus=0-$((VCPUS-1)),memdev=ram-node0 \
    -rtc clock=host,base=localtime \
    -nographic \
    -bios $BIOS_FILE \
    -serial telnet:localhost:$TELNET_PORT,server=on,wait=off \
    -drive file=$ER_IMAGE,if=ide,format=qcow2,cache=writethrough \
    -drive if=ide,media=cdrom \
    -monitor telnet:localhost:$MONITOR_PORT,server,nowait \
    -netdev bridge,id=ndfc-mgmt,br=$MGMT_BRIDGE \
    -device $MODEL,netdev=ndfc-mgmt,mac=00:00:11:00:00:01 \
    -netdev bridge,id=ER_S1,br=BR_ER_S1 \
    -device $MODEL,netdev=ER_S1,mac=00:00:11:00:00:02 \
    -netdev bridge,id=ER_S2,br=BR_ER_S2 \
    -device $MODEL,netdev=ER_S2,mac=00:00:11:00:00:03 \
    -name $VM_NAME &

VM_PID=$!
echo "VM started with PID: $VM_PID"

# Function to monitor and auto-fix CD-ROM hang
auto_fix_cdrom() {
    echo "Starting automatic CD-ROM hang monitor..."
    sleep 30  # Give VM time to start
    
    local hang_detected=false
    local boot_successful=false
    local timeout_count=0
    local max_timeouts=8  # Wait up to 4 minutes (8 * 30 seconds)
    
    while [ $timeout_count -lt $max_timeouts ]; do
        sleep 30
        timeout_count=$((timeout_count + 1))
        echo "Check $timeout_count/$max_timeouts - Monitoring VM progress..."
        
        # Check if VM is still running
        if ! kill -0 $VM_PID 2>/dev/null; then
            echo "VM has exited unexpectedly"
            return 1
        fi
        
        # Try to capture console output
        if timeout 3 bash -c "echo 'show version' | telnet localhost $TELNET_PORT" 2>/dev/null | grep -q "switch#\|Nexus\|NX-OS"; then
            echo "SUCCESS: N9Kv has booted successfully!"
            boot_successful=true
            break
        fi
        
        # Check if we're at the hang point (2+ minutes of waiting)
        if [ $timeout_count -ge 4 ] && [ "$hang_detected" = "false" ]; then
            echo "Detected likely CD-ROM hang - attempting automatic fix..."
            hang_detected=true
            
            # Try to eject CD-ROM via monitor
            timeout 10 bash -c "
                echo 'info block' | telnet localhost $MONITOR_PORT
                sleep 2
                echo 'eject ide1-cd0' | telnet localhost $MONITOR_PORT  
                sleep 2
                echo 'change ide1-cd0 /dev/null' | telnet localhost $MONITOR_PORT
                sleep 2
                echo 'quit' | telnet localhost $MONITOR_PORT
            " 2>/dev/null
            
            echo "CD-ROM eject attempted - continuing to monitor..."
        fi
    done
    
    if [ "$boot_successful" = "true" ]; then
        echo "=== N9Kv Boot Successful ==="
        echo "Console access: telnet localhost $TELNET_PORT"
        echo "Username: admin (no password initially)"
        return 0
    else
        echo "Boot timeout reached - manual intervention may be needed"
        echo "Try connecting to: telnet localhost $TELNET_PORT"
        echo "Or monitor: telnet localhost $MONITOR_PORT"
        return 1
    fi
}

# Alternative manual fix function
manual_fix_instructions() {
    echo ""
    echo "=== MANUAL FIX INSTRUCTIONS ==="
    echo "If the automatic fix doesn't work, do this manually:"
    echo ""
    echo "1. Open another terminal and connect to QEMU monitor:"
    echo "   telnet localhost $MONITOR_PORT"
    echo ""
    echo "2. In the monitor, type these commands:"
    echo "   info block"
    echo "   eject ide1-cd0" 
    echo "   change ide1-cd0 /dev/null"
    echo "   quit"
    echo ""
    echo "3. Then check console:"
    echo "   telnet localhost $TELNET_PORT"
    echo ""
    echo "4. If still hanging, try restarting the VM with:"
    echo "   pkill -f 'qemu.*$VM_NAME'"
    echo "   # Then run this script again"
    echo ""
}

# Start the monitoring in background
auto_fix_cdrom &
MONITOR_PID=$!

# Show manual instructions
manual_fix_instructions

echo ""
echo "VM is starting... Automatic monitoring active."
echo "Console: telnet localhost $TELNET_PORT"
echo "Monitor: telnet localhost $MONITOR_PORT"
echo ""
echo "Waiting for boot completion or timeout..."

# Wait for the monitoring to complete
wait $MONITOR_PID
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "N9Kv is ready for use!"
else
    echo "Automatic fix may not have worked - try manual intervention"
fi