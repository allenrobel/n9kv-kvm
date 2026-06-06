#!/bin/bash
# Ensures the Open vSwitch bridges for the Nexus 9000v environment exist and are
# configured to forward reserved-multicast control frames (LACP / STP / LLDP /
# CDP). Without other-config:forward-bpdu=true, OVS silently drops the
# 01:80:c2:00:00:0x range and LACP peer-links never bundle.
#
# Bridges are normally created by netplan (see 9912-bridges.yaml); this script
# is idempotent, re-asserts the settings, and will create any missing bridge so
# that bridges with no VM attached yet are still correct at boot.
#
# TAP interfaces are NOT handled here -- nexus9000v.py creates each TAP and
# attaches it to its bridge at VM launch (and re-asserts forward-bpdu then too).
#
# This script should be run with root privileges.
# Usage: sudo ./bridges_config.sh

set -euo pipefail

MTU=9216

# SITE1/SITE2 bridges (canonical, from 9912-bridges.yaml).
BRIDGES=(
    BR_ND_DATA_12
    BR_ISN_S1_S2_1
    BR_S1_BG1_SP1_1
    BR_S2_BG1_SP1_1
    BR_S1_SP1_LE1_1
    BR_S1_SP1_LE2_1
    BR_S2_SP1_LE1_1
    BR_S1_LE1_LE2_1
    BR_S1_LE1_H1_1
    BR_S1_LE1_T1_1
    BR_S1_LE2_T1_1
    BR_S2_LE1_H1_1
)

if [[ $EUID -ne 0 ]]; then
    echo "Error: must be run as root (use sudo)." >&2
    exit 1
fi

if ! command -v ovs-vsctl >/dev/null 2>&1; then
    echo "Error: ovs-vsctl not found. Install with: sudo apt install openvswitch-switch" >&2
    exit 1
fi

for bridge in "${BRIDGES[@]}"; do
    # Create the OVS bridge if netplan hasn't already (br-exists: 0=present, 2=absent).
    if ovs-vsctl br-exists "$bridge"; then
        echo "OVS bridge $bridge already exists."
    else
        echo "OVS bridge $bridge does not exist. Creating..."
        ovs-vsctl add-br "$bridge"
    fi

    echo "Configuring bridge $bridge..."
    # Forward LACP/STP/LLDP/CDP (01:80:c2:00:00:0x) instead of treating them as control frames.
    ovs-vsctl set bridge "$bridge" other-config:forward-bpdu=true
    # Keep the internal port at jumbo MTU to match the n9kv TAP ports.
    ovs-vsctl set int "$bridge" mtu_request="$MTU"

    echo "Bringing up bridge $bridge..."
    ip link set "$bridge" up
done

echo "Done. forward-bpdu=true set on ${#BRIDGES[@]} bridge(s)."

