#!/bin/bash

# Install multiple N9KV instances using your TAP topology
export HOSTNAME="LE1"
export N9KV_IMAGE="/iso1/nxos/$HOSTNAME.qcow2"
export CONFIG_ISO="/iso2/nxos/config/$HOSTNAME.iso"
# Switch 1 (LE1) - Leaf
virt-install \
    --name=$HOSTNAME \
    --machine q35 \
    --ram=8192 --vcpus=4 \
    --disk path=$N9KV_IMAGE,format=qcow2,bus=sata,cache=writethrough \
    --disk path=$CONFIG_ISO,device=cdrom,readonly=on \
    --network bridge=BR_ND_DATA,model=e1000 \
    --network bridge=BR_SP1_LE1,model=e1000 \
    --network bridge=BR_LE1_HO1,model=e1000 \
    --serial tcp,host=0.0.0.0:2011,mode=bind,protocol=telnet \
    --console pty,target_type=serial \
    --graphics vnc,port=5911 \
    --os-variant=linux2022 --import --noautoconsole
