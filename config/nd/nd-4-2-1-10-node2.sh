#!/usr/bin/env bash
#
# Install a Nexus Dashboard (ND) instance using QEMU/KVM
ND_VERSION=4.2.1.10
ND_NODE=node2
ND_SOURCE_DIR=/iso1/nd/$ND_VERSION
ND_IMAGE=nd-dk9.$ND_VERSION.qcow2
ND_NAME=nd.$ND_VERSION.$ND_NODE
ND_INSTALL_DIR=/iso3/nd/$ND_VERSION
ND_MGMT_NET=outside
ND_DATA_NET=BR_ND_DATA_14
ND_DISK1_IMAGE=nd-$ND_NODE-disk1.qcow2
ND_DISK2_IMAGE=nd-$ND_NODE-disk2.qcow2
mkdir $ND_INSTALL_DIR
qemu-img create -f qcow2 -F qcow2 -b $ND_SOURCE_DIR/$ND_IMAGE $ND_INSTALL_DIR/$ND_DISK1_IMAGE
qemu-img create -f qcow2 $ND_INSTALL_DIR/$ND_DISK2_IMAGE 500G
sudo virt-install --name $ND_NAME \
    --vcpus 16 --ram 96000 --osinfo linux2020 \
    --graphics none \
    --disk path=$ND_INSTALL_DIR/$ND_DISK1_IMAGE \
    --disk path=$ND_INSTALL_DIR/$ND_DISK2_IMAGE \
    --network bridge:$ND_MGMT_NET,model=virtio,address.type=pci,address.domain=0,address.bus=0,address.slot=3 \
    --network bridge=$ND_DATA_NET,virtualport_type=openvswitch,model=virtio,address.type=pci,address.domain=0,address.bus=0,address.slot=4 \
    --noautoconsole --import

echo "Nexus Dashboard $ND_NAME installation started. Use 'virsh list' to check status."
echo "You will need to access the console to complete the setup."
echo "  'virsh console $ND_NAME'"
echo "Management network: $ND_MGMT_NET"
echo "Data network: $ND_DATA_NET"
echo "Image path: $ND_INSTALL_DIR/$ND_DISK1_IMAGE"
echo "Data disk path: $ND_INSTALL_DIR/$ND_DISK2_IMAGE"
echo "Installation may take some time. Monitor progress with 'virsh console $ND_NAME'."
