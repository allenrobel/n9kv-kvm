#!/bin/bash

# QEMU N9KV Startup Script
# Based on your working QEMU configuration

IMAGE_PATH="/iso/nxos"
N9KV_SHARED_IMAGE="$IMAGE_PATH/nexus9300v64.10.3.8.M.qcow2"
ER_IMAGE="$IMAGE_PATH/ER.qcow2"
S1_IMAGE="$IMAGE_PATH/S1.qcow2"
S2_IMAGE="$IMAGE_PATH/S2.qcow2"
L1_IMAGE="$IMAGE_PATH/L1.qcow2"
# Create writable disk copies for each VM
echo "Creating disk images..."
cp "$N9KV_SHARED_IMAGE" "$ER_IMAGE"
cp "$N9KV_SHARED_IMAGE" "$S1_IMAGE"
cp "$N9KV_SHARED_IMAGE" "$S2_IMAGE"
cp "$N9KV_SHARED_IMAGE" "$L1_IMAGE"

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
qemu-system-x86_64 -nographic -monitor none -smp 4 -m 8192 -enable-kvm \
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
  -drive file=$ER_IMAGE,if=none,id=drive-sata-disk0,format=qcow2 \
  -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,id=sata-disk0 \
  -serial telnet:localhost:9020,server,nowait \
  -M q35 \
  -name n9kv-ER &

sleep 2

# Start S1 (Spine 1)
echo "Starting n9kv-S1..."
qemu-system-x86_64 -nographic -monitor none -smp 4 -m 8192 -enable-kvm \
  -device i82801b11-bridge,id=dmi-pci-bridge \
  -device pci-bridge,id=bridge-1,chassis_nr=1,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-2,chassis_nr=2,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-3,chassis_nr=3,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-4,chassis_nr=4,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-5,chassis_nr=5,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-6,chassis_nr=6,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-7,chassis_nr=7,bus=dmi-pci-bridge \
  -netdev tap,ifname=tap_S1_MGMT,script=no,downscript=no,id=eth_s1_mgmt \
  -device e1000,bus=bridge-1,addr=1.0,netdev=eth_s1_mgmt,mac=00:b0:21:02:01:00,multifunction=on,romfile= \
  -netdev tap,ifname=tap_S1_E1_1,script=no,downscript=no,id=eth_s1_e1_1 \
  -device e1000,bus=bridge-1,addr=1.1,netdev=eth_s1_e1_1,mac=00:b0:21:02:01:01,multifunction=on,romfile= \
  -netdev tap,ifname=tap_S1_E1_2,script=no,downscript=no,id=eth_s1_e1_2 \
  -device e1000,bus=bridge-1,addr=1.2,netdev=eth_s1_e1_2,mac=00:b0:21:02:01:02,multifunction=on,romfile= \
  -device ahci,id=ahci0 \
  -drive file=$S1_IMAGE,if=none,id=drive-sata-disk0,format=qcow2 \
  -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,id=sata-disk0 \
  -serial telnet:localhost:9021,server,nowait \
  -M q35 \
  -name n9kv-S1 &

sleep 2

# Start S2 (Spine 2)
echo "Starting n9kv-S2..."
qemu-system-x86_64 -nographic -monitor none -smp 4 -m 8192 -enable-kvm \
  -device i82801b11-bridge,id=dmi-pci-bridge \
  -device pci-bridge,id=bridge-1,chassis_nr=1,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-2,chassis_nr=2,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-3,chassis_nr=3,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-4,chassis_nr=4,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-5,chassis_nr=5,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-6,chassis_nr=6,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-7,chassis_nr=7,bus=dmi-pci-bridge \
  -netdev tap,ifname=tap_S2_MGMT,script=no,downscript=no,id=eth_s2_mgmt \
  -device e1000,bus=bridge-1,addr=1.0,netdev=eth_s2_mgmt,mac=00:b0:21:02:02:00,multifunction=on,romfile= \
  -netdev tap,ifname=tap_S2_E1_1,script=no,downscript=no,id=eth_s2_e1_1 \
  -device e1000,bus=bridge-1,addr=1.1,netdev=eth_s2_e1_1,mac=00:b0:21:02:02:01,multifunction=on,romfile= \
  -netdev tap,ifname=tap_S2_E1_2,script=no,downscript=no,id=eth_s2_e1_2 \
  -device e1000,bus=bridge-1,addr=1.2,netdev=eth_s2_e1_2,mac=00:b0:21:02:02:02,multifunction=on,romfile= \
  -device ahci,id=ahci0 \
  -drive file=$S2_IMAGE,if=none,id=drive-sata-disk0,format=qcow2 \
  -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,id=sata-disk0 \
  -serial telnet:localhost:9022,server,nowait \
  -M q35 \
  -name n9kv-S2 &

sleep 2

# Start L1 (Leaf 1)
echo "Starting n9kv-L1..."
qemu-system-x86_64 -nographic -monitor none -smp 4 -m 8192 -enable-kvm \
  -device i82801b11-bridge,id=dmi-pci-bridge \
  -device pci-bridge,id=bridge-1,chassis_nr=1,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-2,chassis_nr=2,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-3,chassis_nr=3,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-4,chassis_nr=4,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-5,chassis_nr=5,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-6,chassis_nr=6,bus=dmi-pci-bridge \
  -device pci-bridge,id=bridge-7,chassis_nr=7,bus=dmi-pci-bridge \
  -netdev tap,ifname=tap_L1_MGMT,script=no,downscript=no,id=eth_l1_mgmt \
  -device e1000,bus=bridge-1,addr=1.0,netdev=eth_l1_mgmt,mac=00:b0:21:02:03:00,multifunction=on,romfile= \
  -netdev tap,ifname=tap_L1_E1_1,script=no,downscript=no,id=eth_l1_e1_1 \
  -device e1000,bus=bridge-1,addr=1.1,netdev=eth_l1_e1_1,mac=00:b0:21:02:03:01,multifunction=on,romfile= \
  -netdev tap,ifname=tap_L1_E1_2,script=no,downscript=no,id=eth_l1_e1_2 \
  -device e1000,bus=bridge-1,addr=1.2,netdev=eth_l1_e1_2,mac=00:b0:21:02:03:02,multifunction=on,romfile= \
  -device ahci,id=ahci0 \
  -drive file=$L1_IMAGE,if=none,id=drive-sata-disk0,format=qcow2 \
  -device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,id=sata-disk0 \
  -serial telnet:localhost:9023,server,nowait \
  -M q35 \
  -name n9kv-L1 &

echo ""
echo "All N9KV instances starting..."
echo ""
echo "Console access via telnet:"
echo "telnet localhost 9020  # n9kv-ER"
echo "telnet localhost 9021  # n9kv-S1" 
echo "telnet localhost 9022  # n9kv-S2"
echo "telnet localhost 9023  # n9kv-L1"
echo ""
echo "To stop all instances:"
echo "pkill -f 'qemu-system.*n9kv'"
echo ""
echo "To reconnect TAP interfaces to bridges after shutdown:"
echo "./setup-custom-network.sh"
echo ""
echo "Process IDs:"
jobs -l