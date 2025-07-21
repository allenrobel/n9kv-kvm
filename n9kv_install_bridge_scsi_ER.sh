#!/bin/bash

# Install multiple N9KV instances using your TAP topology
N9KV_IMAGE_ER="/iso/nxos/ER.qcow2"

# Switch 1 (ER) - Edge Router
virt-install \
    --name="n9kv-ER" \
    --ram=8192 --vcpus=4 \
    --disk path="$N9KV_IMAGE_ER",format=qcow2,bus=scsi,cache=writethrough \
    --network bridge=ndfc-mgmt,model=e1000 \
    --network bridge=BR_ER_S1,model=e1000 \
    --network bridge=BR_ER_S2,model=e1000 \
    --graphics vnc,port=5901 \
    --os-variant=linux2022 --import --noautoconsole
