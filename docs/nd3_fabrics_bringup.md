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

## MSD Fabric

TODO: This section may not be completely accurate with
respect to menu names, etc.  We'll update it later...

- Manage
  - Fabrics
  - Actions
    - Create Fabric
      - `Fabric Name` MSD
      - Click `Choose Fabric`
      - From the popup, select `Multi-Site Domain Fabric`

TOTO complete this section...

## SITE1 Fabric

We want to ensure three things.

1. The IP ranges do not overlap with SITE2
2. The BGP AS is unique vs SITE2
3. `Back2Back&ToExternal` is set and suboptions are enabled

- Manage
  - Actions
    - Create Fabric
      - `Fabric Name` SITE1
      - Click `Choose Fabric`
      - From the popup, select `Data Cemter VXLAN EVPN`
      - Click `Select`
      - General Parameters
        - `BGP AS #` 65001
      - Resources
        - `Underlay Routing Loopback IP Range`
          - 10.11.0.0/22
        - `Underlay VTEP Loopback IP Range`
          - 10.12.0.0/22
        - `Underlay Subnet IP Range`
          - 10.13.0.0/22
        - Scroll down to `VRF Lite Deployment`
        - Click the popup menu (current displays `Manual`) and select `Back2Back&ToExternal`
        - Enable the three suboptions directly below
          - `Auto Deploy for Peer`
          - `Auto Deploy Default VRF`
          - `Auto Deploy Default VRF for Peer`
        - `VRF Lite Subnet IP Range` 10.14.0.0/16 (make this unique vs SITE2)
        - Click `Save`

## SITE2 Fabric

We want to ensure three things.

1. The IP ranges do not overlap with SITE1
2. The BGP AS is unique vs ISN and SITE1
3. `Back2Back&ToExternal` is set and suboptions are enabled

- Manage
  - Actions
    - Create Fabric
      - `Fabric Name` SITE2
      - Click `Choose Fabric`
      - From the popup, select `Data Cemter VXLAN EVPN`
      - Click `Select`
      - General Parameters
        - `BGP AS #` 65002
      - Resources
        - `Underlay Routing Loopback IP Range`
          - 10.21.0.0/22
        - `Underlay VTEP Loopback IP Range`
          - 10.22.0.0/22
        - `Underlay Subnet IP Range`
          - 10.23.0.0/22
        - Scroll down to `VRF Lite Deployment`
        - Click the popup menu (current displays `Manual`) and select `Back2Back&ToExternal`
        - Enable the three suboptions directly below
          - `Auto Deploy for Peer`
          - `Auto Deploy Default VRF`
          - `Auto Deploy Default VRF for Peer`
        - `VRF Lite Subnet IP Range` 10.24.0.0/16 (make this unique vs SITE1)
        - Click `Save`

## Review Fabrics

On the Manage -> Fabrics screen, the `Fabric Health` column should indicate `Healthy`
status for all three fabrics.

If it does not, then double-click into the fabric(s) that show warnings, and review
`Event Analytics` for the fabrics.  Most likely, there is an IP range conflict between
fabrics.

## Add SITE1 and SITE2 to MSD Fabric

TODO: Complete this section.
