#!/bin/bash

# Switch configuration parameters
SWITCH_NAME=ER
SWITCH_ROLE="Edge Router"
# SWITCH_SERIAL must be unique per switch and is required for n9kv bootup with unique MAC addresses
SWITCH_SERIAL="9ABCDEF011"
NEIGHBOR_1="S1"
NEIGHBOR_2="S2"
MGMT_BRIDGE=ndfc-mgmt
ISL_BRIDGE_1="BR_ER_S1"
ISL_BRIDGE_2="BR_ER_S2"
# MAC_1 sets mgmt0 mac address
# The other two are for ISL links but, alas, are ignored by n9kv bootup.
# We use the ./config/ansible/interface_mac_addresses_*.yaml scripts to set these.
MAC_1="00:00:11:00:00:01"
MAC_2="00:00:11:00:00:02"
MAC_3="00:00:11:00:00:03"

TELNET_PORT=9011   # Telnet port for console access
MONITOR_PORT=4411  # Monitor port for QEMU

IMAGE_PATH=/iso/nxos
N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v64.10.3.8.M.qcow2
BIOS_FILE=$IMAGE_PATH/bios.bin

# You shouldn't have to change anything below this line...

# VM configuration parameters
DISK_SIZE=32G    # Customize size as needed
RAM=16384        # 16GB RAM
VCPUS=4          # 4 vCPUs (minimum recommended)
MODEL=e1000      # Network model

# Check if BIOS file exists
if [ ! -f $BIOS_FILE ]; then
    echo "ERROR: BIOS file $BIOS_FILE not found!"
    echo "Install OVMF for 64-bit images: sudo apt install ovmf"
    echo "Then copy:"
    echo "cp /usr/share/ovmf/OVMF.fd $BIOS_FILE"
    echo "Exiting..."
    exit 1
fi

VM_IMAGE=$IMAGE_PATH/$SWITCH_NAME.qcow2
# Create writable disk copies for each VM
echo "Creating disk images..."
# Create full copies instead of backing files
cp $N9KV_SHARED_IMAGE $VM_IMAGE

# Resize the copies
qemu-img resize $VM_IMAGE $DISK_SIZE

# Verify sizes
echo "Disk image sizes:"
qemu-img info $VM_IMAGE | grep "virtual size"

echo "Creating $SWITCH_NAME - $SWITCH_ROLE..."
VM_NAME=$SWITCH_NAME

qemu-system-x86_64 \
    -smbios type=1,manufacturer="Cisco",product="Nexus9000",serial="$SWITCH_SERIAL" \
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
    -drive file=$VM_IMAGE,if=none,id=drive-sata-disk0,format=qcow2,cache=writethrough \
    -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,bootindex=1 \
    -monitor telnet:localhost:$MONITOR_PORT,server,nowait \
    -netdev bridge,id=ndfc-mgmt,br=$MGMT_BRIDGE \
    -device $MODEL,netdev=ndfc-mgmt,mac=$MAC_1 \
    -netdev bridge,id=ISL_BRIDGE_1,br=$ISL_BRIDGE_1 \
    -device $MODEL,netdev=ISL_BRIDGE_1,mac=$MAC_2 \
    -netdev bridge,id=ISL_BRIDGE_2,br=$ISL_BRIDGE_2 \
    -device $MODEL,netdev=ISL_BRIDGE_2,mac=$MAC_3 \
    -name $VM_NAME &


echo "$VM_NAME instance created."
echo "$SWITCH_NAME -> $NEIGHBOR_1: $ISL_BRIDGE_1"
echo "$SWITCH_NAME -> $NEIGHBOR_2: $ISL_BRIDGE_2"
echo ""
echo "$VM_NAME starting..."
echo "All mgmt interfaces connected to $MGMT_BRIDGE bridge."
echo ""
echo "Console access:"
echo "telnet localhost $TELNET_PORT"
echo ""
echo "Monitor access:"
echo "telnet localhost $MONITOR_PORT"
echo ""
echo "To stop all instances:"
echo "pkill -f 'qemu-system.*n9kv'"
echo ""
echo "Process IDs:"
pgrep -f 'qemu-system.*n9kv' | xargs -I {} echo "PID: {}"
