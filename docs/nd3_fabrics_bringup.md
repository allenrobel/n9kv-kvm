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
breadcrumbs to make it through this step.

- Manage
  - Fabrics
  - Actions
    - Create Fabric
      - `Fabric Name` ISN
      - Click `Choose Fabric`
      - From the popup, select `External Connectivity Network`
      - Click `Select`
      - General Parameters
        - `BGP AS #` 65001
        - `Fabric Monitor Mode` Uncheck/disable (important!)
        - Click `Save`
  - Actions
    - Create Fabric
      - `Fabric Name` VXLAN
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
        - Click `Save`
