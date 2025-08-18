# ND 4.1 Add switches

## Add BG1, SP1, LE1 Switches to SITE1 Fabric

- In the sidebar, click `Manage` -> `Inventory`
- On the `Inventory` page, click `Actions` -> `Add Switches`
- On the `Add Switches` page, click `Choose Fabric`
- In the `Select Fabric` dialog, choose `SITE1` and click `Select`
- On the `Add Switches` page
  - `Switch Addition Mechanism` Discover
  - `Seed IP` 192.168.12.141
  - `Device Type` nx-os
  - `Username` admin
  - `Password` The password you assigned to the BG1, SP1, LE1 switches
  - `Set as individual device write credential` Enable
  - `Max Hops` 1
    - Since the seed switch is SP1, and SP1 is connected to both BG1 and LE1, a 1 hop discovery radius takes less time than 2 hop
  - `Preserve Config` Uncheck/Disable this (important!)
  - Click `Discover Switches`
- The switches should be displayed in the `Discovery Results` section.
  - Their status should display as `Manageable`
  - Select them and Click `Add Switches`
  - The Progress bar will start to increment and Status will change to `In Progress`
  - After some time, the Status will change to `Switch Added`
  - Click `Close` to exit this screen.
- Back at the Inventory screen
  - Select the BG1 switch.
    - Click `Actions` and `Set Role`
    - In the `Select Role` dialog, select Border Gateway
    - Click `Select`
    - Click `OK` in the Warning dialog
  - Select the SP1 switch.
    - Click `Actions` and `Set Role`
    - In the `Select Role` dialog, select Spine
    - Click `Select`
    - Click `OK` in the Warning dialog
  - Verify that the LE1 switch is set to Leaf role by default.
  - If it's set to something else, change it to Leaf in the same way you changed BG1 and SP1 roles.
- In the left sidebar, click `Manage` and `Fabrics`
- On the `Fabrics` page, double-click the SITE1 fabric name (not the radio button, but the actual blue fabric name)
- On the `SITE1` page, click the blue `Actions` button, and then select `Recalculate and Deploy`
- On the `Deploy Configuration - SITE1` page, click `Deploy All`

## Add S2, L2 Switches to SITE2 Fabric

- In the sidebar, click `Manage` -> `Inventory`
- On the `Inventory` page, click `Actions` -> `Add Switches`
- On the `Add Switches` page, click `Choose Fabric`
- In the `Select Fabric` dialog, choose `SITE2` and click `Select`
- On the `Add Switches` page
  - `Switch Addition Mechanism` Discover
  - `Seed IP` 192.168.11.132
  - `Device Type` nx-os
  - `Username` admin
  - `Password` The password you assigned to the S2, L2 switches
  - `Set as individual device write credential` Enable
  - `Max Hops` 1
    - Since the seed switch is L2, and L2 is connected to S2, a 1 hop discovery radius takes less time than 2 hop
  - `Preserve Config` Uncheck/Disable this (important!)
  - Click `Discover Switches`
- The switches should be displayed in the `Discovery Results` section.
  - Their status should display as `Manageable`
  - Select them and Click `Add Switches`
  - The Progress bar will start to increment and Status will change to `In Progress`
  - After some time, the Status will change to `Switch Added`
  - Click `Close` to exit this screen.
- Back at the Inventory screen
  - Select the BG2 switch.
    - Click `Actions` and `Set Role`
    - In the `Select Role` dialog, select Border Gateway
    - Click `Select`
    - Click `OK` in the Warning dialog
  - Select the SP2 switch.
    - Click `Actions` and `Set Role`
    - In the `Select Role` dialog, select Spine
    - Click `Select`
    - Click `OK` in the Warning dialog
  - Verify that the LE2 switch is set to Leaf role by default.
  - If it's set to something else, change it to Leaf in the same way you changed BG2 and SP2 roles.
- In the left sidebar, click `Manage` and `Fabrics`
- On the `Fabrics` page, double-click the SITE2 fabric name (not the radio button, but the actual blue fabric name)
- On the `SITE2` page, click the blue `Actions` button, and then select `Recalculate and Deploy`
- On the `Deploy Configuration - SITE2` page, click `Deploy All`

## Recalculate and Deploy in the MSD Fabric

TODO Add detailed steps here.  For now, we'll add an overview.

In general, you want to do a Recalculate and Deploy in the following
order when making changes.

1. Child Fabrics (SITE1 and SITE2)
2. MSD Fabric

In our case (initial setting of switch roles) the following happens
with respect to BGP.

- Recalculate and Deploy in SITE1
  - BGP peering is established between LE1 and SP1
  - BGP peering is established between SP1 and BG1
- Recalculate and Deploy in SITE1
  - BGP peering is established between LE2 and SP2
  - BGP peering is established between SP2 and BG2
- Recalculate and Deploy in MSD
  - BGP peering is established between BG1 and BG2
