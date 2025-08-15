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

ND_IP4 = environ.get("ND_IP4", "192.168.7.7")
CR1_IP4 = environ.get("CR1_IP4", "192.168.12.111")
ER1_IP4 = environ.get("ER1_IP4", "192.168.12.121")
BG1_IP4 = environ.get("BG1_IP4", "192.168.12.131")
BG2_IP4 = environ.get("BG2_IP4", "192.168.12.132")
SP1_IP4 = environ.get("SP1_IP4", "192.168.12.141")
SP2_IP4 = environ.get("SP2_IP4", "192.168.12.142")
LE1_IP4 = environ.get("LE1_IP4", "192.168.12.151")
LE2_IP4 = environ.get("LE2_IP4", "192.168.12.152")
LE1_IP4_INTERFACE_2 = environ.get("LE1_IP4_INTERFACE_2", "192.168.0.151")
LE2_IP4_INTERFACE_2 = environ.get("LE2_IP4_INTERFACE_2", "192.168.0.152")

# Fabric types
SITE1_FABRIC = environ.get("ND_SITE1_FABRIC", "SITE1")
SITE2_FABRIC = environ.get("ND_SITE2_FABRIC", "SITE2")
ISN_FABRIC = environ.get("ND_ISN_FABRIC", "ISN")
MSD_FABRIC = environ.get("ND_MSD_FABRIC", "MSD")

# Device credentials
ND_PASSWORD = environ.get("ND_PASSWORD", "SuperSecretPassword")
ND_USERNAME = environ.get("ND_USERNAME", "admin")
NXOS_PASSWORD = environ.get("NXOS_PASSWORD", "SuperSecretPassword")
NXOS_USERNAME = environ.get("NXOS_USERNAME", "admin")

# Switch hostnames
# CR = Core Router (route server)
# ER = Edge Router
# BG = Border Gateway
# SP = Spine
# LE = Leaf

CR1_HOSTNAME = environ.get("CR1_HOSTNAME", "CR1")
ER1_HOSTNAME = environ.get("ER1_HOSTNAME", "ER1")
BG1_HOSTNAME = environ.get("BG1_HOSTNAME", "BG1")
BG2_HOSTNAME = environ.get("BG2_HOSTNAME", "BG2")
SP1_HOSTNAME = environ.get("SP1_HOSTNAME", "SP1")
SP2_HOSTNAME = environ.get("SP2_HOSTNAME", "SP2")
LE1_HOSTNAME = environ.get("LE1_HOSTNAME", "LE1")
LE2_HOSTNAME = environ.get("LE2_HOSTNAME", "LE2")

# Links
# Source             Destination        Bridge
# CR1_INTERFACE_1    ER1_INTERFACE_3    BR_CR1_ER1
# ER1_INTERFACE_1    BG1_INTERFACE_1    BR_ER1_BG1
# ER1_INTERFACE_2    BG2_INTERFACE_1    BR_ER1_BG2
# BG1_INTERFACE_2    SP1_INTERFACE_1    BR_BG1_SP1
# BG2_INTERFACE_2    SP2_INTERFACE_1    BR_BG2_SP2
# SP1_INTERFACE_2    LE1_INTERFACE_1    BR_SP1_LE1
# SP2_INTERFACE_2    LE2_INTERFACE_1    BR_SP2_LE2
# LE1_INTERFACE_2    HO1_INTERFACE_1    BR_LE1_HO1
# LE2_INTERFACE_2    HO2_INTERFACE_1    BR_LE2_HO2

# Base set of interfaces
CR1_INTERFACE_1 = environ.get("CR1_INTERFACE_1", "Ethernet1/1")

ER1_INTERFACE_1 = environ.get("ER1_INTERFACE_1", "Ethernet1/1")
ER1_INTERFACE_2 = environ.get("ER1_INTERFACE_2", "Ethernet1/2")
ER1_INTERFACE_3 = environ.get("ER1_INTERFACE_3", "Ethernet1/3")

BG1_INTERFACE_1 = environ.get("BG1_INTERFACE_1", "Ethernet1/1")
BG1_INTERFACE_2 = environ.get("BG1_INTERFACE_2", "Ethernet1/2")

BG2_INTERFACE_1 = environ.get("BG2_INTERFACE_1", "Ethernet1/1")
BG2_INTERFACE_2 = environ.get("BG2_INTERFACE_2", "Ethernet1/2")

SP1_INTERFACE_1 = environ.get("SP1_INTERFACE_1", "Ethernet1/1")
SP1_INTERFACE_2 = environ.get("SP1_INTERFACE_2", "Ethernet1/2")

SP2_INTERFACE_1 = environ.get("SP2_INTERFACE_1", "Ethernet1/1")
SP2_INTERFACE_2 = environ.get("SP2_INTERFACE_2", "Ethernet1/2")

LE1_INTERFACE_1 = environ.get("LE1_INTERFACE_1", "Ethernet1/1")
LE1_INTERFACE_2 = environ.get("LE1_INTERFACE_2", "Ethernet1/2")

LE2_INTERFACE_1 = environ.get("LE2_INTERFACE_1", "Ethernet1/1")
LE2_INTERFACE_2 = environ.get("LE2_INTERFACE_2", "Ethernet1/2")

