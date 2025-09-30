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

"""
import json
from os import environ

# Try to populate vars from the environment, else use defaults.

# Device IP addresses

ND_IP4 = environ.get("ND_IP4", "192.168.7.7")
ND_IP4_2 = environ.get("ND_IP4_2", "192.168.7.8")

# SITE1 / SITE2
BG1_IP4 = environ.get("BG1_IP4", "192.168.12.131")
BG2_IP4 = environ.get("BG2_IP4", "192.168.12.132")
SP1_IP4 = environ.get("SP1_IP4", "192.168.12.141")
SP2_IP4 = environ.get("SP2_IP4", "192.168.12.142")
LE1_IP4 = environ.get("LE1_IP4", "192.168.12.151")
LE2_IP4 = environ.get("LE2_IP4", "192.168.12.152")
LE1_IP4_INTERFACE_2 = environ.get("LE1_IP4_INTERFACE_2", "192.168.0.1")
LE2_IP4_INTERFACE_2 = environ.get("LE2_IP4_INTERFACE_2", "192.168.0.2")

# SITE3 / SITE4
BG3_IP4 = environ.get("BG3_IP4", "192.168.14.131")
BG4_IP4 = environ.get("BG4_IP4", "192.168.14.132")
SP3_IP4 = environ.get("SP3_IP4", "192.168.14.141")
SP4_IP4 = environ.get("SP4_IP4", "192.168.14.142")
LE3_IP4 = environ.get("LE3_IP4", "192.168.14.151")
LE4_IP4 = environ.get("LE4_IP4", "192.168.14.152")
VP3_IP4 = environ.get("VP3_IP4", "192.168.14.153")
VP4_IP4 = environ.get("VP4_IP4", "192.168.14.154")
LE3_IP4_INTERFACE_2 = environ.get("LE3_IP4_INTERFACE_2", "192.168.0.3")
LE4_IP4_INTERFACE_2 = environ.get("LE4_IP4_INTERFACE_2", "192.168.0.4")

VP3_IP4_INTERFACE_2 = environ.get("VP3_IP4_INTERFACE_2", "192.168.0.5")
VP4_IP4_INTERFACE_2 = environ.get("VP4_IP4_INTERFACE_2", "192.168.0.6")

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
BG1_HOSTNAME = environ.get("BG1_HOSTNAME", "BG1")
BG2_HOSTNAME = environ.get("BG2_HOSTNAME", "BG2")
SP1_HOSTNAME = environ.get("SP1_HOSTNAME", "SP1")
SP2_HOSTNAME = environ.get("SP2_HOSTNAME", "SP2")
LE1_HOSTNAME = environ.get("LE1_HOSTNAME", "LE1")
LE2_HOSTNAME = environ.get("LE2_HOSTNAME", "LE2")

# SITE3 / SITE4
BG3_HOSTNAME = environ.get("BG3_HOSTNAME", "BG3")
BG4_HOSTNAME = environ.get("BG4_HOSTNAME", "BG4")
SP3_HOSTNAME = environ.get("SP3_HOSTNAME", "SP3")
SP4_HOSTNAME = environ.get("SP4_HOSTNAME", "SP4")
LE3_HOSTNAME = environ.get("LE3_HOSTNAME", "LE3")
LE4_HOSTNAME = environ.get("LE4_HOSTNAME", "LE4")
VP3_HOSTNAME = environ.get("VP3_HOSTNAME", "VP3")
VP4_HOSTNAME = environ.get("VP4_HOSTNAME", "VP4")

# Links
# Source             Destination        Bridge
# BG1_INTERFACE_2    SP1_INTERFACE_1    BR_BG1_SP1
# BG2_INTERFACE_2    SP2_INTERFACE_1    BR_BG2_SP2
# SP1_INTERFACE_2    LE1_INTERFACE_1    BR_SP1_LE1
# SP2_INTERFACE_2    LE2_INTERFACE_1    BR_SP2_LE2
# LE1_INTERFACE_2    HO1_INTERFACE_1    BR_LE1_HO1
# LE2_INTERFACE_2    HO2_INTERFACE_1    BR_LE2_HO2

# Base set of interfaces
# SITE1 / SITE2
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
# SITE1 / SITE2
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

# SITE3 / SITE4
BG3_INTERFACE_1 = environ.get("BG3_INTERFACE_1", "Ethernet1/1")
BG3_INTERFACE_2 = environ.get("BG3_INTERFACE_2", "Ethernet1/2")

BG4_INTERFACE_1 = environ.get("BG4_INTERFACE_1", "Ethernet1/1")
BG4_INTERFACE_2 = environ.get("BG4_INTERFACE_2", "Ethernet1/2")

SP3_INTERFACE_1 = environ.get("SP3_INTERFACE_1", "Ethernet1/1")
SP3_INTERFACE_2 = environ.get("SP3_INTERFACE_2", "Ethernet1/2")

SP4_INTERFACE_1 = environ.get("SP4_INTERFACE_1", "Ethernet1/1")
SP4_INTERFACE_2 = environ.get("SP4_INTERFACE_2", "Ethernet1/2")
SP4_INTERFACE_3 = environ.get("SP4_INTERFACE_3", "Ethernet1/3")
SP4_INTERFACE_4 = environ.get("SP4_INTERFACE_4", "Ethernet1/4")

LE3_INTERFACE_1 = environ.get("LE3_INTERFACE_1", "Ethernet1/1")
LE3_INTERFACE_2 = environ.get("LE3_INTERFACE_2", "Ethernet1/2")

LE4_INTERFACE_1 = environ.get("LE4_INTERFACE_1", "Ethernet1/1")
LE4_INTERFACE_2 = environ.get("LE4_INTERFACE_2", "Ethernet1/2")

VP3_INTERFACE_1 = environ.get("VP3_INTERFACE_1", "Ethernet1/1")
VP3_INTERFACE_2 = environ.get("VP3_INTERFACE_2", "Ethernet1/2")

VP4_INTERFACE_1 = environ.get("VP4_INTERFACE_1", "Ethernet1/1")
VP4_INTERFACE_2 = environ.get("VP4_INTERFACE_2", "Ethernet1/2")

# SITE3 / SITE4
BG3_MAC_1 = environ.get("BG3_MAC_1", "0000.0033.0001")
BG3_MAC_2 = environ.get("BG3_MAC_2", "0000.0033.0002")

BG4_MAC_1 = environ.get("BG4_MAC_1", "0000.0034.0001")
BG4_MAC_2 = environ.get("BG4_MAC_2", "0000.0034.0002")

SP3_MAC_1 = environ.get("SP3_MAC_1", "0000.0043.0001")
SP3_MAC_2 = environ.get("SP3_MAC_2", "0000.0043.0002")

SP4_MAC_1 = environ.get("SP4_MAC_1", "0000.0044.0001")
SP4_MAC_2 = environ.get("SP4_MAC_2", "0000.0044.0002")
SP4_MAC_3 = environ.get("SP4_MAC_3", "0000.0044.0003")
SP4_MAC_4 = environ.get("SP4_MAC_4", "0000.0044.0004")

LE3_MAC_1 = environ.get("LE3_MAC_1", "0000.0053.0001")
LE3_MAC_2 = environ.get("LE3_MAC_2", "0000.0053.0002")

LE4_MAC_1 = environ.get("LE4_MAC_1", "0000.0054.0001")
LE4_MAC_2 = environ.get("LE4_MAC_2", "0000.0054.0002")

VP3_MAC_1 = environ.get("VP3_MAC_1", "0000.0063.0001")
VP3_MAC_2 = environ.get("VP3_MAC_2", "0000.0063.0002")

VP4_MAC_1 = environ.get("VP4_MAC_1", "0000.0064.0001")
VP4_MAC_2 = environ.get("VP4_MAC_2", "0000.0064.0002")

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
            "BG1_IP4": BG1_IP4,
            "BG2_IP4": BG2_IP4,
            "SP1_IP4": SP1_IP4,
            "SP2_IP4": SP2_IP4,
            "LE1_IP4": LE1_IP4,
            "LE2_IP4": LE2_IP4,
            "BG3_IP4": BG3_IP4,
            "BG4_IP4": BG4_IP4,
            "SP3_IP4": SP3_IP4,
            "SP4_IP4": SP4_IP4,
            "LE3_IP4": LE3_IP4,
            "LE4_IP4": LE4_IP4,
            "VP3_IP4": VP3_IP4,
            "VP4_IP4": VP4_IP4,
            "BG1_HOSTNAME": BG1_HOSTNAME,
            "BG2_HOSTNAME": BG2_HOSTNAME,
            "SP1_HOSTNAME": SP1_HOSTNAME,
            "SP2_HOSTNAME": SP2_HOSTNAME,
            "LE1_HOSTNAME": LE1_HOSTNAME,
            "LE2_HOSTNAME": LE2_HOSTNAME,
            "BG3_HOSTNAME": BG3_HOSTNAME,
            "BG4_HOSTNAME": BG4_HOSTNAME,
            "SP3_HOSTNAME": SP3_HOSTNAME,
            "SP4_HOSTNAME": SP4_HOSTNAME,
            "LE3_HOSTNAME": LE3_HOSTNAME,
            "LE4_HOSTNAME": LE4_HOSTNAME,
            "VP3_HOSTNAME": VP3_HOSTNAME,
            "VP4_HOSTNAME": VP4_HOSTNAME,
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
            "BG3_MAC_1": BG3_MAC_1,
            "BG3_MAC_2": BG3_MAC_2,
            "BG4_MAC_1": BG4_MAC_1,
            "BG4_MAC_2": BG4_MAC_2,
            "SP3_MAC_1": SP3_MAC_1,
            "SP3_MAC_2": SP3_MAC_2,
            "SP4_MAC_1": SP4_MAC_1,
            "SP4_MAC_2": SP4_MAC_2,
            "SP4_MAC_3": SP4_MAC_3,
            "SP4_MAC_4": SP4_MAC_4,
            "LE3_MAC_1": LE3_MAC_1,
            "LE3_MAC_2": LE3_MAC_2,
            "LE4_MAC_1": LE4_MAC_1,
            "LE4_MAC_2": LE4_MAC_2,
            "VP3_MAC_1": VP3_MAC_1,
            "VP3_MAC_2": VP3_MAC_2,
            "VP4_MAC_1": VP4_MAC_1,
            "VP4_MAC_2": VP4_MAC_2,
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
            "BG3_INTERFACE_1": BG3_INTERFACE_1,
            "BG3_INTERFACE_2": BG3_INTERFACE_2,
            "BG4_INTERFACE_1": BG4_INTERFACE_1,
            "BG4_INTERFACE_2": BG4_INTERFACE_2,
            "SP3_INTERFACE_1": SP3_INTERFACE_1,
            "SP3_INTERFACE_2": SP3_INTERFACE_2,
            "SP4_INTERFACE_1": SP4_INTERFACE_1,
            "SP4_INTERFACE_2": SP4_INTERFACE_2,
            "SP4_INTERFACE_3": SP4_INTERFACE_3,
            "SP4_INTERFACE_4": SP4_INTERFACE_4,
            "LE3_INTERFACE_1": LE3_INTERFACE_1,
            "LE3_INTERFACE_2": LE3_INTERFACE_2,
            "LE4_INTERFACE_1": LE4_INTERFACE_1,
            "LE4_INTERFACE_2": LE4_INTERFACE_2,
            "LE3_IP4_INTERFACE_2": LE3_IP4_INTERFACE_2,
            "LE4_IP4_INTERFACE_2": LE4_IP4_INTERFACE_2,
            "VP3_INTERFACE_1": VP3_INTERFACE_1,
            "VP3_INTERFACE_2": VP3_INTERFACE_2,
            "VP4_INTERFACE_1": VP4_INTERFACE_1,
            "VP4_INTERFACE_2": VP4_INTERFACE_2,
            "VP3_IP4_INTERFACE_2": VP3_IP4_INTERFACE_2,
            "VP4_IP4_INTERFACE_2": VP4_IP4_INTERFACE_2,
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
            "BG1",
            "BG2",
            "BG3",
            "BG4",
            "SP1",
            "SP2",
            "SP3",
            "SP4",
            "LE1",
            "LE2",
            "LE3",
            "LE4",
            "VP3",
            "VP4",
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
