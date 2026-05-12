#!/bin/bash

# Install multiple N9KV instances using your TAP topology
export HOSTNAME="S1_LE1"
export N9KV_IMAGE="/iso1/nxos/$HOSTNAME.qcow2"
export CONFIG_ISO="/iso2/nxos/config/$HOSTNAME.iso"
# S1_LE1 - Leaf 1 in SITE1
virt-install \
    --name=$HOSTNAME \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=$N9KV_IMAGE,format=qcow2,bus=sata,cache=writethrough \
    --disk path=$CONFIG_ISO,device=cdrom,readonly=on \
    --network bridge=BR_ND_DATA,model=e1000 \
    --network bridge=BR_S1_SP1_LE1_1,model=e1000 \
    --network bridge=BR_S1_LE1_H1_1,model=e1000 \
    --serial tcp,host=0.0.0.0:2011,mode=bind,protocol=telnet \
    --console pty,target_type=serial \
    --graphics vnc,port=5911 \
    --os-variant=linux2022 --import --noautoconsole
