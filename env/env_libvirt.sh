# This file is meant to be sourced.
# e.g. source ./evn_libvirt.sh
# If Virtual Machine Manager (virt-manager) was started as root, set the environment variable
# to allow commands such as "virsh list" to query the correct virt-manager instance.
export LIBVIRT_DEFAULT_URI="qemu:///system"

# If Virtual Machine Manager was started as non-root user, comment the above line
# and uncomment the following line to use the user session.
# export LIBVIRT_DEFAULT_URI="qemu:///session"