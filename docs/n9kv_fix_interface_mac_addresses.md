
# nexus9000v Fix Interface Mac Addresses

Now that the nexus9000v switches have booted, you may notice the following in their console logs.

```bash
 %STP-2-DISPUTE_DETECTED: Dispute detected on port Ethernet1/1 in VLAN0001 from Bridge ID 0000.0001.1b08 source MAC 0000.0001.0102 PVID 1
```

To fix this, we'll run Ansible playbooks to push `switch_freeform` policies to
Nexus Dashboard that configure unique mac addresses on the inter-switch links.
Without this, the nexus9000v will not be able to peer, since the interface
Eth1/1-2 mac addresses are identical on all switches.

These playbooks require the NDFC Ansible Collection.  So if you
haven't already, follow the link here to install it.

[Install NDFC Ansible Collection](./install_ansible_collection.md)

Either edit `$HOME/repos/n9kv-kvm/config/ansible/dynamic_inventory.py` to update
the following variables to match your setup, or set environment variables for them.
Below, we set environment variables as we do not want to leave passwords laying
around on disk.

Replace `your_nd_password` with the password you used when bringing up
Nexus Dashboard.

We also export the following:

- `ND_IP4` The IP address of Nexus Dashboard
- `no_proxy` and `NO_PROXY` environment variables with the address of Nexus Dashboard to avoid proxy-related errors.
- `ANSIBLE_COLLECTIONS_PATH` so that the playbook tasks find the `cisco.dcnm.dcnm_policy` module.

```bash
source $HOME/repos/n9kv-kvm/.venv/bin/activate
cd $HOME/repos/n9kv-kvm/config/ansible
export ND_IP4=192.168.11.2
export ND_USERNAME=admin
export ND_PASSWORD=your_nd_password
export NO_PROXY=$ND_IP4
export no_proxy=$ND_IP4
export ANSIBLE_COLLECTIONS_PATH=$HOME/repos/ansible/collections
ansible-playbook interface_mac_addresses_ER.yaml -i dynamic_inventory.py
ansible-playbook interface_mac_addresses_S1.yaml -i dynamic_inventory.py
ansible-playbook interface_mac_addresses_S2.yaml -i dynamic_inventory.py
ansible-playbook interface_mac_addresses_L1.yaml -i dynamic_inventory.py
ansible-playbook interface_mac_addresses_L2.yaml -i dynamic_inventory.py
```

After running the above scripts do a `Recalculate and Deploy` in Nexus
Dashboard for the `SITE1`, `SITE2`, and `ISN` fabrics.
