#!/usr/bin/env python3
"""
# Summary
Dynamic inventory for n9kv testbed. Inventory is built from environment variables.

## Usage

### Mandatory general variables

The following general environment variables are related
to credentials, controller reachability, and role/testcase
assignment.  These should be considered mandatory; though
the NXOS_* variables are not strictly needed unless called
for by the specific role/testcase.

Values below are examples, and should be modified for your
setup and the roles/testcases you are running.

```bash
export ND_ROLE=dcnm_vrf         # The role to run
export ND_TESTCASE=query        # The testcase to run
export ND_IP4=10.1.1.1          # Controller IPv4 address
export ND_PASSWORD=MyPassword   # Controller password
export ND_USERNAME=admin        # Controller username
export NXOS_PASSWORD=MyPassword # Switch password
export NXOS_USERNAME=admin      # Switch username
```

### Fabrics

We can add more fabrics later as the need arises...

```bash
export ND_FABRIC_1=MyFabric1   # Assigned to var fabric_1
export ND_FABRIC_2=MyFabric2   # Assigned to var fabric_2
export ND_FABRIC_3=MyFabric3   # Assigned to var fabric_3

```

### Interfaces

Interface usage varies by testcase.  See individual
testcase YAML files for details regarding each test's
usage.

#### Interface naming convention

##### Environment variables

ND_INTERFACE_[A][b]

Where:

A - The number of the switch to which the interface belongs
b - An incrementing lower-case letter in range a-z

###### Examples:

```bash
export ND_INTERFACE_1a=Ethernet1/1
export ND_INTERFACE_2a=Ethernet1/1
export ND_INTERFACE_2b=Ethernet1/2
export ND_INTERFACE_3a=Ethernet2/4
```

Above:

- switch_1 has one interface; Ethernet1/1
- switch_2 two interfaces; Ethernet1/1 and Ethernet1/2
- switch_3 has one interface; Ethernet2/4

##### Test case variables

Interface variables within test cases follow the same convention
as above, but are lowercase, and remove the leading ND_.

###### Examples

interface_1a - 1st interface on switch_1
interface_1b - 2st interface on switch_1
etc...
"""
#
# Copyright (c) 2024 Cisco and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import, division, print_function

__metaclass__ = type  # pylint: disable=invalid-name
__copyright__ = "Copyright (c) 2025 Cisco and/or its affiliates."
__author__ = "Allen Robel"

import json
from os import environ

fabric_vxlan = environ.get("ND_FABRIC_VXLAN")
fabric_isn = environ.get("ND_FABRIC_ISN")
nd_ip4 = environ.get("ND_IP4")
nd_password = environ.get("ND_PASSWORD")
nd_username = environ.get("ND_USERNAME", "admin")
nxos_password = environ.get("NXOS_PASSWORD")
nxos_username = environ.get("NXOS_USERNAME", "admin")

# Base set of switches
ER = environ.get("ER_IP4", "192.168.11.111")
S1 = environ.get("S1_IP4", "192.168.11.121")
S2 = environ.get("S2_IP4", "192.168.11.122")
L1 = environ.get("L1_IP4", "192.168.11.131")

# Base set of interfaces
ER_interface_1 = environ.get("ND_INTERFACE_1a", "Ethernet1/1")
ER_interface_2 = environ.get("ND_INTERFACE_1b", "Ethernet1/2")
S1_interface_1 = environ.get("ND_INTERFACE_2a", "Ethernet1/1")
S1_interface_2 = environ.get("ND_INTERFACE_2b", "Ethernet1/2")
S2_interface_1 = environ.get("ND_INTERFACE_3a", "Ethernet1/1")
S2_interface_2 = environ.get("ND_INTERFACE_3b", "Ethernet1/2")
L1_interface_1 = environ.get("ND_INTERFACE_4a", "Ethernet1/1")
L1_interface_2 = environ.get("ND_INTERFACE_4b", "Ethernet1/2")

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
            "ansible_password": nd_password,
            "ansible_python_interpreter": "python",
            "ansible_user": nd_username,
            "fabric_vxlan": fabric_vxlan,
            "fabric_isn": fabric_isn,
            "ER": ER,
            "S1": S1,
            "S2": S2,
            "L1": L1,
            "ER_interface_1": ER_interface_1,
            "ER_interface_2": ER_interface_2,
            "S1_interface_1": S1_interface_1,
            "S1_interface_2": S1_interface_2,
            "S2_interface_1": S2_interface_1,
            "S2_interface_2": S2_interface_2,
            "L1_interface_1": L1_interface_1,
            "L1_interface_2": L1_interface_2,
            "nxos_username": nxos_username,
            "nxos_password": nxos_password,
            "switch_password": nxos_password,
            "switch_username": nxos_username,
        },
    },
    "nd": {
        "hosts": [nd_ip4],
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
