# To run this script, do the following.
# LE1# run bash
# bash-4.4$ su
# Password:  <<< admin password >>>
# bash-4.4#
# bash-4.4# vi setup_external_disk.bash # Or copy it to bootflash e.g. copy scp://user@host:/path/to/setup_external_disk.bash bootflash:setup_external_disk.bash
# bash-4.4# bash setup_external_disk.bash # or, if you copied it to bootflash:, bash /bootflash/setup_external_disk.bash
# bash-4.4# chgrp network-admin /mnt/images  # Change group to network-admin
# bash-4.4# chmod g+w /mnt/images # Give network-admin group write permissions
# bash-4.4# cd /bootflash
# bash-4.4# cp nxos.10.3.8.M.bin /mnt/images/ # Copy NX-OS image to new disk (modify to use whatever image is present)
# bash-4.4# rm nxos.10.3.8.M.bin # Remove original image from bootflash
# bash-4.4# ln -s /mnt/images/nxos.10.3.8.M.bin nxos.10.3.8.M.bin # Create symlink in bootflash to new location
# bash-4.4# df --human . # should show close to 4GB free

# Detect disks
lsblk

# Assuming external disk is /dev/sdb, partition it
fdisk /dev/sdb << EOF
n
p
1


w
EOF

# Format with ext4
mkfs.ext4 -L IMAGES /dev/sdb1

# Create mount point
mkdir -p /mnt/images

# Mount it
mount /dev/sdb1 /mnt/images

# Verify
df -h /mnt/images

# Get UUID for fstab
UUID=$(blkid -s UUID -o value /dev/sdb1)
echo "UUID=$UUID /mnt/images ext4 defaults 0 2" >> /etc/fstab

# Test fstab entry
umount /mnt/images
mount -a
df -h /mnt/images

# Set permissions
chmod 755 /mnt/images

# Exit back to NX-OS
exit
