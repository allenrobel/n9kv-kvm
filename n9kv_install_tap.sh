#!/bin/bash

# Install multiple N9KV instances using your TAP topology
N9KV_IMAGE="/path/to/nexus9300v64.10.3.6.F.qcow2"

# Switch 1 (L1) - Leaf Switch
virt-install \
    --name="n9kv-ER" \
    --ram=8192 --vcpus=4 \
    --disk path="$N9KV_IMAGE",format=qcow2,bus=ide,cache=writethrough \
    --network type=direct,source=tap_ER_MGMT,model=e1000 \
    --network type=direct,source=tap_ER_E1_1,model=e1000 \
    --network type=direct,source=tap_ER_E1_2,model=e1000 \
    --graphics vnc,port=5901 \
    --os-variant=linux2022 --import --noautoconsole

# Switch 2 (S1) - Spine Switch
virt-install \
    --name="n9kv-S1" \
    --ram=8192 --vcpus=4 \
    --disk path="$N9KV_IMAGE",format=qcow2,bus=ide,cache=writethrough \
    --network type=direct,source=tap_S1_MGMT,model=e1000 \
    --network type=direct,source=tap_S1_E1_1,model=e1000 \
    --network type=direct,source=tap_S1_E1_2,model=e1000 \
    --graphics vnc,port=5902 \
    --os-variant=linux2022 --import --noautoconsole

# Switch 3 (S2) - Spine Switch
virt-install \
    --name="n9kv-S2" \
    --ram=8192 --vcpus=4 \
    --disk path="$N9KV_IMAGE",format=qcow2,bus=ide,cache=writethrough \
    --network type=direct,source=tap_S2_MGMT,model=e1000 \
    --network type=direct,source=tap_S2_E1_1,model=e1000 \
    --network type=direct,source=tap_S2_E1_2,model=e1000 \
    --graphics vnc,port=5903 \
    --os-variant=linux2022 --import --noautoconsole

# Switch 4 (L1) - Leaf Switch
virt-install \
    --name="n9kv-L1" \
    --ram=8192 --vcpus=4 \
    --disk path="$N9KV_IMAGE",format=qcow2,bus=ide,cache=writethrough \
    --network type=direct,source=tap_L1_MGMT,model=e1000 \
    --network type=direct,source=tap_L1_E1_1,model=e1000 \
    --network type=direct,source=tap_L1_E1_2,model=e1000 \
    --graphics vnc,port=5904 \
    --os-variant=linux2022 --import --noautoconsole

echo "All N9KV instances created. Network topology:"
echo "ER -> S1: BR_ER_S1"
echo "ER -> S2: BR_ER_S2"
echo "S1 -> L1: BR_S1_L1"
echo "S2 -> L1: BR_S2_L1"
echo "All mgmt interfaces on ndfc-mgmt bridge"
echo "If Virtual Machine Manager (virt-manager) is installed, you can view and manage these instances there."
echo "See env in this directory if virsh list is not displaying VM instances."
echo "Use 'virsh list' to see running instances and 'virsh console <name>' to access them."
echo "Use 'virsh start <name>' to start any instance if not running."
echo "Use 'virsh shutdown <name>' to gracefully stop any instance."
echo "Use 'virsh destroy <name>' to force stop any instance if needed."
echo "Use 'virsh undefine <name>' to remove an instance completely."
echo "Use 'virsh net-list' to see active networks and 'virsh net-destroy <name>' to stop any network."
