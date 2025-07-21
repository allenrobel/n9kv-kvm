#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
N9KV_IMAGE="/iso/nxos/nexus9300v64.10.3.8.M.qcow2"

# Create local disk copies for each VM (N9KV needs writable disks)
cp "$N9KV_IMAGE" ER.qcow2
cp "$N9KV_IMAGE" S1.qcow2  
cp "$N9KV_IMAGE" S2.qcow2
cp "$N9KV_IMAGE" L1.qcow2

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
    --serial telnet,host=localhost,port=9022,mode=bind,protocol=raw \
    --os-variant=linux2022 \
    --boot hd \
    --import \
    --noautoconsole

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
    --serial telnet,host=localhost,port=9023,mode=bind,protocol=raw \
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
echo "Console access via telnet:"
echo "telnet localhost 9020  # n9kv-ER"
echo "telnet localhost 9021  # n9kv-S1"
echo "telnet localhost 9022  # n9kv-S2"
echo "telnet localhost 9023  # n9kv-L1"
echo ""
echo "Alternative console access:"
echo "virsh console n9kv-ER"
echo "virsh console n9kv-S1"
echo "virsh console n9kv-S2"
echo "virsh console n9kv-L1"
echo ""
echo "VM Management:"
echo "virsh list                    # Show running VMs"
echo "virsh start <name>           # Start a VM"
echo "virsh shutdown <name>        # Graceful shutdown"
echo "virsh destroy <name>         # Force stop"