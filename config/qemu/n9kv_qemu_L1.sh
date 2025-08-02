#!/bin/bash

# Switch configuration parameters
SWITCH_NAME=L1
SWITCH_ROLE="Leaf Switch"
# SWITCH_SERIAL must be unique per switch and is required for n9kv bootup with unique MAC addresses
SWITCH_SERIAL=9ABCDEF031
NEIGHBOR_1=S1
NEIGHBOR_2=S2
MGMT_BRIDGE=BR_ND_DATA
ISL_BRIDGE_1=BR_S1_L1
ISL_BRIDGE_2=BR_S2_L1
# MAC_1 sets mgmt0 mac address
# The other two are for ISL links but, alas, are ignored by n9kv bootup.
# We use the ./config/ansible/interface_mac_addresses_*.yaml scripts to set these.
MAC_1="00:00:31:00:00:01"
MAC_2="00:00:31:00:00:02"
MAC_3="00:00:31:00:00:03"

TELNET_PORT=9031   # Telnet port for console access
MONITOR_PORT=4431  # Monitor port for QEMU

IMAGE_PATH=/iso/nxos
# N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v64.10.3.8.M.qcow2
N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9500v64.10.5.3.F.qcow2

# sudo apt install ovmf
BIOS_FILE=/usr/share/ovmf/OVMF.fd

# To create dummy CD-ROM image with startup configuration
# mkisofs -o ER.iso -l --iso-level 2 nxos_config.txt
# Or see the playbook in ./config/ansible/playbooks/startup_config_iso.yaml
CDROM_PATH=/iso/nxos/config
CDROM_IMAGE=$CDROM_PATH/$SWITCH_NAME.iso

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
    -drive file=$CDROM_IMAGE,media=cdrom \
    -drive file=$VM_IMAGE,if=none,id=drive-sata-disk0,format=qcow2,cache=writethrough \
    -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,bootindex=1 \
    -monitor telnet:localhost:$MONITOR_PORT,server,nowait \
    -netdev bridge,id=ND_DATA,br=$MGMT_BRIDGE \
    -device $MODEL,netdev=ND_DATA,mac=$MAC_1 \
    -netdev bridge,id=ISL_BRIDGE_1,br=$ISL_BRIDGE_1 \
    -device $MODEL,netdev=ISL_BRIDGE_1,mac=$MAC_2 \
    -netdev bridge,id=ISL_BRIDGE_2,br=$ISL_BRIDGE_2 \
    -device $MODEL,netdev=ISL_BRIDGE_2,mac=$MAC_3 \
    -name $VM_NAME &


echo "$VM_NAME instance created."
echo ""
echo "$SWITCH_NAME -> $NEIGHBOR_1: $ISL_BRIDGE_1"
echo "$SWITCH_NAME -> $NEIGHBOR_2: $ISL_BRIDGE_2"
echo ""
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
