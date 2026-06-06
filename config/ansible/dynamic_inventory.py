#!/usr/bin/env python3
"""
# Summary
Dynamic inventory for n9kv testbed. Inventory is built from environment
variables.

## Usage Example

Generate startup configurations and .iso files

```bash
cd $HOME/repos/n9kv-kvm/config/ansible
ansible-playbook \
        startup_config_iso.yaml \
        -i $HOME/repos/n9kv-kvm/config/ansible/dynamic_inventory.py
```

### Environment Variables

This inventory script uses a combination of environment variables
and locally-set variables to define the testbed configuration.

It first tries to read the variables from the environment,
and if not set, it uses the defaults defined in this script.

### Naming convention

Hostnames and env var prefixes follow `S<site>_<role><idx>` (per-site
renumbering from 1). For example, the leaf in SITE1 is `S1_LE1`; the
border gateway in SITE4 is `S4_BG1`.

"""
import json
from os import environ

# Try to populate vars from the environment, else use defaults.

# Device IP addresses

ND_IP4 = environ.get("ND_IP4", "192.168.7.7")
ND_IP4_2 = environ.get("ND_IP4_2", "192.168.7.8")

# SITE1 / SITE2
S1_BG1_IP4 = environ.get("S1_BG1_IP4", "192.168.12.131")
S2_BG1_IP4 = environ.get("S2_BG1_IP4", "192.168.12.132")
S1_SP1_IP4 = environ.get("S1_SP1_IP4", "192.168.12.141")
S2_SP1_IP4 = environ.get("S2_SP1_IP4", "192.168.12.142")
S1_LE1_IP4 = environ.get("S1_LE1_IP4", "192.168.12.151")
S1_LE2_IP4 = environ.get("S1_LE2_IP4", "192.168.12.152")
S1_TOR1_IP4 = environ.get("S1_TOR1_IP4", "192.168.12.161")
S1_LE1_IP4_INTERFACE_2 = environ.get("S1_LE1_IP4_INTERFACE_2", "192.168.0.1")
S2_LE1_IP4 = environ.get("S2_LE1_IP4", "192.168.12.153")
S2_LE1_IP4_INTERFACE_2 = environ.get("S2_LE1_IP4_INTERFACE_2", "192.168.0.2")

# SITE3 / SITE4
S3_BG1_IP4 = environ.get("S3_BG1_IP4", "192.168.14.131")
S4_BG1_IP4 = environ.get("S4_BG1_IP4", "192.168.14.132")
S3_SP1_IP4 = environ.get("S3_SP1_IP4", "192.168.14.141")
S4_SP1_IP4 = environ.get("S4_SP1_IP4", "192.168.14.142")
S3_LE1_IP4 = environ.get("S3_LE1_IP4", "192.168.14.151")
S4_LE1_IP4 = environ.get("S4_LE1_IP4", "192.168.14.152")
S4_LE2_IP4 = environ.get("S4_LE2_IP4", "192.168.14.153")
S4_LE3_IP4 = environ.get("S4_LE3_IP4", "192.168.14.154")
S3_LE1_IP4_INTERFACE_2 = environ.get("S3_LE1_IP4_INTERFACE_2", "192.168.0.3")
S4_LE1_IP4_INTERFACE_2 = environ.get("S4_LE1_IP4_INTERFACE_2", "192.168.0.4")

S4_LE2_IP4_INTERFACE_2 = environ.get("S4_LE2_IP4_INTERFACE_2", "192.168.0.5")
S4_LE3_IP4_INTERFACE_2 = environ.get("S4_LE3_IP4_INTERFACE_2", "192.168.0.6")

# Fabric types
SITE1_FABRIC = environ.get("ND_SITE1_FABRIC", "SITE1")
SITE2_FABRIC = environ.get("ND_SITE2_FABRIC", "SITE2")
SITE3_FABRIC = environ.get("ND_SITE3_FABRIC", "SITE3")
SITE4_FABRIC = environ.get("ND_SITE4_FABRIC", "SITE4")
ISN_FABRIC = environ.get("ND_ISN_FABRIC", "ISN")
MSD_FABRIC = environ.get("ND_MSD_FABRIC", "MSD")

