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
virt-install \
    --name=$VM_NAME \
    --machine type=pc-i440fx-3.1,accel=kvm \
    --boot loader=$BIOS_FILE \
    --ram=$RAM \
    --vcpus=$VCPUS \
    --disk path=$ER_IMAGE,format=qcow2,bus=sata \
    --network bridge=$MGMT_BRIDGE,model=$MODEL,mac=52:11:00:00:00:01 \
    --network bridge=$MGMT_BRIDGE,model=$MODEL,mac=52:11:00:00:00:02 \
    --network bridge=BR_ER_S1,model=$MODEL,mac=52:11:00:00:00:03 \
    --network bridge=BR_ER_S2,model=$MODEL,mac=52:11:00:00:00:04 \
    --graphics none \
    --console pty,target_type=serial \
    --serial pty \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

echo "$VM_NAME instance created."
echo "ER -> S1: BR_ER_S1"
echo "ER -> S2: BR_ER_S2"
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
