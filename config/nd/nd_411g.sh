#!/usr/bin/env bash
#
# Install a Nexus Dashboard (ND) instance using QEMU/KVM
ND_SOURCE_DIR=/iso1/nd/411g
ND_IMAGE=nd-dk9.4.1.1g.qcow2
ND_INSTALL_DIR=/iso2/nd/411g
ND_MGMT_NET=outside
ND_DATA_NET=BR_ND_DATA
ND_NAME=nd411g
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
echo "Installation may take some time. Monitor progress with 'virsh console $ND_NAME'."
