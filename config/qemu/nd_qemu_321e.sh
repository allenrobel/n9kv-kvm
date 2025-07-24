#!/usr/bin/env bash
#
ND_SOURCE_DIR=/iso/nd
ND_INSTALL_DIR=/iso/nd/321e
ND_MGMT_NET=BR_ND_MGMT
ND_DATA_NET=BR_ND_DATA
ND_IMAGE=nd-dk9.3.2.1e.qcow2
ND_NAME=nd_321e
mkdir $ND_INSTALL_DIR
qemu-img create -f qcow2 -F qcow2 -b $ND_SOURCE_DIR/$ND_IMAGE $ND_INSTALL_DIR/nd-node1-disk1.qcow2
qemu-img create -f qcow2 $ND_INSTALL_DIR/nd-node1-disk2.qcow2 500G
sudo virt-install --name $ND_NAME \
    --vcpus 16 --ram 96000 --osinfo linux2020 \
    --disk path=$ND_INSTALL_DIR/nd-node1-disk1.qcow2 \
    --disk path=$ND_INSTALL_DIR/nd-node1-disk2.qcow2 \
    --network bridge:$ND_MGMT_NET,model=virtio,address.type=pci,address.domain=0,address.bus=0,address.slot=3 \
    --network bridge:$ND_DATA_NET,model=virtio,address.type=pci,address.domain=0,address.bus=0,address.slot=4 \
    --noautoconsole --import

echo "Nexus Dashboard $ND_NAME installation started. Use 'virsh list' to check status."
echo "You will need to access the console to complete the setup."
echo "  'virsh console $ND_NAME'"
echo "Management network: $ND_MGMT_NET"
echo "Data network: $ND_DATA_NET"
echo "Image path: $ND_INSTALL_DIR/nd-node1-disk1.qcow2"
echo "Data disk path: $ND_INSTALL_DIR/nd-node1-disk2.qcow2"
echo "Installation may take some time. Monitor progress with 'virsh console $ND_NAME'.
