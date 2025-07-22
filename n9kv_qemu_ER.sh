#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
IMAGE_PATH=/iso/nxos
# N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v.9.3.4.qcow2
N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v.10.1.2.qcow2
BIOS_FILE=$IMAGE_PATH/bios.bin
DISK_SIZE=32G    # Customize size as needed
RAM=8192         # 8GB RAM (minimum recommended)
VCPUS=4          # 4 vCPUs (minimum recommended)
# MODEL=rtl8139  # Network model for older systems
# MODEL=ne2k_pci # Network model for older systems
# MODEL=pcnet    # Network model for older systems
MODEL=e1000      # Network model
# MODEL=e1000e   # Network model for newer systems

MGMT_BRIDGE=ndfc-data  # Management bridge

TELNET_PORT=9020  # Default telnet port for console access

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
n9kv_virt_ER.sh

# Ensure TAP interfaces are available
echo "Preparing TAP interfaces..."
ip link set tap_ER_MGMT nomaster 2>/dev/null || true
ip link set tap_ER_MGMT up 2>/dev/null || true

# Use QEMU with specific PCI slot assignments
qemu-system-x86_64 \
    -nographic -monitor none -smp $VCPUS -m $RAM -enable-kvm -bios $BIOS_FILE \
    -M q35 \
    -device i82801b11-bridge,id=dmi-pci-bridge \
    -device pci-bridge,id=bridge-1,chassis_nr=1,bus=dmi-pci-bridge \
    -device pci-bridge,id=bridge-2,chassis_nr=2,bus=dmi-pci-bridge \
    -device pci-bridge,id=bridge-3,chassis_nr=3,bus=dmi-pci-bridge \
    -netdev tap,ifname=tap_ER_MGMT,script=no,downscript=no,id=mgmt0 \
    -device e1000,bus=bridge-1,addr=1.0,netdev=mgmt0,mac=52:54:00:11:00:00,multifunction=on,romfile= \
    -netdev tap,ifname=tap_ER_E1_1,script=no,downscript=no,id=eth1 \
    -device e1000,bus=bridge-1,addr=1.1,netdev=eth1,mac=52:54:00:11:00:01,multifunction=on,romfile= \
    -netdev tap,ifname=tap_ER_E1_2,script=no,downscript=no,id=eth2 \
    -device e1000,bus=bridge-1,addr=1.2,netdev=eth2,mac=52:54:00:11:00:02,multifunction=on,romfile= \
    -device ahci,id=ahci0 \
    -drive file=$ER_IMAGE,if=none,id=drive-sata-disk0,format=qcow2 \
    -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,id=sata-disk0 \
    -serial telnet:localhost:$TELNET_PORT,server,nowait \
    -name $VM_NAME &

echo "$VM_NAME instance created."
echo "ER -> S1: BR_ER_S1"
echo "ER -> S2: BR_ER_S2"
echo "All mgmt interfaces connected to $MGMT_BRIDGE bridge."
echo ""
echo "Console access:"
echo "telnet localhost $TELNET_PORT"
echo ""
echo "To stop all instances:"
echo "pkill -f 'qemu-system.*n9kv'"
echo ""
echo "To reconnect TAP interfaces to bridges after shutdown:"
echo "./setup-custom-network.sh"
echo ""
echo "Process IDs:"
pgrep -f 'qemu-system.*n9kv' | xargs -I {} echo "PID: {}"
echo "N9KV ER starting..."
