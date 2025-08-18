# ND 4.1 - Create ISN, SITE1, and SITE2 fabrics

Below are summary steps for creating the fabrics used in this project.
The outlines follow the GUI paths to effect the desired configurations.
For example, `Manage` refers to the `Manage` button in the left sidebar.
`Fabrics` to the suboption when clicking `Manage`, and `Actions` to the
button at the top-right of the Fabrics page, etc.

We'll add screen grabs later but hopefully below will provide enough
breadcrumbs to make it through this step.

## MSD (Multi-site Domain) fabric bringup

### Summary MSD

- Manage
  - Fabrics
    - Fabric Groups
      - Actions -> Create fabric group
      - Select a type
        - Name `MSD`
        - Select VXLAN/Multi-Site Domain (MSD)
        - Click `Next`
      - Advanced Settings
        - DCI
          - Multi-Site Overlay IFC Deployment Method
            - Select `directPeering` from the popup menu
          - Multi-Site Underlay IFC Auto Deployment Flag
            - Enable
          - BGP Send-community on Multi-Site Underlay IF
            - Enable
        - Click `Next`
        - Review settings and click `Submit`

## SITE1 and SITE2 fabric bringup

### General Guidelines

To enable VRF Lite peering between the BG1 and BG2 Border Gatewats in fabrics SITE1
and SITE2, it's imperitive that you enable `back2back&ToExternal` and its relevant
suboptions (suboptions depend on your goals but, for now, enable them all). 
Without doing so, ND will not automatically configure this peering when you invoke
`Recalculate and Deploy`.

We also need to ensure there is no overlap between the address ranges
that ND uses for various functions.  To do this, we'll modify the second
octet of each of the ranges to match the site number e.g. 11, 12, 13, etc
for SITE1 and 21, 22, 23, etc, for SITE2.

### Summary SITE1

- Manage
  - Fabrics
    - Create Fabric
      - `Create new LAN fabric`
      - Click `Next`
      - Select `VXLAN` and check `Data Center VXLAN EVPN`
      - Click `Next`
        - `Settings`
          - `Configuration mode`
            - Select `Advanced` (important!)
          - `Name` SITE1
          - `Overlay routing protcol` iBGP
          - `BGP ASN` 65001
          - Click `Next`
            - `Advanced settings`
              - Click the `Resources` tab (middle-top of page)
                - Underlay Routing Loopback IP Range
                  - 10.11.0.0/22
                - Underlay VTEP Loopback IP Range
                  - 10.12.0.0/22
                - Underlay RP Loopback IP Range
                  - 10.13.0.0/24
                - Underlay Subnet IP Range
                  - 10.14.0.0/22
              - Scroll down to `VRF Lite Deployment`
                - Click and set to `back2BackAndExternal`
              - Enable the following
                - `Auto Deploy for Peer`
                - `Auto Deploy Default VRF`
                - `Auto Deploy Default VRF for Peer`
              - VRF Lite Subnet IP Range
                - 10.15.0.0/16
            - Click `Next`
              - `Summary`
                - Review and click `Submit`

### Summary SITE2

- Manage
  - Fabrics
    - Create Fabric
      - `Create new LAN fabric`
      - Click `Next`
      - Select `VXLAN` and check `Data Center VXLAN EVPN`
      - Click `Next`
        - `Settings`
          - `Configuration mode`
            - Select `Advanced` (important!)
          - `Name` SITE2
          - `Overlay routing protcol` iBGP
          - `BGP ASN` 65002
          - Click `Next`
            - `Advanced settings`
              - Click the `Resources` tab (middle-top of page)
                - Underlay Routing Loopback IP Range
                  - 10.21.0.0/22
                - Underlay VTEP Loopback IP Range
                  - 10.22.0.0/22
                - Underlay RP Loopback IP Range
                  - 10.23.0.0/24
                - Underlay Subnet IP Range
                  - 10.24.0.0/22
              - Scroll down to `VRF Lite Deployment`
                - Click and set to `back2BackAndExternal`
              - Enable the following
                - `Auto Deploy for Peer`
                - `Auto Deploy Default VRF`
                - `Auto Deploy Default VRF for Peer`
              - VRF Lite Subnet IP Range
                - 10.25.0.0/16
            - Click `Next`
              - `Summary`
                - Review and click `Submit`
