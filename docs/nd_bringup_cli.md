# ND Bringup - CLI Phase

Edit one of the `nd_qemu_*.sh` files (e.g. `nd_qemu_321e.sh`) in
`$HOME/repos/n9kv-kvm/config/qemu/` to suit your environment e.g.
the ND image path and name.  Note the `ND_NAME` setting
in this file.  This is what you will console to below.

Also, take note of disk space requirements.  The ND qcow2 images
range from 15.9GB (321e) to 16.4GB (4.1 EFT), so ensure your
`ND_SOURCE_DIR` (see below) has at least this much space.

And note that `ND_INSTALL_DIR` (see below) needs to have enough
space to hold both of the created disk1 and disk2 files.  With
ND 4.1, and a very minimal configuration, this is 50GB, but these
disks are configured to grow to 500GB (e.g. ND hosts nexus9000v images
which will grow the size of disk2 as you upload these images to ND),
so plan accordingly based on your estimated usage.

```bash
ND_SOURCE_DIR=/iso/nd         # The directory containing ND_IMAGE
ND_IMAGE=nd-dk9.3.2.1e.qcow2  # The ND image name
ND_INSTALL_DIR=/iso/nd/321e   # Where to create ND disk1 and disk2
ND_MGMT_NET=BR_ND_MGMT        # Bridge for ND's management network
ND_DATA_NET=BR_ND_DATA        # Bridge for ND's data network
ND_NAME=nd_321e               # Name of ND instance (use for console below)
```

Below are current sizes in a newly-installed ND 4.1 EFT setup.

```bash
arobel@cvd-2:~$ ls -l /iso/nd/4.1.0.156b/running
total 47226124
-rw-r--r-- 1 libvirt-qemu kvm  1349058560 Jul 27 18:47 nd-node1-disk1.qcow2
-rw-r--r-- 1 libvirt-qemu kvm 47009562624 Jul 27 18:47 nd-node1-disk2.qcow2
arobel@cvd-2:~$
```

And the same for an ND 3.2(1e) setup hosting one NX-OS image.

```bash
(.venv) arobel@cvd-1:~/repos/n9kv-kvm$ ls -l /iso/nd/321e
total 172147752
-rwx------ 1 root         arobel          766 Oct 10  2024 install.bash
-rw-r--r-- 1 libvirt-qemu kvm     68034297856 Jul 29 23:35 nd-node1-disk1.qcow2
-rw-r--r-- 1 libvirt-qemu kvm    108243255296 Jul 29 23:35 nd-node1-disk2.qcow2
(.venv) arobel@cvd-1:~/repos/n9kv-kvm$ 
```

Once you've reviewed and modified the ND setup script, run it and connect
to the virsh console to finish the ND setup.

```bash
cd $HOME/repos/n9kv-kvm/config/qemu
sudo ./nd_qemu_321e.sh
virsh console nd_321e
```

After connecting to the virsh console, give the setup some time
(5 to 10 minutes) and you'll eventually see something similar to
the output below.

Press return and answer the questions for Admin Password,
Management Network IP Address/Mask, and Cluster Leader (answer
Y to cluster leader since we are using a single node setup).

You'll use an address within `Vlan11` connected to `BR_ND_MGMT`
for Management Network IP Address/Mask.  See the preceeding section
`Configure netplan` to configure `Vlan11` and the bridges.

```bash
Press any key to run first-boot setup on this console...

Fri Jul 25 02:22:46 UTC 2025: Starting Nexus Dashboard setup utility
Welcome to Nexus Dashboard 4.1.0.156b 
Press Enter to manually bootstrap your node...
Admin Password: 
Reenter Admin Password: 
Management Network: 
  IP Address/Mask: 192.168.11.2/24
Is Cluster Leader? Note: only one node in the cluster must be leader. (Y/n): Y
Please review the config
Cluster Leader: true
Management Network:
  Gateway: 192.168.11.1
  IP Address/Mask: 192.168.11.2/24

Re-enter config?(y/N): N

System configured successfully
Initializing System on first boot. Please wait..
Fri Jul 25 02:24:29 UTC 2025: Nexus Dashboard setup complete.

<skip stuff...>

Nexus Dashboard localhost ttyS0

Nexus Dashboard (4.1.0.156b): system initialized successfully
Please wait for system to boot : [########################################] 100%
System up, please wait for UI to be online.

System UI online, please login to https://192.168.11.2 to continue.
```