# Device credentials
ND_PASSWORD = environ.get("ND_PASSWORD", "SuperSecretPassword")
ND_USERNAME = environ.get("ND_USERNAME", "admin")
NXOS_PASSWORD = environ.get("NXOS_PASSWORD", "SuperSecretPassword")
NXOS_USERNAME = environ.get("NXOS_USERNAME", "admin")

# Switch hostnames
# BG = Border Gateway
# SP = Spine
# LE = Leaf

# SITE1 / SITE2
S1_BG1_HOSTNAME = environ.get("S1_BG1_HOSTNAME", "S1_BG1")
S2_BG1_HOSTNAME = environ.get("S2_BG1_HOSTNAME", "S2_BG1")
S1_SP1_HOSTNAME = environ.get("S1_SP1_HOSTNAME", "S1_SP1")
S2_SP1_HOSTNAME = environ.get("S2_SP1_HOSTNAME", "S2_SP1")
S1_LE1_HOSTNAME = environ.get("S1_LE1_HOSTNAME", "S1_LE1")
S2_LE1_HOSTNAME = environ.get("S2_LE1_HOSTNAME", "S2_LE1")
S1_LE2_HOSTNAME = environ.get("S1_LE2_HOSTNAME", "S1_LE2")
S1_TOR1_HOSTNAME = environ.get("S1_TOR1_HOSTNAME", "S1_TOR1")

# SITE3 / SITE4
S3_BG1_HOSTNAME = environ.get("S3_BG1_HOSTNAME", "S3_BG1")
S4_BG1_HOSTNAME = environ.get("S4_BG1_HOSTNAME", "S4_BG1")
S3_SP1_HOSTNAME = environ.get("S3_SP1_HOSTNAME", "S3_SP1")
S4_SP1_HOSTNAME = environ.get("S4_SP1_HOSTNAME", "S4_SP1")
S3_LE1_HOSTNAME = environ.get("S3_LE1_HOSTNAME", "S3_LE1")
S4_LE1_HOSTNAME = environ.get("S4_LE1_HOSTNAME", "S4_LE1")
S4_LE2_HOSTNAME = environ.get("S4_LE2_HOSTNAME", "S4_LE2")
S4_LE3_HOSTNAME = environ.get("S4_LE3_HOSTNAME", "S4_LE3")

# Links
# Source                  Destination             Bridge
# S1_BG1_INTERFACE_2      S1_SP1_INTERFACE_1      BR_S1_BG1_SP1_1
# S2_BG1_INTERFACE_2      S2_SP1_INTERFACE_1      BR_S2_BG1_SP1_1
# S1_SP1_INTERFACE_2      S1_LE1_INTERFACE_1      BR_S1_SP1_LE1_1
# S2_SP1_INTERFACE_2      S2_LE1_INTERFACE_1      BR_S2_SP1_LE1_1
# S1_LE1_INTERFACE_2      S1_H1_INTERFACE_1       BR_S1_LE1_H1_1
# S2_LE1_INTERFACE_2      S2_H1_INTERFACE_1       BR_S2_LE1_H1_1

# Base set of interfaces
# SITE1 / SITE2
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

# S1_LE2 has 3 ISLs (spine, VPC peer-link to S1_LE1, downlink to S1_TOR1).
# S1_LE1 grows to 4 ISLs (spine, host, VPC peer-link, downlink to S1_TOR1).
S1_LE1_INTERFACE_3 = environ.get("S1_LE1_INTERFACE_3", "Ethernet1/3")
S1_LE1_INTERFACE_4 = environ.get("S1_LE1_INTERFACE_4", "Ethernet1/4")
S1_LE2_INTERFACE_1 = environ.get("S1_LE2_INTERFACE_1", "Ethernet1/1")
S1_LE2_INTERFACE_2 = environ.get("S1_LE2_INTERFACE_2", "Ethernet1/2")
S1_LE2_INTERFACE_3 = environ.get("S1_LE2_INTERFACE_3", "Ethernet1/3")
S1_TOR1_INTERFACE_1 = environ.get("S1_TOR1_INTERFACE_1", "Ethernet1/1")
S1_TOR1_INTERFACE_2 = environ.get("S1_TOR1_INTERFACE_2", "Ethernet1/2")
S1_SP1_INTERFACE_3 = environ.get("S1_SP1_INTERFACE_3", "Ethernet1/3")

# SITE3 / SITE4
S3_BG1_INTERFACE_1 = environ.get("S3_BG1_INTERFACE_1", "Ethernet1/1")
S3_BG1_INTERFACE_2 = environ.get("S3_BG1_INTERFACE_2", "Ethernet1/2")

