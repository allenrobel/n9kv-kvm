# ND 3.2 Fabrics Bringup

## Summary

In the dropdown menu next to `Nexus Dashboard`, select `Fabric Controller`
to enter the Nexus Dashboard Fabric Controller (NDFC) app.

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
