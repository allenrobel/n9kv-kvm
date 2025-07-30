# ND 4.1 Add switches

## Add ER Switch to ISN Fabric

- In the sidebar, click `Manage` -> `Inventory`
- On the `Inventory` page, click `Actions` -> `Add Switches`
- On the `Add Switches` page, click `Choose Fabric`
- In the `Select Fabric` dialog, choose `ISN` and click `Select`
- On the `Add Switches` page
  - `Switch Addition Mechanism` Discover
  - `Seed IP` 192.168.11.111
  - `Device Type` nx-os
  - `Username` admin
  - `Password` The password you assigned to the ER switch
  - `Set as individual device write credential` Enable
  - `Max Hops` 0
  - Click `Discover Switches`
- The ER switch should be displayed in the `Discovery Results` section.
  - Its status should display as `Manageable`
  - Select it and Click `Add Switches`
  - The Progress bar will start to increment and Status will change to `In Progress`
  - After some time, the Status will change to `Switch Added`
  - Click `Close` to exit this screen.
- Back at the Inventory screen, select the ER switch again.
- Click `Actions` and `Set Role`
- In the `Select Role` dialog, scroll down and select Edge Router
- Click `Select`
- Click `OK` in the Warning dialog
- In the left sidebar, click `Manage` and `Fabrics`
- On the `Fabrics` page, click the ISN fabric name (not the radio button, but the actual blue fabric name)
- On the `ISN` page, click the blue `Actions` button, and then select `Recalculate and Deploy`
- On the `Deploy Configuration - ISN` page, click `Deploy All`

## Add S1, S2, and L1 Switches to VXLAN Fabric

- In the sidebar, click `Manage` -> `Inventory`
- On the `Inventory` page, click `Actions` -> `Add Switches`
- On the `Add Switches` page, click `Choose Fabric`
- In the `Select Fabric` dialog, choose `VXLAN` and click `Select`
- On the `Add Switches` page
  - `Switch Addition Mechanism` Discover
  - `Seed IP` 192.168.11.131
  - `Device Type` nx-os
  - `Username` admin
  - `Password` The password you assigned to the S1, S2, and L1 switches
  - `Set as individual device write credential` Enable
  - `Max Hops` 1
    - Since the seed switch is L1, and L1 is connected to S1 and S2, we need a 1 hop discovery radius
  - `Preserve Config` Uncheck/Disable this (important!)
  - Click `Discover Switches`
- The switches should be displayed in the `Discovery Results` section.
  - Their status should display as `Manageable`
  - Select them and Click `Add Switches`
  - The Progress bar will start to increment and Status will change to `In Progress`
  - After some time, the Status will change to `Switch Added`
  - Click `Close` to exit this screen.
- Back at the Inventory screen, select the S1 and S2 switches.
- Click `Actions` and `Set Role`
- In the `Select Role` dialog, select Border Spine
- Click `Select`
- Click `OK` in the Warning dialog
  - The L1 switch is set to Leaf role by default, so we don't need to change its role
- In the left sidebar, click `Manage` and `Fabrics`
- On the `Fabrics` page, click the VXLAN fabric name (not the radio button, but the actual blue fabric name)
- On the `VXLAN` page, click the blue `Actions` button, and then select `Recalculate and Deploy`
- On the `Deploy Configuration - VXLAN` page, click `Deploy All`