S4_BG1_INTERFACE_1 = environ.get("S4_BG1_INTERFACE_1", "Ethernet1/1")
S4_BG1_INTERFACE_2 = environ.get("S4_BG1_INTERFACE_2", "Ethernet1/2")

S3_SP1_INTERFACE_1 = environ.get("S3_SP1_INTERFACE_1", "Ethernet1/1")
S3_SP1_INTERFACE_2 = environ.get("S3_SP1_INTERFACE_2", "Ethernet1/2")

S4_SP1_INTERFACE_1 = environ.get("S4_SP1_INTERFACE_1", "Ethernet1/1")
S4_SP1_INTERFACE_2 = environ.get("S4_SP1_INTERFACE_2", "Ethernet1/2")
S4_SP1_INTERFACE_3 = environ.get("S4_SP1_INTERFACE_3", "Ethernet1/3")
S4_SP1_INTERFACE_4 = environ.get("S4_SP1_INTERFACE_4", "Ethernet1/4")

S3_LE1_INTERFACE_1 = environ.get("S3_LE1_INTERFACE_1", "Ethernet1/1")
S3_LE1_INTERFACE_2 = environ.get("S3_LE1_INTERFACE_2", "Ethernet1/2")

S4_LE1_INTERFACE_1 = environ.get("S4_LE1_INTERFACE_1", "Ethernet1/1")
S4_LE1_INTERFACE_2 = environ.get("S4_LE1_INTERFACE_2", "Ethernet1/2")

S4_LE2_INTERFACE_1 = environ.get("S4_LE2_INTERFACE_1", "Ethernet1/1")
S4_LE2_INTERFACE_2 = environ.get("S4_LE2_INTERFACE_2", "Ethernet1/2")

