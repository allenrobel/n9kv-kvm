#!/bin/bash

# show tun links
ip link show type tun

# show bridge links
ip link show type bridge

# specific links (example: SITE1 leaf mgmt TAP, SITE1 spine<->leaf bridge)
ip link show tap_S1_LE1_MGMT
ip link show BR_S1_SP1_LE1_1

# show interface with ip address
ip addr show tap_S1_LE1_MGMT
# or
ip a show tap_S1_LE1_MGMT

# Show which interfaces are attached to a bridge:

ip link show master BR_S1_SP1_LE1_1

# Show bridge details (including forwarding database):

bridge link show

# Show bridge forwarding database:

bridge fdb show

# Show detailed bridge information:

bridge link show dev tap_S1_LE1_E1_1

# List only UP interfaces:

ip link show up

# List only DOWN interfaces:

ip link show | grep -A1 "state DOWN"

# Search for specific interfaces by pattern:

ip link show | grep "tap_S1_LE1"
ip link show | grep "BR_"
