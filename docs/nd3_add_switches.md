# Add Switches to Fabrics ND 3.2

## 1. Add ER Switch to ISN Fabric

We'll first add the ER switch to the ISN fabric.

## 2. Select Inventory Screen (ER switch)

Click `Manage -> Inventory`

![Manage -> Inventory](./images/nd3/add_switches/00_manage_inventory.png)

## 3. Inventory Screen (ER switch)

Click Actions -> Add Switches

![Actions -> Add Switches](./images/nd3/add_switches/01_inventory.png)

## 4. Pick a Fabric Screen (ER switch)

Click `Choose Fabric`

![Pick a Fabric](./images/nd3/add_switches/02_pick_a_fabric.png)

## 5. Select Fabric Screen (ER switch)

- Select `ISN`
- Click `Select`

![Select Fabric](./images/nd3/add_switches/03_select_fabric.png)

## 6. Seed Switch Details Screen (ER switch)

- `Seed IP` 192.168.12.111
- `Username` admin
- `Password` whatever you set when bringup up the nexus9000v switches
- `Max Hops` 0 (default of 2 will work, but 0 reduces the discovery time`
- `Set as individual device write credential` Enable
- Click `Discover Switches`

![Seed Switch Details](./images/nd3/add_switches/04_seed_switch_details.png)

## 7. Discovery Results Screen (ER switch)

- Select the ER switch
- Click `Add Switches`

![Discovery Results](./images/nd3/add_switches/05_discovery_results.png)

## 8. Wait for the switch to be added (ER switch)

![Wait](./images/nd3/add_switches/06_wait.png)

- Click `Close`

![Wait](./images/nd3/add_switches/07_wait.png)

## 9. Inventory Screen (SITE1 Fabric Switches)

- Click `Add Switches`

![Wait](./images/nd3/add_switches/08_inventory.png)

## 10. Pick a Fabric Screen (SITE1 Fabric switches)

- Click `Choose Fabric`

![Pick a Fabric](./images/nd3/add_switches/09_pick_a_fabric.png)

## 11. Select Fabric Screen (SITE1 Fabric switches)

- Select the VXLAN fabric
- Click `Select`

![Select Fabric](./images/nd3/add_switches/10_select_fabric.png)

## 12. Seed Switch Details Screen (SITE1 Fabric switches)

- `Seed IP` 192.168.12.131
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

- Select switches (L1, S1)
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

- `Seed IP` 192.168.12.132
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

- Select switches (L2, S2)
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

- ER (Edge Router role)
- S1 (Border Spine role)
- S2 (Border Spine role)
- L1 (Leaf role)
- L2 (Leaf role)

- Select the ER switch
- Click Actions -> Set Role

![Set Role](./images/nd3/add_switches/25_set_role.png)

## 24. Select Role Dialog (ER)

- Scroll down the list and select Edge Router
- Click `Select`

![Select Role](./images/nd3/add_switches/26_select_role.png)

## 25. Warning Dialog (ER)

- Read and acknowledge the warning.  Click `OK`
- We will Recalculate and Deploy later.

![Warning Dialog](./images/nd3/add_switches/27_warning.png)

## 26. Border Spine Switch Role

- Select the S1 and S2 switches
- Click Actions -> Set Role

![Border Spine Switch Role](./images/nd3/add_switches/28_border_spine_switch_role.png)

## 27 Select Role Dialog (Border Spine Switches)

- Select `Border Spine`
- Click `Select`

![Select Role](./images/nd3/add_switches/29_select_role.png)

## 28. Warning Dialog (Border Spine Switches)

- Read and acknowledge the warning.  Click `OK`
- We will Recalculate and Deploy later.

![Select Role](./images/nd3/add_switches/30_warning.png)

## 29. Leaf Switch Role

- Select the L1, L2 switches
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

This will take time (15-30 minutes) as the S1, S2, L1, L2 switches reboot.

Click `Refresh` occasionally to avoid being logged out due to inactivity...

![Wait](./images/nd3/add_switches/34_wait.png)

## 33. All Switches Are Ready

![All Switches Ready](./images/nd3/add_switches/35_all_switches_ready.png)

## 34. Manage Fabrics

- Click `Manage -> Fabrics`

![Manage -> Fabrics](./images/nd3/add_switches/36_manage_fabrics.png)

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

## Fabrics (ISN)

Perform steps 34-41 for the ISN fabric.

## Fix Peering

You'll notice on the switch consoles that they are not peering.

This is because the mac address on all inter-switch interfaces are the same.

Follow this link to fix that.

[Fix Interface Mac Addresses](https://github.com/allenrobel/n9kv-kvm/blob/main/docs/n9kv_fix_interface_mac_addresses.md)
