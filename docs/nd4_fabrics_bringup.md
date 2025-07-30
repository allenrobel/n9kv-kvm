# ND 4.1 - Create ISN and VXLAN fabrics

Below are summary steps for creating ISN and VXLAN fabrics.

We will add more detail later, including screen grabs.

## ISN (inter-site network) fabric bringup

### Summary ISN

- Manage
  - Fabrics
    - Create Fabric
      - Create new LAN fabric
      - Click `Next`
      - Select `External and inter-fabric connectivity`
      - Click `Next`
        - Select Advanced (important!)
        - `Name` ISN
        - `BGP ASN` 65001
        - Click `Next`
          - Advanced settings
            - General Parameters
              - Fabric Monitor Mode (uncheck/disable this)
              - Click `Next`
                - Summary
                  - Review and click `Submit`

## VXLAN fabric bringup

### General Guidelines

To enable VRF Lite peering between the S1 and S2 Border Spines in fabric VXLAN and
the ER Edge Router in fabric ISN, it's imperitive that you enable `back2back&ToExternal`
and its relevant suboptions (suboptions depend on your goals but, for now, enable them
all). Without doing so, ND will not automatically configure this peering when you invoke
`Recalculate and Deploy`.

### Summary VXLAN

- Manage
  - Fabrics
    - Create Fabric
      - `Create new LAN fabric`
      - Click `Next`
      - Select `VXLAN`
      - Click `Next`
        - `Settings`
          - `Configuration mode`
            - Select `Advanced` (important!)
          - `Name` VXLAN
          - `Overlay routing protcol` iBGP
          - `BGP ASN` 65002
          - Click `Next`
            - `Advanced settings`
              - Click the `Resources` tab (middle-top of page)
              - Scroll down to `VRF Lite Deployment`
                - Click and set to `back2BackAndExternal`
              - Enable the following
                - `Auto Deploy for Peer`
                - `Auto Deploy Default VRF`
                - `Auto Deploy Default VRF for Peer`
            - Click `Next`
              - `Summary`
                - Review and click `Submit`
