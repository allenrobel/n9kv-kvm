# Add Switches to Fabrics ND 3.2

## Add ER Switch to ISN Fabric

We'll first add the ER switch to the ISN fabric.

## Select Inventory Screen (ER switch)

Click `Manage -> Inventory`

![Manage -> Inventory](./images/nd3/add_switches/00_manage_inventory.png)

## Inventory Screen (ER switch)

Click Actions -> Add Switches

![Actions -> Add Switches](./images/nd3/add_switches/01_inventory.png)

## Pick a Fabric Screen (ER switch)

Click `Choose Fabric`

![Pick a Fabric](./images/nd3/add_switches/02_pick_a_fabric.png)

## Select Fabric Screen (ER switch)

- Select `ISN`
- Click `Select`

![Select Fabric](./images/nd3/add_switches/03_select_fabric.png)

## Seed Switch Details Screen (ER switch)

- `Seed IP` 192.168.12.111
- `Username` admin
- `Password` whatever you set when bringup up the nexus9000v switches
- `Max Hops` 0 (default of 2 will work, but 0 reduces the discovery time`
- `Set as individual device write credential` Enable
- Click `Discover Switches`

![Seed Switch Details](./images/nd3/add_switches/04_seed_switch_details.png)

## Discovery Results Screen (ER switch)

- Select the ER switch
- Click `Add Switches`

![Discovery Results](./images/nd3/add_switches/05_discovery_results.png)

## Wait for the switch to be added (ER switch)

![Wait](./images/nd3/add_switches/06_wait.png)

- Click `Close`

![Wait](./images/nd3/add_switches/07_wait.png)

## Inventory Screen (VXLAN Fabric Switches)

- Click `Add Switches`

![Wait](./images/nd3/add_switches/08_inventory.png)

## Pick a Fabric Screen (VXLAN switches)

- Click `Choose Fabric`

![Pick a Fabric](./images/nd3/add_switches/09_pick_a_fabric.png)

## Select Fabric Screen (VXLAN switches)

- Select the VXLAN fabric
- Click `Select`

![Select Fabric](./images/nd3/add_switches/10_select_fabric.png)

## Detour for NX-OS version 10.5(3)F

If you configured the nexus9000v to boot 10.5(3)F, their `Eth1/1` and `Eth1/2` interfaces will be
`shutdown` by default.  Connect to each of them and bring these interfaces up so that
the switch discovery steps below work.

Either telnet to the console of each switch:

- telnet localhost 9011
- telnet localhost 9021
- telnet localhost 9022
- telnet localhost 9031

Or ssh to each switch

- ssh admin@192.168.12.111
- ssh admin@192.168.12.121
- ssh admin@192.168.12.122
- ssh admin@192.168.12.131

And issue the following on each switch

```bash
conf
interface Eth1/1-2
no shutdown
end
copy run start
```

## Seed Switch Details Screen (VXLAN switches)

- `Seed IP` 192.168.12.131
- `Username` admin
- `Password` whatever you set when bringup up the nexus9000v switches
- `Max Hops` 1 (default of 2 will work, but 1 reduces the discovery time`
- `Set as individual device write credential` Enable
- `Preserve Config` disable (important!!!)
- Click `Discover Switches`

We are using the IP address of the L1 switch since it's connected to both S1 and S2 switches.

![Seed Switch Details](./images/nd3/add_switches/11_seed_switch_details.png)

## Warning Dialog

- Click `Confirm`

![Warning Dialog](./images/nd3/add_switches/12_warning_dialog.png)

## Discovery Results Screen

- Select all three switches (L1, S1, S2)
- Click `Add Switches`

![Discovery Results](./images/nd3/add_switches/13_discovery_results.png)

The switches will be rebooted.

![Discovery Results](./images/nd3/add_switches/14_switches_reboot.png)

## Wait

- Wait for the switches to be added.
- Click `Close`

![Wait](./images/nd3/add_switches/15_wait_for_switch_added.png)

## Change Switch Roles

We'll now change the roles of the switches.

- ER (Edge Router role)
- S1 (Border Spine role)
- S2 (Border Spine role)
- L1 (Leaf role)

- Select the ER switch
- Click Actions -> Set Role

![Set Role](./images/nd3/add_switches/16_set_role.png)

## Select Role Dialog (ER)

- Scroll down the list and select Edge Router
- Click `Select`

![Select Role](./images/nd3/add_switches/17_select_role.png)

## Warning Dialog (ER)

- Read and acknowledge the warning.  Click `OK`
- We will Recalculate and Deploy later.

![Select Role](./images/nd3/add_switches/18_warning.png)

## Border Spine Switch Role

- Select the S1 and S2 switches
- Click Actions -> Set Role

![Border Spine Switch Role](./images/nd3/add_switches/19_border_spine_switch_role.png)

## Select Role Dialog (Border Spine Switches)

- Select `Border Spine`
- Click `Select`

![Select Role](./images/nd3/add_switches/20_select_role.png)

## Warning Dialog (S1, S2)

- Read and acknowledge the warning.  Click `OK`
- We will Recalculate and Deploy later.

![Select Role](./images/nd3/add_switches/21_warning.png)

## L1 Switch Role

- Select the L1 switch
- Click Actions -> Set Role

![Set Role](./images/nd3/add_switches/22_set_role.png)

## Select Role Dialog (L1 Switch)

- Select `Leaf`
- Click `Select`

![Select Role](./images/nd3/add_switches/23_select_role.png)

## Warning Dialog (L1)

- Read and acknowledge the warning.  Click `OK`
- We will Recalculate and Deploy later.

![Warning](./images/nd3/add_switches/24_warning.png)

## Wait (for reachability)

Wait for all switches to become reachable (Discovery Status column will display `OK`).

This will take time (15-30 minutes) as the S1, S2, L1 switches reboot.

Click `Refresh` occasionally to avoid being logged out due to inactivity...

![Wait](./images/nd3/add_switches/25_wait.png)

## All Switches Are Ready

![All Switches Ready](./images/nd3/add_switches/26_all_switches_ready.png)

## Manage Fabrics

- Click `Manage -> Fabrics`

![Manage -> Fabrics](./images/nd3/add_switches/27_manage_fabrics.png)

## VXLAN Fabric

- In the Fabric Name column, double-click the blue `VXLAN` name

![VXLAN Fabric](./images/nd3/add_switches/28_vxlan_fabric.png)

## Recalculate and Deploy - VXLAN

- Click the blue Actions dropdown and select `Recalculate and Deploy`

![Recalculate and Deploy](./images/nd3/add_switches/29_recalculate_and_deploy.png)

## Wait for switch configs to be built

![Wait](./images/nd3/add_switches/30_wait.png)

## Deploy Configuration - VXLAN

- Click `Deploy All`

![Deploy Configuration](./images/nd3/add_switches/31_deploy.png)

## Wait

- Wait for the deployment to finish

![Wait](./images/nd3/add_switches/32_wait.png)

## Ignore Error on Switch consoles

On the switch consoles, during deployment, you'll see the following, which you can ignore.

```bash
2025 Aug  2 03:25:39 L1 %$ VDC-1 %$ nve[28908]: 'feature nve overlay' requires 'application leaf engine' (ALE) 1 or above based line cards. Please consult documentation
```

- Click `Close`

![Wait](./images/nd3/add_switches/33_close.png)

## Fabric Overview - VXLAN (close the window)

- Click the `X` at the upper-right of the winder to close it.

![Wait](./images/nd3/add_switches/34_close_window.png)

## Fabrics (ISN) Select

- In the Fabric Name column, double-click the blue ISN fabric name

![Fabrics Select ISN](./images/nd3/add_switches/35_fabrics_isn.png)

## Fabric Overview (ISN)

- Click `Actions` -> `Recalculate and Deploy`

![Recalculate and Deploy](./images/nd3/add_switches/36_recalculate_and_deploy.png)

## Deploy Configuration (ISN)

- Click `Deploy All`

![Recalculate and Deploy](./images/nd3/add_switches/37_deploy.png)

## Wait (ISN)

- When the deployment is complete, click `Close`

![Close](./images/nd3/add_switches/38_close.png)

## Fix Peering

You'll notice on the switch consoles that they are not peering.

This is because the mac address on all inter-switch interfaces are the same.

Follow this link to fix that.

[Fix Interface Mac Addresses](https://github.com/allenrobel/n9kv-kvm/blob/main/docs/n9kv_fix_interface_mac_addresses.md)
