#!/usr/bin/env python3
"""
# Summary
Dynamic inventory variant for n9kv testbed SITE3 / SITE4. Inventory is built
from environment variables.

## Usage Example

```bash
ansible-playbook \
    $HOME/repos/n9kv-kvm/config/ansible/some_playbook.yaml \
    -i $HOME/repos/n9kv-kvm/config/ansible/dynamic_inventory_site3_site4.py
```

### Environment Variables

This inventory script uses environment variables, or locally-set variables,
to define the testbed configuration.

It first tries to read the variables from the environment, and if not set,
it uses the defaults defined in this script.

### Naming convention

Hostnames and env var prefixes follow `S<site>_<role><idx>` (per-site
renumbering from 1).

"""
import json
from os import environ

# Try to populate vars from the environment, else use defaults.

# Device IP addresses

ND_IP4 = environ.get("ND_IP4", "192.168.7.7")

# SITE1 / SITE2
S1_BG1_IP4 = environ.get("S1_BG1_IP4", "192.168.12.131")
S2_BG1_IP4 = environ.get("S2_BG1_IP4", "192.168.12.132")
S1_SP1_IP4 = environ.get("S1_SP1_IP4", "192.168.12.141")
S2_SP1_IP4 = environ.get("S2_SP1_IP4", "192.168.12.142")
S1_LE1_IP4 = environ.get("S1_LE1_IP4", "192.168.12.151")
S2_LE1_IP4 = environ.get("S2_LE1_IP4", "192.168.12.152")
S1_LE1_IP4_INTERFACE_2 = environ.get("S1_LE1_IP4_INTERFACE_2", "192.168.0.151")
S2_LE1_IP4_INTERFACE_2 = environ.get("S2_LE1_IP4_INTERFACE_2", "192.168.0.152")

# SITE3 / SITE4
S3_BG1_IP4 = environ.get("S3_BG1_IP4", "192.168.14.131")
S4_BG1_IP4 = environ.get("S4_BG1_IP4", "192.168.14.132")
S3_SP1_IP4 = environ.get("S3_SP1_IP4", "192.168.14.141")
S4_SP1_IP4 = environ.get("S4_SP1_IP4", "192.168.14.142")
S3_LE1_IP4 = environ.get("S3_LE1_IP4", "192.168.14.151")
S4_LE1_IP4 = environ.get("S4_LE1_IP4", "192.168.14.152")
S3_LE1_IP4_INTERFACE_2 = environ.get("S3_LE1_IP4_INTERFACE_2", "192.168.0.151")
S4_LE1_IP4_INTERFACE_2 = environ.get("S4_LE1_IP4_INTERFACE_2", "192.168.0.152")

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

# SITE1 / SITE2
S1_BG1_HOSTNAME = environ.get("S1_BG1_HOSTNAME", "S1_BG1")
S2_BG1_HOSTNAME = environ.get("S2_BG1_HOSTNAME", "S2_BG1")
S1_SP1_HOSTNAME = environ.get("S1_SP1_HOSTNAME", "S1_SP1")
S2_SP1_HOSTNAME = environ.get("S2_SP1_HOSTNAME", "S2_SP1")
S1_LE1_HOSTNAME = environ.get("S1_LE1_HOSTNAME", "S1_LE1")
S2_LE1_HOSTNAME = environ.get("S2_LE1_HOSTNAME", "S2_LE1")

# Links
# Source                  Destination             Bridge
# S1_BG1_INTERFACE_2      S1_SP1_INTERFACE_1      BR_S1_BG1_SP1_1
# S2_BG1_INTERFACE_2      S2_SP1_INTERFACE_1      BR_S2_BG1_SP1_1
# S1_SP1_INTERFACE_2      S1_LE1_INTERFACE_1      BR_S1_SP1_LE1_1
# S2_SP1_INTERFACE_2      S2_LE1_INTERFACE_1      BR_S2_SP1_LE1_1
# S1_LE1_INTERFACE_2      S1_H1_INTERFACE_1       BR_S1_LE1_H1_1
# S2_LE1_INTERFACE_2      S2_H1_INTERFACE_1       BR_S2_LE1_H1_1

