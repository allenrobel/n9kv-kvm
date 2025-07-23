#!/bin/bash

BRIDGES=(BR_ER_S1 BR_ER_S2 BR_S1_L1 BR_S2_L1)
for bridge in "${BRIDGES[@]}"; do
    if ! ip link show $bridge >/dev/null 2>&1; then
        echo "Bridge $bridge does not exist. Creating..."
        ip link add name $bridge type bridge stp_state 0
    else
        echo "Bridge $bridge already exists."
    fi
done
