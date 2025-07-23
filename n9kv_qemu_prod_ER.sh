#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
IMAGE_PATH=/iso/nxos
# N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v.9.3.4.qcow2
# N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v.10.1.2.qcow2
N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v64.10.3.8.M.qcow2
BIOS_FILE=$IMAGE_PATH/bios.bin

# VM configuration parameters
DISK_SIZE=32G    # Customize size as needed
RAM=16384        # 16GB RAM
VCPUS=4          # 4 vCPUs (minimum recommended)
MODEL=e1000      # Network model

# MODEL=e1000e   # Network model for newer systems
# MODEL=ne2k_pci # Network model for older systems
# MODEL=pcnet    # Network model for older systems
# MODEL=rtl8139  # Network model for older systems

MGMT_BRIDGE=ndfc-mgmt  # Management bridge

TELNET_PORT=9020  # Default telnet port for console access
MONITOR_PORT=4444  # Default monitor port for QEMU

# Check if BIOS file exists
if [ ! -f $BIOS_FILE ]; then
    echo "ERROR: BIOS file $BIOS_FILE not found!"
    echo "Install OVMF for 64-bit images: sudo apt install ovmf"
    echo "OR:"
    sudo "Install OVMF for 32-bit images: apt install ovmf-ia32"
    echo "Then copy (for 64-bit):"
    echo "cp /usr/share/ovmf/OVMF.fd $BIOS_FILE"
    echo "Or copy (for 32-bit):"
    echo "cp /usr/share/OVMF/OVMF32_CODE_4M.fd $BIOS_FILE"
    echo "Exiting..."
    exit 1
fi

ER_IMAGE=$IMAGE_PATH/ER.qcow2
# Create writable disk copies for each VM
echo "Creating disk images..."
# Create full copies instead of backing files
cp $N9KV_SHARED_IMAGE $ER_IMAGE

# Resize the copies
qemu-img resize $ER_IMAGE $DISK_SIZE

# Verify sizes
echo "Disk image sizes:"
qemu-img info $ER_IMAGE | grep "virtual size"


# Switch 1 (ER) - Edge Router
echo "Creating Switch 1 (ER) - Edge Router..."
VM_NAME=ER

<<'ORIGINAL_CONFIG'
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
    -device virtio-scsi-pci,id=scsi0 \
    -drive file=$ER_IMAGE,if=none,id=drive-scsi0,format=qcow2,cache=writethrough \
    -device scsi-hd,bus=scsi0.0,drive=drive-scsi0,bootindex=1 \
    -drive if=ide,media=cdrom,readonly=on \
    -monitor telnet:localhost:$MONITOR_PORT,server,nowait \
    -netdev bridge,id=ndfc-mgmt,br=$MGMT_BRIDGE \
    -device $MODEL,netdev=ndfc-mgmt,mac=00:00:11:00:00:01 \
    -netdev bridge,id=ER_S1,br=BR_ER_S1 \
    -device $MODEL,netdev=ER_S1,mac=00:00:11:00:00:02 \
    -netdev bridge,id=ER_S2,br=BR_ER_S2 \
    -device $MODEL,netdev=ER_S2,mac=00:00:11:00:00:03 \
    -name $VM_NAME &
ORIGINAL_CONFIG

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


echo "$VM_NAME instance created."
echo "ER -> S1: BR_ER_S1"
echo "ER -> S2: BR_ER_S2"
echo "$VM_NAME starting..."
echo ""
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