# Base set of interfaces
S1_BG1_INTERFACE_1 = environ.get("S1_BG1_INTERFACE_1", "Ethernet1/1")
S1_BG1_INTERFACE_2 = environ.get("S1_BG1_INTERFACE_2", "Ethernet1/2")

S2_BG1_INTERFACE_1 = environ.get("S2_BG1_INTERFACE_1", "Ethernet1/1")
S2_BG1_INTERFACE_2 = environ.get("S2_BG1_INTERFACE_2", "Ethernet1/2")

S1_SP1_INTERFACE_1 = environ.get("S1_SP1_INTERFACE_1", "Ethernet1/1")
S1_SP1_INTERFACE_2 = environ.get("S1_SP1_INTERFACE_2", "Ethernet1/2")

S2_SP1_INTERFACE_1 = environ.get("S2_SP1_INTERFACE_1", "Ethernet1/1")
S2_SP1_INTERFACE_2 = environ.get("S2_SP1_INTERFACE_2", "Ethernet1/2")

S1_LE1_INTERFACE_1 = environ.get("S1_LE1_INTERFACE_1", "Ethernet1/1")
S1_LE1_INTERFACE_2 = environ.get("S1_LE1_INTERFACE_2", "Ethernet1/2")

S2_LE1_INTERFACE_1 = environ.get("S2_LE1_INTERFACE_1", "Ethernet1/1")
S2_LE1_INTERFACE_2 = environ.get("S2_LE1_INTERFACE_2", "Ethernet1/2")

# output is printed to STDOUT, where ansible-playbook -i reads it.
# If you change any vars above, be sure to add them below.

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
            "S1_BG1_IP4": S1_BG1_IP4,
            "S2_BG1_IP4": S2_BG1_IP4,
            "S1_SP1_IP4": S1_SP1_IP4,
            "S2_SP1_IP4": S2_SP1_IP4,
            "S1_LE1_IP4": S1_LE1_IP4,
            "S2_LE1_IP4": S2_LE1_IP4,
            "S1_BG1_HOSTNAME": S1_BG1_HOSTNAME,
            "S2_BG1_HOSTNAME": S2_BG1_HOSTNAME,
            "S1_SP1_HOSTNAME": S1_SP1_HOSTNAME,
            "S2_SP1_HOSTNAME": S2_SP1_HOSTNAME,
            "S1_LE1_HOSTNAME": S1_LE1_HOSTNAME,
            "S2_LE1_HOSTNAME": S2_LE1_HOSTNAME,
            "S1_BG1_INTERFACE_1": S1_BG1_INTERFACE_1,
            "S1_BG1_INTERFACE_2": S1_BG1_INTERFACE_2,
            "S2_BG1_INTERFACE_1": S2_BG1_INTERFACE_1,
            "S2_BG1_INTERFACE_2": S2_BG1_INTERFACE_2,
            "S1_SP1_INTERFACE_1": S1_SP1_INTERFACE_1,
            "S1_SP1_INTERFACE_2": S1_SP1_INTERFACE_2,
            "S2_SP1_INTERFACE_1": S2_SP1_INTERFACE_1,
            "S2_SP1_INTERFACE_2": S2_SP1_INTERFACE_2,
            "S1_LE1_INTERFACE_1": S1_LE1_INTERFACE_1,
            "S1_LE1_INTERFACE_2": S1_LE1_INTERFACE_2,
            "S2_LE1_INTERFACE_1": S2_LE1_INTERFACE_1,
            "S2_LE1_INTERFACE_2": S2_LE1_INTERFACE_2,
            "S1_LE1_IP4_INTERFACE_2": S1_LE1_IP4_INTERFACE_2,
            "S2_LE1_IP4_INTERFACE_2": S2_LE1_IP4_INTERFACE_2,
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
            "S1_BG1",
            "S2_BG1",
            "S1_SP1",
            "S2_SP1",
            "S1_LE1",
            "S2_LE1",
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
