#!/bin/bash
VM_NAME="nd322m_test"

# Get the disk path(s) before destroying
DISK_PATH=$(virsh domblklist $VM_NAME | grep -v '^-' | awk '{print $2}' | grep -v '^$')

# Check if the VM exists
if virsh list --all | grep -q "^\s*$VM_NAME"; then
    virsh destroy $VM_NAME 2>/dev/null || true
    virsh undefine $VM_NAME
else
    echo "VM $VM_NAME not found"
    exit 1
fi

# Remove disk images
for disk in $DISK_PATH; do
    [ -f "$disk" ] && rm "$disk"
done

echo "Nexus Dashboard $VM_NAME has been destroyed and its disk images removed."