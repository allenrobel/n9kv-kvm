#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
IMAGE_PATH=/iso/nxos
# N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v.9.3.4.qcow2
N9KV_SHARED_IMAGE=$IMAGE_PATH/nexus9300v.10.1.2.qcow2
BIOS_FILE=$IMAGE_PATH/bios.bin
DISK_SIZE=32G    # Customize size as needed
RAM=16384        # 8GB RAM (minimum recommended)
VCPUS=4          # 4 vCPUs (minimum recommended)
# MODEL=rtl8139  # Network model for older systems
# MODEL=ne2k_pci # Network model for older systems
# MODEL=pcnet    # Network model for older systems
MODEL=e1000      # Network model
# MODEL=e1000e   # Network model for newer systems

MGMT_BRIDGE=ndfc-data  # Management bridge

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

S1_IMAGE=$IMAGE_PATH/S1.qcow2
# Create writable disk copies for each VM
echo "Creating disk images..."
# Create full copies instead of backing files
cp $N9KV_SHARED_IMAGE $S1_IMAGE

# Resize the copies
qemu-img resize $S1_IMAGE $DISK_SIZE

# Verify sizes
echo "Disk image sizes:"
qemu-img info $S1_IMAGE | grep "virtual size"


# Switch 1 (S1) - Border Spine Switch
echo "Creating Switch 1 (S1) - Border Spine Switch..."
VM_NAME=S1
virt-install \
    --name=$VM_NAME \
    --machine q35 \
    --boot loader=$BIOS_FILE \
    --ram=$RAM \
    --vcpus=$VCPUS \
    --disk path=$S1_IMAGE,format=qcow2,bus=sata \
    --network bridge=$MGMT_BRIDGE,model=$MODEL,mac=52:21:00:00:00:05 \
    --network bridge=$MGMT_BRIDGE,model=$MODEL,mac=52:21:00:00:00:06 \
    --network bridge=BR_ER_S1,model=$MODEL,mac=52:21:00:00:00:07 \
    --network bridge=BR_S1_L1,model=$MODEL,mac=52:21:00:00:00:08 \
    --graphics none \
    --console pty,target_type=serial \
    --serial pty \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

echo "$VM_NAME instance created."
echo "S1 -> ER: BR_ER_S1"
echo "S1 -> L1: BR_S1_L1"
echo "All mgmt interfaces connected to $MGMT_BRIDGE bridge."
echo ""
echo "Console access:"
echo "virsh console $VM_NAME"
echo ""
echo "Alternative: Check Virtual Machine Manager for PTY devices"
echo ""
echo "VM Management:"
echo "virsh list                   # Show running VMs"
echo "virsh start <name>           # Start a VM"
echo "virsh shutdown <name>        # Graceful shutdown"
echo "virsh destroy <name>         # Force stop"
