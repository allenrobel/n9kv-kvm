#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
N9KV_IMAGE="/iso/nxos/nexus9300v64.10.3.8.M.qcow2"

# Create local disk copies for each VM (N9KV needs writable disks)
cp "$N9KV_IMAGE" S2.qcow2

# Switch 3 (S2) - Border Spine Switch
virt-install \
    --name="n9kv-S2" \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=S2.qcow2,format=qcow2,bus=sata \
    --network type=direct,source=tap_S2_MGMT,model=e1000,mac=00:b0:21:02:02:00 \
    --network type=direct,source=tap_S2_E1_1,model=e1000,mac=00:b0:21:02:02:01 \
    --network type=direct,source=tap_S2_E1_2,model=e1000,mac=00:b0:21:02:02:02 \
    --graphics none \
    --console pty,target_type=serial \
    --serial tcp,host=localhost:9022,mode=bind,protocol=telnet \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

echo "S2 N9KV instance created."
