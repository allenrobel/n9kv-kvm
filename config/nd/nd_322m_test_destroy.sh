#!/bin/bash
VM_NAME="nd322m_test"

# Get the disk path(s) before destroying
DISK_PATH=$(virsh domblklist $VM_NAME | grep -v '^-' | awk '{print $2}' | grep -v '^$')

# Stop the VM
virsh destroy $VM_NAME

# Undefine it
virsh undefine $VM_NAME

# Remove disk images
for disk in $DISK_PATH; do
    [ -f "$disk" ] && rm "$disk"
done

echo "Nexus Dashboard $VM_NAME has been destroyed and its disk images removed."