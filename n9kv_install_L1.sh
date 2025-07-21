#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
N9KV_IMAGE="/iso/nxos/nexus9300v64.10.3.8.M.qcow2"

# Create local disk copies for each VM (N9KV needs writable disks)
cp "$N9KV_IMAGE" L1.qcow2

# Switch 4 (L1) - Leaf Switch
virt-install \
    --name="n9kv-L1" \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=L1.qcow2,format=qcow2,bus=sata \
    --network type=direct,source=tap_L1_MGMT,model=e1000,mac=00:b0:21:02:03:00 \
    --network type=direct,source=tap_L1_E1_1,model=e1000,mac=00:b0:21:02:03:01 \
    --network type=direct,source=tap_L1_E1_2,model=e1000,mac=00:b0:21:02:03:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial tcp,host=localhost:9023,mode=bind,protocol=telnet \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

echo "L1 N9KV instance created."
