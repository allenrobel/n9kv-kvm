#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
N9KV_IMAGE="/iso/nxos/nexus9300v64.10.3.8.M.qcow2"

# Create local disk copies for each VM (N9KV needs writable disks)
cp "$N9KV_IMAGE" S1.qcow2  

# Switch 2 (S1) - Border Spine Switch
virt-install \
    --name="n9kv-S1" \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=S1.qcow2,format=qcow2,bus=sata \
    --network type=direct,source=tap_S1_MGMT,model=e1000,mac=00:b0:21:02:01:00 \
    --network type=direct,source=tap_S1_E1_1,model=e1000,mac=00:b0:21:02:01:01 \
    --network type=direct,source=tap_S1_E1_2,model=e1000,mac=00:b0:21:02:01:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial telnet,host=localhost,port=9021,mode=bind,protocol=raw \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

echo "S1 N9KV instance created."
