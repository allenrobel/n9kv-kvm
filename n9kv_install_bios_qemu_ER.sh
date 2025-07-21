#!/bin/bash

# Install multiple N9KV instances using your TAP topology
# Based on working QEMU configuration
IMAGE_PATH="/iso/nxos"
N9KV_SHARED_IMAGE="$IMAGE_PATH/nexus9300v64.10.3.8.M.qcow2"
BIOS_FILE="$IMAGE_PATH/bios.bin"

# Check if BIOS file exists
if [ ! -f "$BIOS_FILE" ]; then
    echo "ERROR: BIOS file $BIOS_FILE not found!"
    echo "Install OVMF: sudo apt install ovmf"
    echo "Then copy: cp /usr/share/ovmf/OVMF.fd $BIOS_FILE"
    exit 1
fi

ER_IMAGE="$IMAGE_PATH/ER.qcow2"
# Create local disk copies for each VM (N9KV needs writable disks)
cp "$N9KV_SHARED_IMAGE" "$ER_IMAGE"

# Ensure TAP interfaces are available (not attached to bridges)
echo "Preparing TAP interfaces..."
ip link set tap_ER_MGMT nomaster 2>/dev/null || true
ip link set tap_ER_E1_1 nomaster 2>/dev/null || true
ip link set tap_ER_E1_2 nomaster 2>/dev/null || true
ip link set tap_S1_MGMT nomaster 2>/dev/null || true
ip link set tap_S1_E1_1 nomaster 2>/dev/null || true
ip link set tap_S1_E1_2 nomaster 2>/dev/null || true
ip link set tap_S2_MGMT nomaster 2>/dev/null || true
ip link set tap_S2_E1_1 nomaster 2>/dev/null || true
ip link set tap_S2_E1_2 nomaster 2>/dev/null || true
ip link set tap_L1_MGMT nomaster 2>/dev/null || true
ip link set tap_L1_E1_1 nomaster 2>/dev/null || true
ip link set tap_L1_E1_2 nomaster 2>/dev/null || true

# Start ER (Edge Router)
echo "Starting n9kv-ER..."
qemu-system-x86_64 -nographic -monitor none -smp 4 -m 8192 -enable-kvm -bios "$BIOS_FILE" \
  -device i82801b11-bridge,id=dmi-pci-bridge \
  -device pci-bridge,id=bridge-1,chassis_nr=1,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-2,chassis_nr=2,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-3,chassis_nr=3,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-4,chassis_nr=4,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-5,chassis_nr=5,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-6,chassis_nr=6,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-7,chassis_nr=7,bus=dmi-pci-bridge \
  -netdev tap,ifname=tap_ER_MGMT,script=no,downscript=no,id=eth_er_mgmt \
  -device e1000,bus=bridge-1,addr=1.0,netdev=eth_er_mgmt,mac=00:b0:21:02:00:00,multifunction=on,romfile= \
  -netdev tap,ifname=tap_ER_E1_1,script=no,downscript=no,id=eth_er_e1_1 \
  -device e1000,bus=bridge-1,addr=1.1,netdev=eth_er_e1_1,mac=00:b0:21:02:00:01,multifunction=on,romfile= \
  -netdev tap,ifname=tap_ER_E1_2,script=no,downscript=no,id=eth_er_e1_2 \
  -device e1000,bus=bridge-1,addr=1.2,netdev=eth_er_e1_2,mac=00:b0:21:02:00:02,multifunction=on,romfile= \
  -device ahci,id=ahci0 \
  -drive file=$ER_IMAGE,if=none,id=drive-sata-disk0,format=qcow2,bootindex=1 \
  -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,id=sata-disk0 \
  -drive file=fat:rw:.,media=cdrom \
  -serial telnet:localhost:9020,server,nowait \
  -M q35 \
  -name n9kv-ER &

echo "ER N9KV instance created."