# Unique mac addresses for the above interfaces.
CR1_MAC_1 = environ.get("CR1_MAC_1", "0000.0011.0001")

ER1_MAC_1 = environ.get("ER1_MAC_1", "0000.0021.0001")
ER1_MAC_2 = environ.get("ER1_MAC_2", "0000.0021.0002")

BG1_MAC_1 = environ.get("BG1_MAC_1", "0000.0031.0001")
BG1_MAC_2 = environ.get("BG1_MAC_2", "0000.0031.0002")

BG2_MAC_1 = environ.get("BG2_MAC_1", "0000.0032.0001")
BG2_MAC_2 = environ.get("BG2_MAC_2", "0000.0032.0002")

SP1_MAC_1 = environ.get("SP1_MAC_1", "0000.0041.0001")
SP1_MAC_2 = environ.get("SP1_MAC_2", "0000.0041.0002")

SP2_MAC_1 = environ.get("SP2_MAC_1", "0000.0042.0001")
SP2_MAC_2 = environ.get("SP2_MAC_2", "0000.0042.0002")

LE1_MAC_1 = environ.get("LE1_MAC_1", "0000.0051.0001")
LE1_MAC_2 = environ.get("LE1_MAC_2", "0000.0051.0002")

LE2_MAC_1 = environ.get("LE2_MAC_1", "0000.0052.0001")
LE2_MAC_2 = environ.get("LE2_MAC_2", "0000.0052.0002")

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
            "SITE1_FABRIC": SITE1_FABRIC,
            "SITE2_FABRIC": SITE2_FABRIC,
            "ISN_FABRIC": ISN_FABRIC,
            "ND_IP4": ND_IP4,
            "CR1_IP4": CR1_IP4,
            "ER1_IP4": ER1_IP4,
            "BG1_IP4": BG1_IP4,
            "BG2_IP4": BG2_IP4,
            "SP1_IP4": SP1_IP4,
            "SP2_IP4": SP2_IP4,
            "LE1_IP4": LE1_IP4,
            "LE2_IP4": LE2_IP4,
            "CR1_HOSTNAME": CR1_HOSTNAME,
            "ER1_HOSTNAME": ER1_HOSTNAME,
            "BG1_HOSTNAME": BG1_HOSTNAME,
            "BG2_HOSTNAME": BG2_HOSTNAME,
            "SP1_HOSTNAME": SP1_HOSTNAME,
            "SP2_HOSTNAME": SP2_HOSTNAME,
            "LE1_HOSTNAME": LE1_HOSTNAME,
            "LE2_HOSTNAME": LE2_HOSTNAME,
            "CR1_MAC_1": CR1_MAC_1,
            "ER1_MAC_1": ER1_MAC_1,
            "ER1_MAC_2": ER1_MAC_2,
            "BG1_MAC_1": BG1_MAC_1,
            "BG1_MAC_2": BG1_MAC_2,
            "BG2_MAC_1": BG2_MAC_1,
            "BG2_MAC_2": BG2_MAC_2,
            "SP1_MAC_1": SP1_MAC_1,
            "SP1_MAC_2": SP1_MAC_2,
            "SP2_MAC_1": SP2_MAC_1,
            "SP2_MAC_2": SP2_MAC_2,
            "LE1_MAC_1": LE1_MAC_1,
            "LE1_MAC_2": LE1_MAC_2,
            "LE2_MAC_1": LE2_MAC_1,
            "LE2_MAC_2": LE2_MAC_2,
            "CR1_INTERFACE_1": CR1_INTERFACE_1,
            "ER1_INTERFACE_1": ER1_INTERFACE_1,
            "ER1_INTERFACE_2": ER1_INTERFACE_2,
            "ER1_INTERFACE_3": ER1_INTERFACE_3,
            "BG1_INTERFACE_1": BG1_INTERFACE_1,
            "BG1_INTERFACE_2": BG1_INTERFACE_2,
            "BG2_INTERFACE_1": BG2_INTERFACE_1,
            "BG2_INTERFACE_2": BG2_INTERFACE_2,
            "SP1_INTERFACE_1": SP1_INTERFACE_1,
            "SP1_INTERFACE_2": SP1_INTERFACE_2,
            "SP2_INTERFACE_1": SP2_INTERFACE_1,
            "SP2_INTERFACE_2": SP2_INTERFACE_2,
            "LE1_INTERFACE_1": LE1_INTERFACE_1,
            "LE1_INTERFACE_2": LE1_INTERFACE_2,
            "LE2_INTERFACE_1": LE2_INTERFACE_1,
            "LE2_INTERFACE_2": LE2_INTERFACE_2,
            "LE1_IP4_INTERFACE_2": LE1_IP4_INTERFACE_2,
            "LE2_IP4_INTERFACE_2": LE2_IP4_INTERFACE_2,
            "ND_PASSWORD": ND_PASSWORD,
            "ND_USERNAME": ND_USERNAME,
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
            "CR1",
            "BG1",
            "BG2",
            "ER1",
            "SP1",
            "SP2",
            "LE1",
            "LE2",
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
