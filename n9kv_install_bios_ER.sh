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
# Create local disk copies for each VM (N9KV needs writable disks)
cp "$N9KV_SHARED_IMAGE" "$ER_IMAGE"

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

echo "ER N9KV instance created."
