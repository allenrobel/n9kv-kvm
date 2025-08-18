# Add Switches to Fabrics ND 3.2

NOTE: This section is out of date!

## 9. Inventory Screen (SITE1 Fabric Switches)

- Click `Add Switches`

![Wait](./images/nd3/add_switches/08_inventory.png)

## 10. Pick a Fabric Screen (SITE1 Fabric switches)

- Click `Choose Fabric`

![Pick a Fabric](./images/nd3/add_switches/09_pick_a_fabric.png)

## 11. Select Fabric Screen (SITE1 Fabric switches)

- Select the SITE1 fabric
- Click `Select`

![Select Fabric](./images/nd3/add_switches/10_select_fabric.png)

## 12. Seed Switch Details Screen (SITE1 Fabric switches)

- `Seed IP` 192.168.12.141
- `Username` admin
- `Password` whatever you set when bringup up the nexus9000v switches
- `Max Hops` 1 (default of 2 will work, but 1 reduces the discovery time`
- `Set as individual device write credential` Enable
- `Preserve Config` disable (important!!!)
- Click `Discover Switches`

![Seed Switch Details](./images/nd3/add_switches/11_seed_switch_details.png)

## 13. Warning Dialog

- Click `Confirm`

![Warning Dialog](./images/nd3/add_switches/12_warning_dialog.png)

## 14. Discovery Results Screen

- Select switches (BG1, SP1, LE1)
- Click `Add Switches`

![Discovery Results](./images/nd3/add_switches/13_discovery_results.png)

The switches will be rebooted.

![Discovery Results](./images/nd3/add_switches/14_switches_reboot.png)

## 15. Wait

- Wait for the switches to be added.
- Click `Close`

![Wait](./images/nd3/add_switches/15_wait_for_switch_added.png)

## 16. Inventory Screen (SITE2 Fabric Switches)

- Click `Add Switches`

![Add Switches](./images/nd3/add_switches/16_add_switches.png)

## 17. Pick a Fabric Screen (SITE2 switches)

- Click `Choose Fabric`

![Choose Fabric](./images/nd3/add_switches/17_pick_a_fabric.png)

## 18. Select Fabric Screen (SITE2 switches)

- Select the SITE2 fabric
- Click `Select`

![Choose Fabric](./images/nd3/add_switches/18_select_fabric.png)

## 19. Seed Switch Details Screen (SITE2 switches)

- `Seed IP` 192.168.12.142
- `Username` admin
- `Password` whatever you set when bringing up the nexus9000v switches
- `Max Hops` 1 (default of 2 will work, but 1 reduces the discovery time`
- `Set as individual device write credential` Enable
- `Preserve Config` disable (important!!!)
- Click `Discover Switches`

![Seed Switch Details](./images/nd3/add_switches/19_seed_switch_details.png)

## 20. Warning Dialog (SITE2 switches)

- Click `Confirm`

![Warning Dialog](./images/nd3/add_switches/20_warning.png)

## 21. Discovery Results Screen (SITE2 switches)

- Select switches (BG2, SP2, LE2)
- Click `Add Switches`

![Discovery Results](./images/nd3/add_switches/21_discovery_results.png)

The switches will be rebooted.

![Switches Reboot](./images/nd3/add_switches/22_switches_reboot.png)

- Wait for the switches to be added.
- Click `Close`

![Wait](./images/nd3/add_switches/23_wait_for_switch_added.png)

## 22. Wait for Discovery Column to display OK for all switches

It will take time (15-30 minutes) for the switches to finish rebooting.

Click Refresh occasionally to avoid being logged out due to inactivity.

Once all switches display OK, we can continue.

![Wait](./images/nd3/add_switches/24_wait_for_discovery_ok.png)

## 23. Change Switch Roles

We'll now change the roles of the switches.

- BG1 (Border Gateway)
- BG2 (Border Gateway)
- SP1 (Spine)
- SP2 (Spine)
- LE1 (Leaf)
- LE2 (Leaf)

## 24. Border Gateway Switch Role

- Select the BG1 and BG2 switches
- Click Actions -> Set Role

## 25. Select Role Dialog (Border Gateway Switches)

- Select `Border Gateway`
- Click `Select`

## 26. Border Spine Switch Role

- Select the SP1 and SP2 switches
- Click Actions -> Set Role

## 27 Select Role Dialog (Spine Switches)

- Select `Spine`
- Click `Select`

## 28. Warning Dialog (Spine Switches)

- Read and acknowledge the warning.  Click `OK`
- We will Recalculate and Deploy later.

![Select Role](./images/nd3/add_switches/30_warning.png)

## 29. Leaf Switch Role

- Select the LE1, LE2 switches
- Click Actions -> Set Role

![Set Role](./images/nd3/add_switches/31_set_role.png)

## 30. Select Role Dialog (Leaf Switches)

- Select `Leaf`
- Click `Select`

![Select Role](./images/nd3/add_switches/32_select_role.png)

## 31. Warning Dialog (Leaf Switches)

- Read and acknowledge the warning.  Click `OK`
- We will Recalculate and Deploy later.

![Warning](./images/nd3/add_switches/33_warning.png)

## 32. Wait (for reachability)

Wait for all switches to become reachable (Discovery Status column will display `OK`).

This will take time (15-30 minutes) as the BG1, BG2, SP1, SP2, LE1, LE2 switches reboot.

Click `Refresh` occasionally to avoid being logged out due to inactivity...

![Wait](./images/nd3/add_switches/34_wait.png)

## 33. All Switches Are Ready

NOTE: image is out of date...

![All Switches Ready](./images/nd3/add_switches/35_all_switches_ready.png)

## 34. Manage Fabrics

- Click `Manage -> Fabrics`

## 35. SITE1 Fabric

- In the Fabric Name column, double-click the blue `SITE1` name

![VXLAN Fabric](./images/nd3/add_switches/37_site1_fabric.png)

## 36. Recalculate and Deploy - SITE1

- Click the blue Actions dropdown and select `Recalculate and Deploy`

![Recalculate and Deploy](./images/nd3/add_switches/38_recalculate_and_deploy.png)

## 37. Wait for switch configs to be built

![Wait](./images/nd3/add_switches/39_wait.png)

## 38. Deploy Configuration - SITE1

- Click `Deploy All`

![Deploy Configuration](./images/nd3/add_switches/40_deploy.png)

## 39. Wait

- Wait for the deployment to finish

![Wait](./images/nd3/add_switches/41_wait.png)

## 40. Ignore Error on Switch consoles

On the switch consoles, during deployment, you'll see the following, which you can ignore.

```bash
2025 Aug  2 03:25:39 L1 %$ VDC-1 %$ nve[28908]: 'feature nve overlay' requires 'application leaf engine' (ALE) 1 or above based line cards. Please consult documentation
```

- Click `Close`

![Wait](./images/nd3/add_switches/42_close.png)

## 41. Fabric Overview - SITE1 (close the window)

- Click the `X` at the upper-right of the winder to close it.

![Wait](./images/nd3/add_switches/43_close_window.png)

## Fabrics (SITE2)

Perform steps 34-41 for the SITE2 fabric.

## Recalculate and Deploy

Perform a Recalculate and Deploy in the fabrics in the following order.

- SITE1
  - This establishes BGP peering between
    - BG1 and SP1
    - SP1 and LE1
- SITE2
  - This establishes BGP peering between
    - BG2 and SP2
    - SP2 and LE2
- MSD
  - This establishes BGP peering between
    - BG1 and BG2