S4_LE3_INTERFACE_1 = environ.get("S4_LE3_INTERFACE_1", "Ethernet1/1")
S4_LE3_INTERFACE_2 = environ.get("S4_LE3_INTERFACE_2", "Ethernet1/2")

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
            "ND_IP4_2": ND_IP4_2,
            "S1_BG1_IP4": S1_BG1_IP4,
            "S2_BG1_IP4": S2_BG1_IP4,
            "S1_SP1_IP4": S1_SP1_IP4,
            "S2_SP1_IP4": S2_SP1_IP4,
            "S1_LE1_IP4": S1_LE1_IP4,
            "S2_LE1_IP4": S2_LE1_IP4,
            "S1_LE2_IP4": S1_LE2_IP4,
            "S1_TOR1_IP4": S1_TOR1_IP4,
            "S3_BG1_IP4": S3_BG1_IP4,
            "S4_BG1_IP4": S4_BG1_IP4,
            "S3_SP1_IP4": S3_SP1_IP4,
            "S4_SP1_IP4": S4_SP1_IP4,
            "S3_LE1_IP4": S3_LE1_IP4,
            "S4_LE1_IP4": S4_LE1_IP4,
            "S4_LE2_IP4": S4_LE2_IP4,
            "S4_LE3_IP4": S4_LE3_IP4,
            "S1_BG1_HOSTNAME": S1_BG1_HOSTNAME,
            "S2_BG1_HOSTNAME": S2_BG1_HOSTNAME,
            "S1_SP1_HOSTNAME": S1_SP1_HOSTNAME,
            "S2_SP1_HOSTNAME": S2_SP1_HOSTNAME,
            "S1_LE1_HOSTNAME": S1_LE1_HOSTNAME,
            "S2_LE1_HOSTNAME": S2_LE1_HOSTNAME,
            "S1_LE2_HOSTNAME": S1_LE2_HOSTNAME,
            "S1_TOR1_HOSTNAME": S1_TOR1_HOSTNAME,
            "S3_BG1_HOSTNAME": S3_BG1_HOSTNAME,
            "S4_BG1_HOSTNAME": S4_BG1_HOSTNAME,
            "S3_SP1_HOSTNAME": S3_SP1_HOSTNAME,
            "S4_SP1_HOSTNAME": S4_SP1_HOSTNAME,
            "S3_LE1_HOSTNAME": S3_LE1_HOSTNAME,
            "S4_LE1_HOSTNAME": S4_LE1_HOSTNAME,
            "S4_LE2_HOSTNAME": S4_LE2_HOSTNAME,
            "S4_LE3_HOSTNAME": S4_LE3_HOSTNAME,
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
            "S1_LE1_INTERFACE_3": S1_LE1_INTERFACE_3,
            "S1_LE1_INTERFACE_4": S1_LE1_INTERFACE_4,
            "S1_LE2_INTERFACE_1": S1_LE2_INTERFACE_1,
            "S1_LE2_INTERFACE_2": S1_LE2_INTERFACE_2,
            "S1_LE2_INTERFACE_3": S1_LE2_INTERFACE_3,
            "S1_TOR1_INTERFACE_1": S1_TOR1_INTERFACE_1,
            "S1_TOR1_INTERFACE_2": S1_TOR1_INTERFACE_2,
            "S1_SP1_INTERFACE_3": S1_SP1_INTERFACE_3,
            "S1_LE1_IP4_INTERFACE_2": S1_LE1_IP4_INTERFACE_2,
            "S2_LE1_IP4_INTERFACE_2": S2_LE1_IP4_INTERFACE_2,
            "S3_BG1_INTERFACE_1": S3_BG1_INTERFACE_1,
            "S3_BG1_INTERFACE_2": S3_BG1_INTERFACE_2,
            "S4_BG1_INTERFACE_1": S4_BG1_INTERFACE_1,
            "S4_BG1_INTERFACE_2": S4_BG1_INTERFACE_2,
            "S3_SP1_INTERFACE_1": S3_SP1_INTERFACE_1,
            "S3_SP1_INTERFACE_2": S3_SP1_INTERFACE_2,
            "S4_SP1_INTERFACE_1": S4_SP1_INTERFACE_1,
            "S4_SP1_INTERFACE_2": S4_SP1_INTERFACE_2,
            "S4_SP1_INTERFACE_3": S4_SP1_INTERFACE_3,
            "S4_SP1_INTERFACE_4": S4_SP1_INTERFACE_4,
            "S3_LE1_INTERFACE_1": S3_LE1_INTERFACE_1,
            "S3_LE1_INTERFACE_2": S3_LE1_INTERFACE_2,
            "S4_LE1_INTERFACE_1": S4_LE1_INTERFACE_1,
            "S4_LE1_INTERFACE_2": S4_LE1_INTERFACE_2,
            "S3_LE1_IP4_INTERFACE_2": S3_LE1_IP4_INTERFACE_2,
            "S4_LE1_IP4_INTERFACE_2": S4_LE1_IP4_INTERFACE_2,
            "S4_LE2_INTERFACE_1": S4_LE2_INTERFACE_1,
            "S4_LE2_INTERFACE_2": S4_LE2_INTERFACE_2,
            "S4_LE3_INTERFACE_1": S4_LE3_INTERFACE_1,
            "S4_LE3_INTERFACE_2": S4_LE3_INTERFACE_2,
            "S4_LE2_IP4_INTERFACE_2": S4_LE2_IP4_INTERFACE_2,
            "S4_LE3_IP4_INTERFACE_2": S4_LE3_IP4_INTERFACE_2,
            "ND_PASSWORD": ND_PASSWORD,
            "ND_USERNAME": ND_USERNAME,
            "NXOS_USERNAME": NXOS_USERNAME,
            "NXOS_PASSWORD": NXOS_PASSWORD,
            "SWITCH_PASSWORD": NXOS_PASSWORD,
            "SWITCH_USERNAME": NXOS_USERNAME,
        },
    },
    "nd1": {
        "hosts": [ND_IP4],
        "vars": {
            "ansible_connection": "ansible.netcommon.httpapi",
            "ansible_network_os": "cisco.dcnm.dcnm",
        },
    },
    "nd2": {
        "hosts": [ND_IP4_2],
        "vars": {
            "ansible_connection": "ansible.netcommon.httpapi",
            "ansible_network_os": "cisco.dcnm.dcnm",
        },
    },
    "nxos": {
        "children": [
            "S1_BG1",
            "S2_BG1",
            "S3_BG1",
            "S4_BG1",
            "S1_SP1",
            "S2_SP1",
            "S3_SP1",
            "S4_SP1",
            "S1_LE1",
            "S2_LE1",
            "S3_LE1",
            "S4_LE1",
            "S4_LE2",
            "S4_LE3",
            "S1_LE2",
            "S1_TOR1",
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
