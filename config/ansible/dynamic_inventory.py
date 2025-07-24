#!/usr/bin/env python3
"""
# Summary
Dynamic inventory for n9kv testbed. Inventory is built from environment variables.

## Usage Example

```bash
ansible-playbook \
    $HOME/repos/n9kv-kvm/config/ansible/interface_mac_addresses_ER.yaml \
    -i $HOME/repos/n9kv-kvm/config/ansible/dynamic_inventory.py
```

### Environment Variables

This inventory script uses environment variables, or locally-set variables,
to define the testbed configuration.

It first tries to read the variables from the environment, and if not set,
it uses the defaults defined in this script.

"""
import json
from os import environ

# Try to populate vars from the environment, else use defaults.

# Device IP addresses

ND_IP4 = environ.get("ND_IP4", "192.168.1.2")
ER_IP4 = environ.get("ER_IP4", "192.168.11.111")
S1_IP4 = environ.get("S1_IP4", "192.168.11.121")
S2_IP4 = environ.get("S2_IP4", "192.168.11.122")
L1_IP4 = environ.get("L1_IP4", "192.168.11.131")


FABRIC_VXLAN = environ.get("ND_FABRIC_VXLAN", "VXLAN")
FABRIC_ISN = environ.get("ND_FABRIC_ISN", "ISN")
ND_PASSWORD = environ.get("ND_PASSWORD", "SuperSecretPassword")
ND_USERNAME = environ.get("ND_USERNAME", "admin")
NXOS_PASSWORD = environ.get("NXOS_PASSWORD", "SuperSecretPassword")
NXOS_USERNAME = environ.get("NXOS_USERNAME", "admin")


# Base set of interfaces
ER_INTERFACE_1 = environ.get("ER_INTERFACE_1", "Ethernet1/1")
ER_INTERFACE_2 = environ.get("ER_INTERFACE_2", "Ethernet1/2")
S1_INTERFACE_1 = environ.get("S1_INTERFACE_1", "Ethernet1/1")
S1_INTERFACE_2 = environ.get("S1_INTERFACE_2", "Ethernet1/2")
S2_INTERFACE_1 = environ.get("S2_INTERFACE_1", "Ethernet1/1")
S2_INTERFACE_2 = environ.get("S2_INTERFACE_2", "Ethernet1/2")
L1_INTERFACE_1 = environ.get("L1_INTERFACE_1", "Ethernet1/1")
L1_INTERFACE_2 = environ.get("L1_INTERFACE_2", "Ethernet1/2")

# Unique mac addresses for the above interfaces.
ER_MAC_1 = environ.get("ER_MAC_1", "0000.0011.0001")
ER_MAC_2 = environ.get("ER_MAC_2", "0000.0011.0002")
S1_MAC_1 = environ.get("S1_MAC_1", "0000.0021.0001")
S1_MAC_2 = environ.get("S1_MAC_2", "0000.0021.0002")
S2_MAC_1 = environ.get("S2_MAC_1", "0000.0022.0001")
S2_MAC_2 = environ.get("S2_MAC_2", "0000.0022.0002")
L1_MAC_1 = environ.get("L1_MAC_1", "0000.0031.0001")
L1_MAC_2 = environ.get("L1_MAC_2", "0000.0031.0002")

# output is printed to STDOUT, where ansible-playbook -i reads it.
# If you change any vars above, be sure to add them below.
# We'll clean this up as the integration test vars are standardized.

output = {
    "_meta": {"hostvars": {}},
    "all": {
        "children": ["ungrouped", "nd", "nxos"],
        "vars": {
            "ansible_httpapi_use_ssl": "true",
            "ansible_httpapi_validate_certs": "false",
            "ansible_password": ND_PASSWORD,
            "ansible_python_interpreter": "python",
            "ansible_user": ND_USERNAME,
            "fabric_vxlan": FABRIC_VXLAN,
            "fabric_isn": FABRIC_ISN,
            "ER_IP4": ER_IP4,
            "S1_IP4": S1_IP4,
            "S2_IP4": S2_IP4,
            "L1_IP4": L1_IP4,
            "ER_INTERFACE_1": ER_INTERFACE_1,
            "ER_INTERFACE_2": ER_INTERFACE_2,
            "S1_INTERFACE_1": S1_INTERFACE_1,
            "S1_INTERFACE_2": S1_INTERFACE_2,
            "S2_INTERFACE_1": S2_INTERFACE_1,
            "S2_INTERFACE_2": S2_INTERFACE_2,
            "L1_INTERFACE_1": L1_INTERFACE_1,
            "L1_INTERFACE_2": L1_INTERFACE_2,
            "NXOS_USERNAME": NXOS_USERNAME,
            "NXOS_PASSWORD": NXOS_PASSWORD,
            "SWITCH_PASSWORD": NXOS_PASSWORD,
            "SWITCH_USERNAME": NXOS_USERNAME,
        },
    },
    "nd": {
        "hosts": [ND_IP4],
        "vars": {
            "ansible_connection": "ansible.netcommon.httpapi",
            "ansible_network_os": "cisco.dcnm.dcnm",
        },
    },
    "nxos": {
        "children": [
            "ER",
            "S1",
            "S2",
            "L1",
        ],
        "vars": {
            "ansible_become": "true",
            "ansible_become_method": "enable",
            "ansible_connection": "ansible.netcommon.network_cli",
            "ansible_network_os": "cisco.nxos.nxos",
        },
    },
}

print(json.dumps(output, indent=4, sort_keys=True))
