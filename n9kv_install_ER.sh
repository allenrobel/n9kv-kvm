#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
N9KV_IMAGE="/iso/nxos/nexus9300v64.10.3.8.M.qcow2"

# Create local disk copies for each VM (N9KV needs writable disks)
cp "$N9KV_IMAGE" ER.qcow2

# Switch 1 (ER) - Edge Router
virt-install \
    --name="n9kv-ER" \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=ER.qcow2,format=qcow2,bus=sata \
    --network type=direct,source=tap_ER_MGMT,model=e1000,mac=00:b0:21:02:00:00 \
    --network type=direct,source=tap_ER_E1_1,model=e1000,mac=00:b0:21:02:00:01 \
    --network type=direct,source=tap_ER_E1_2,model=e1000,mac=00:b0:21:02:00:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial telnet,host=localhost,port=9020,mode=bind,protocol=raw \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

echo "ER N9KV instance created."
