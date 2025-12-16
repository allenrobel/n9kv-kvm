#!/bin/bash
# Script to expand bootflash in Nexus 9000v image
# Run this BEFORE creating VMs

SOURCE_IMAGE="/iso1/nxos/nexus9300v64.10.3.8.M.qcow2"
MODIFIED_IMAGE="/iso1/nxos/nexus9300v64.10.3.8.M-expanded.qcow2"

# 1. Copy the original image
cp "$SOURCE_IMAGE" "$MODIFIED_IMAGE"

# 2. Resize the qcow2 container to 64GB (or whatever you need)
qemu-img resize "$MODIFIED_IMAGE" 64G

# 3. Connect the image via NBD (Network Block Device)
modprobe nbd max_part=8
qemu-nbd --connect=/dev/nbd0 "$MODIFIED_IMAGE"

# Give it a moment to settle
sleep 2

# 4. Check current partition layout
echo "Current partition layout:"
fdisk -l /dev/nbd0

# 5. Use parted to resize the bootflash partition (sda4)
# WARNING: This is destructive if done wrong!

# First, delete and recreate sda7 (logflash) if it's after bootflash
# Then expand sda4 (bootflash)

parted /dev/nbd0 << EOF
print
resizepart 4 16GB
print
quit
EOF

# 6. Resize the filesystem on bootflash
e2fsck -f /dev/nbd0p4
resize2fs /dev/nbd0p4

# 7. Verify the new size
echo "New partition layout:"
fdisk -l /dev/nbd0
df -h /dev/nbd0p4

# 8. Disconnect NBD
qemu-nbd --disconnect /dev/nbd0

echo "Modified image created: $MODIFIED_IMAGE"
echo "Bootflash should now have more space"
