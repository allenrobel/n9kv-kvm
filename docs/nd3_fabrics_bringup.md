# ND 3.2 Fabrics Bringup

## Summary

In the dropdown menu next to `Nexus Dashboard`, select `Fabric Controller`
to enter the Nexus Dashboard Fabric Controller (NDFC) app.

Below are summary steps for creating the fabrics used in this project.
The outlines follow the GUI paths to effect the desired configurations.
For example, `Manage` refers to the `Manage` button in the left sidebar.
`Fabrics` to the suboption when clicking `Manage`, `Actions` to the
button at the top-right of the Fabrics page, etc.

We'll add screen grabs later but hopefully below will provide enough
breadcrumbs to make it through these steps.

## ISN Fabric

- Manage
  - Fabrics
  - Actions
    - Create Fabric
      - `Fabric Name` ISN
      - Click `Choose Fabric`
      - From the popup, select `Multi-Site External Network`
        - Scroll down to the last item in the list...
      - Click `Select`
      - General Parameters
        - `BGP AS #` 65001
        - `Fabric Monitor Mode` Uncheck/disable (important!)
      - Advanced
        - `Enable NX-API` Check/enable
        - Click `Save`

## SITE1 Fabric

- Manage
  - Actions
    - Create Fabric
      - `Fabric Name` SITE1
      - Click `Choose Fabric`
      - From the popup, select `Data Cemter VXLAN EVPN`
      - Click `Select`
      - General Parameters
        - `BGP AS #` 65002
      - Resources
        - Scroll down to `VRF Lite Deployment`
        - Click the popup menu (current displays `Manual`) and select `Back2Back&ToExternal`
        - Enable the three suboptions directly below
          - `Auto Deploy for Peer`
          - `Auto Deploy Default VRF`
          - `Auto Deploy Default VRF for Peer`
        - `VRF Lite Subnet IP Range` 10.221.0.0/16 (make this unique vs SITE2)
        - Click `Save`

## SITE2 Fabric

- Manage
  - Actions
    - Create Fabric
      - `Fabric Name` SITE2
      - Click `Choose Fabric`
      - From the popup, select `Data Cemter VXLAN EVPN`
      - Click `Select`
      - General Parameters
        - `BGP AS #` 65003
      - Resources
        - Scroll down to `VRF Lite Deployment`
        - Click the popup menu (current displays `Manual`) and select `Back2Back&ToExternal`
        - Enable the three suboptions directly below
          - `Auto Deploy for Peer`
          - `Auto Deploy Default VRF`
          - `Auto Deploy Default VRF for Peer`
        - `VRF Lite Subnet IP Range` 10.222.0.0/16 (make this unique vs SITE1)
        - Click `Save`
