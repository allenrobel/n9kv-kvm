#!/bin/bash

# N9Kv Kernel Boot Parameter Fix - Avoid CD-ROM detection entirely

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

echo "Testing different approaches to avoid CD-ROM hang..."

# APPROACH 1: Single IDE drive, no CD-ROM device at all
echo "=== APPROACH 1: Single IDE drive only ==="
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
    -device ahci,id=ahci0,bus=pcie.0 \
    -drive file=$ER_IMAGE,if=none,id=drive-sata-disk0,format=qcow2,cache=writethrough \
    -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,bootindex=1 \
    -monitor telnet:localhost:$MONITOR_PORT,server,nowait \
    -netdev bridge,id=ndfc-mgmt,br=$MGMT_BRIDGE \
    -device $MODEL,netdev=ndfc-mgmt,mac=00:00:11:00:00:01 \
    -netdev bridge,id=ER_S1,br=BR_ER_S1 \
    -device $MODEL,netdev=ER_S1,mac=00:00:11:00:00:02 \
    -netdev bridge,id=ER_S2,br=BR_ER_S2 \
    -device $MODEL,netdev=ER_S2,mac=00:00:11:00:00:03 \
    -name $VM_NAME &

VM_PID=$!

# Monitor function that doesn't try to eject CD-ROM
monitor_boot() {
    echo "Monitoring boot progress (no CD-ROM intervention)..."
    local timeout_count=0
    local max_timeouts=12  # Wait up to 6 minutes
    
    while [ $timeout_count -lt $max_timeouts ]; do
        sleep 30
        timeout_count=$((timeout_count + 1))
        echo "Check $timeout_count/$max_timeouts - Monitoring VM progress..."
        
        # Check if VM is still running
        if ! kill -0 $VM_PID 2>/dev/null; then
            echo "VM has exited"
            return 1
        fi
        
        # Try to capture any console output indicating progress
        if timeout 3 bash -c "echo '' | telnet localhost $TELNET_PORT" 2>/dev/null | grep -q "switch#\|login:\|Nexus\|NX-OS\|>" 2>/dev/null; then
            echo "SUCCESS: N9Kv appears to have booted!"
            return 0
        fi
        
        # Check for specific hang messages
        local console_output=$(timeout 3 bash -c "echo '' | telnet localhost $TELNET_PORT" 2>/dev/null)
        if echo "$console_output" | grep -q "Trying to mount cdrom"; then
            echo "WARNING: Still hanging at cdrom mount (attempt $timeout_count)"
            if [ $timeout_count -ge 8 ]; then
                echo "Giving up - cdrom hang persists"
                return 1
            fi
        fi
    done
    
    echo "Boot monitoring timeout reached"
    return 1
}

# Start monitoring
monitor_boot &
MONITOR_PID=$!

echo ""
echo "=== VM STARTED ==="
echo "VM PID: $VM_PID"
echo "Console: telnet localhost $TELNET_PORT"
echo "Monitor: telnet localhost $MONITOR_PORT"
echo ""
echo "Waiting for boot to complete (no automatic CD-ROM intervention)..."

# Wait for monitoring to complete
wait $MONITOR_PID
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo ""
    echo "=== SUCCESS ==="
    echo "N9Kv appears to have booted successfully!"
    echo "Connect with: telnet localhost $TELNET_PORT"
else
    echo ""
    echo "=== ALTERNATIVE APPROACHES ==="
    echo "APPROACH 1 failed. Trying alternative configurations..."
    
    # Kill current VM
    kill $VM_PID 2>/dev/null
    sleep 5
    pkill -f "qemu.*$VM_NAME" 2>/dev/null
    
    echo ""
    echo "=== APPROACH 2: Legacy IDE without AHCI ==="
    sleep 3
    
    qemu-system-x86_64 \
        -enable-kvm \
        -machine type=q35,accel=kvm,kernel-irqchip=off \
        -cpu qemu64,-smep,-smap,-spec-ctrl \
        -smp 2,sockets=1,cores=2,threads=1 \
        -m 6144 \
        -rtc clock=host,base=localtime \
        -nographic \
        -bios $BIOS_FILE \
        -serial telnet:localhost:$TELNET_PORT,server=on,wait=off \
        -drive file=$ER_IMAGE,if=ide,index=0,format=qcow2,cache=writethrough \
        -monitor telnet:localhost:$MONITOR_PORT,server,nowait \
        -netdev bridge,id=ndfc-mgmt,br=$MGMT_BRIDGE \
        -device rtl8139,netdev=ndfc-mgmt,mac=00:00:11:00:00:01 \
        -netdev bridge,id=ER_S1,br=BR_ER_S1 \
        -device rtl8139,netdev=ER_S1,mac=00:00:11:00:00:02 \
        -netdev bridge,id=ER_S2,br=BR_ER_S2 \
        -device rtl8139,netdev=ER_S2,mac=00:00:11:00:00:03 \
        -name ${VM_NAME}_alt &
    
    ALT_PID=$!
    echo "Alternative VM started with PID: $ALT_PID"
    echo "Testing for 3 minutes..."
    
    sleep 180
    if kill -0 $ALT_PID 2>/dev/null; then
        echo "Alternative approach is running - check console manually"
        echo "telnet localhost $TELNET_PORT"
    else
        echo "Alternative approach also failed"
    fi
fi

echo ""
echo "=== FINAL STATUS ==="
echo "Console: telnet localhost $TELNET_PORT"
echo "Monitor: telnet localhost $MONITOR_PORT"