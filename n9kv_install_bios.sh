#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
IMAGE_PATH="/iso/nxos"
N9KV_SHARED_IMAGE="$IMAGE_PATH/nexus9300v64.10.3.8.M.qcow2"
BIOS_FILE="$IMAGE_PATH/bios.bin"

# Check if BIOS file exists
if [ ! -f "$BIOS_FILE" ]; then
    echo "ERROR: BIOS file $BIOS_FILE not found!"
    echo "Install OVMF: sudo apt install ovmf"
    echo "Then copy: cp /usr/share/ovmf/OVMF.fd $BIOS_FILE"
    exit 1
fi

ER_IMAGE="$IMAGE_PATH/ER.qcow2"
S1_IMAGE="$IMAGE_PATH/S1.qcow2"
S2_IMAGE="$IMAGE_PATH/S2.qcow2"
L1_IMAGE="$IMAGE_PATH/L1.qcow2"
# Create writable disk copies for each VM
echo "Creating disk images..."
cp "$N9KV_SHARED_IMAGE" "$ER_IMAGE"
cp "$N9KV_SHARED_IMAGE" "$S1_IMAGE"
cp "$N9KV_SHARED_IMAGE" "$S2_IMAGE"
cp "$N9KV_SHARED_IMAGE" "$L1_IMAGE"


# Switch 1 (ER) - Edge Router
virt-install \
    --name="n9kv-ER" \
    --machine q35 \
    --boot loader="$BIOS_FILE" \
    --ram=8192 --vcpus=4 \
    --disk path=$ER_IMAGE,format=qcow2,bus=sata \
    --network type=direct,source=tap_ER_MGMT,model=e1000,mac=00:b0:21:02:00:00 \
    --network type=direct,source=tap_ER_E1_1,model=e1000,mac=00:b0:21:02:00:01 \
    --network type=direct,source=tap_ER_E1_2,model=e1000,mac=00:b0:21:02:00:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial pty \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

# Switch 2 (S1) - Border Spine Switch
virt-install \
    --name="n9kv-S1" \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=$S1_IMAGE,format=qcow2,bus=sata \
    --network type=direct,source=tap_S1_MGMT,model=e1000,mac=00:b0:21:02:01:00 \
    --network type=direct,source=tap_S1_E1_1,model=e1000,mac=00:b0:21:02:01:01 \
    --network type=direct,source=tap_S1_E1_2,model=e1000,mac=00:b0:21:02:01:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial pty \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

# Switch 3 (S2) - Border Spine Switch
virt-install \
    --name="n9kv-S2" \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=$S2_IMAGE,format=qcow2,bus=sata \
    --network type=direct,source=tap_S2_MGMT,model=e1000,mac=00:b0:21:02:02:00 \
    --network type=direct,source=tap_S2_E1_1,model=e1000,mac=00:b0:21:02:02:01 \
    --network type=direct,source=tap_S2_E1_2,model=e1000,mac=00:b0:21:02:02:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial pty \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

# Switch 4 (L1) - Leaf Switch
virt-install \
    --name="n9kv-L1" \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=$L1_IMAGE,format=qcow2,bus=sata \
    --network type=direct,source=tap_L1_MGMT,model=e1000,mac=00:b0:21:02:03:00 \
    --network type=direct,source=tap_L1_E1_1,model=e1000,mac=00:b0:21:02:03:01 \
    --network type=direct,source=tap_L1_E1_2,model=e1000,mac=00:b0:21:02:03:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial pty \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

echo "All N9KV instances created. Network topology:"
echo "ER -> S1: BR_ER_S1"
echo "ER -> S2: BR_ER_S2"
echo "S1 -> L1: BR_S1_L1"
echo "S2 -> L1: BR_S2_L1"
echo "All mgmt interfaces connected to respective TAP interfaces"
echo ""
echo "Console access:"
echo "virsh console n9kv-ER"
echo "virsh console n9kv-S1"
echo "virsh console n9kv-S2"
echo "virsh console n9kv-L1"
echo ""
echo "Alternative: Check Virtual Machine Manager for PTY devices"
echo ""
echo "VM Management:"
echo "virsh list                   # Show running VMs"
echo "virsh start <name>           # Start a VM"
echo "virsh shutdown <name>        # Graceful shutdown"
echo "virsh destroy <name>         # Force stop"
