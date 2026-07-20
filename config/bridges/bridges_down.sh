#!/bin/bash

# Tear down SITE1/SITE2 bridges and any associated TAP/VNET interfaces.

BRIDGES=(
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
    BR_S1_SP1_LE3_1
    BR_S1_SP1_LE4_1
    BR_S1_LE3_LE4_1
    BR_S2_LE1_H1_1
    BR_ISN_WAN_S1_1
    BR_ISN_WAN_S2_1
)

# Detach any tap/vnet interfaces still bound to these bridges, then bring the
# bridge down and delete it.
for bridge in "${BRIDGES[@]}"; do
    if ! ip link show "$bridge" >/dev/null 2>&1; then
        echo "Bridge $bridge does not exist, skipping."
        continue
    fi

    SLAVES=$(bridge link show | grep -E "master $bridge\b" | cut -d: -f2 | cut -d' ' -f2 | cut -d'@' -f1)
    for slave in $SLAVES; do
        echo "Detaching $slave from $bridge..."
        ip link set "$slave" nomaster
        ip link set "$slave" down
    done

    echo "Bringing down bridge $bridge..."
    ip link set "$bridge" down
    echo "Deleting bridge $bridge..."
    ip link delete "$bridge"
done

echo "All SITE1/SITE2 bridges torn down successfully"
