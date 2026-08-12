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

To enable VRF Lite peering between the S1_BG1 and S2_BG1 Border Gatewats in fabrics SITE1
and SITE2, it's imperitive that you enable `back2back&ToExternal` and its relevant
suboptions (suboptions depend on your goals but, for now, enable them all).
Without doing so, ND will not automatically configure this peering when you invoke
`Recalculate and Deploy`.

We also need to ensure there is no overlap between the address ranges
that ND uses for various functions.  To do this, we'll modify the second
octet of each of the ranges to match the site number e.g. 11, 12, 13, etc
for SITE1 and 21, 22, 23, etc, for SITE2.  Feel free to use a different
scheme if you want.

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

### SITE1 fabric PTP (deliberate asymmetry — SITE1 enabled, SITE2 disabled)

SITE1 runs with fabric PTP **enabled and deployed** (since 2026-08-12); SITE2 stays **disabled**.
This is intentional: one fabric in each state supports API-behavior testing (e.g. the ND-injected
`ptp` echo reads `true` on SITE1 pre-deploy records vs `false` on SITE2 — see vault note
`interface-get-undocumented-ptp-field`). Do not "clean up" the SITE1 PTP config.

- Fabric settings (`management` block): `ptp: true`, `ptpVlanId: 1000`, `ptpLoopbackId: 0`, `ptpDomainId: 0`
- ND preflight requires, on each ToR **and its pairing vPC leafs** (here S1_TOR1 + S1_LE1/S1_LE2):
  a PTP source SVI for the PTP VLAN, **with an IPv4 address** (two separate preflight errors
  otherwise — first for the missing VLAN id/SVIs, then for the missing SVI IP)
- SVIs created (`interfaceType: svi`, `policyType: svi`, `adminState: true`), subnet
  `10.16.100.0/24` (clear of all other lab pools; host octet mirrors each switch's mgmt IP):
  - S1_TOR1 `vlan1000` 10.16.100.161/24 (ND renders `ptp source 10.16.100.161` from this SVI)
  - S1_LE1 `vlan1000` 10.16.100.151/24
  - S1_LE2 `vlan1000` 10.16.100.152/24
- Non-ToR-pairing switches (LE3/LE4/SP1/BG1) need no SVI; their `ptp source` uses loopback0
- Generated CLI: `feature ptp`, `clock protocol ptp vdc 1`, `ptp domain 0`, `ptp source <ip>`
  fabric-wide, per-port `ptp` on physical underlay links and vPC peer-link members only
  (never under port-channels)

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

## ISN external fabric bringup

The ISN fabric hosts WAN1 (C8000V edge router) and provides the inter-site WAN path.

### Summary ISN

- Manage
  - Fabrics
    - Create Fabric
      - `Create new LAN fabric`
      - Click `Next`
      - Select `External and Inter-Fabric Connectivity`
      - Click `Next`
        - `Settings`
          - `Name` ISN
          - `BGP ASN` 65535
          - Click `Next`
            - Review settings and click `Submit`

> **Gotcha (ND 4.2.1, API-created fabrics):** an `externalConnectivity` fabric created via
> `POST /api/v1/manage/fabrics` comes up with `management.monitoredMode: true`. Monitored mode
> silently blocks all deploys ("deployment disable mode"; deploy reports completed but
> `pendingConfig` never shrinks). Flip it off before adding switches: GET the fabric object,
> set `management.monitoredMode: false`, PUT it back — or uncheck Monitored Mode in the GUI
> fabric settings.

### WAN1 loopback and BGP router-id (required)

WAN1's day-0 startup config carries no loopback and no BGP router-id, and the fabric-generated
`router bgp 65535` (from the `base_bgp_external` policy) does not include one. Without it, BGP
cannot run (`% BGP cannot run because the router-id is not configured`). After adding WAN1 to
ISN, configure both of the following, then deploy ISN:

- **Loopback0 `10.35.0.1/32`** — created as a managed *interface* (not a raw policy):
  `POST /api/v1/manage/fabrics/ISN/switches/{WAN1-serial}/interfaces` with
  `configData.networkOS = {networkOSType: "ios-xe", policy: {policyType: "iosXeLoopback",
  adminState: true, ip: "10.35.0.1", description: "Routing loopback (router-id)"}}`.
  GUI: Manage > Fabrics > ISN > Interfaces > Create Interface > Loopback on WAN1.
  (Posting `ios_xe_int_loopback` directly to the policies API fails template validation —
  loopbacks are first-class interface objects on ND 4.2.1.)
- **BGP router-id policy** — `POST /api/v1/manage/fabrics/ISN/policies` with
  `templateName: ios_xe_bgp_router_id`, `entityType: switch`, `entityName: SWITCH`,
  `templateInputs: {BGP_AS: "65535", LOOPBACK_IP: "10.35.0.1"}`.

> **Note (4.2.1/4.3 alignment):** keep `10.35.0.1/32` for WAN1 Loopback0 on both ND versions.
> Cross-site infrastructure carries no site prefix; `10.35.x` stays clear of the site pools
> (`10.1x`/`10.2x`), the MSD ranges (`10.10.0.x`), and the WAN p2p /30s
> (`10.15.0.0/30`, `10.25.0.0/30`).

### WAN eBGP peering (when it appears)

The `ebgpVrfLite` links put **no** IPs on the parent interfaces (Gi2/Gi3, Eth1/3). Peering
subinterfaces + BGP neighbors on both ends are auto-generated only when a **VRF is extended**
over the link (requires the fabrics' `back2BackAndToExternal` + auto-deploy flags and the
links' `autoGenConfigPeer: true`). Until the first VRF extension, `show ip bgp summary` on
WAN1 legitimately shows no neighbors.

### API equivalents (captured on ND 4.2.1, 2026-08-07)

Fabric create accepts a minimal payload; everything else is server-side defaulting.
License tier is `premier` (lowercase on the wire).

```json
POST /api/v1/manage/fabrics
{
  "name": "ISN",
  "category": "fabric",
  "licenseTier": "premier",
  "management": {"bgpAsn": "65535", "type": "externalConnectivity"},
  "securityDomain": "all",
  "telemetryCollection": false
}
```

SITE1/SITE2 use `"type": "vxlanIbgp"` with their ASNs, then a follow-up GET/modify/PUT of the
fabric object to apply the Resources-tab ranges (`bgpLoopbackIpRange`, `nveLoopbackIpRange`,
`anycastRendezvousPointIpRange`, `intraFabricSubnetRange`, `vrfLiteSubnetRange`) and the VRF-Lite
settings (`vrfLiteAutoConfig: "back2BackAndToExternal"`, `autoSymmetricVrfLite`,
`autoVrfLiteDefaultVrf`, `autoSymmetricDefaultVrf`).

## Add SITE1 and SITE2 to MSD Fabric Group

ISN is also added as a member — the fabric group contains all three fabrics.

- Manage
  - Fabrics
    - Fabric Groups
      - Click `MSD`
      - Actions -> Add member fabrics
      - Select `SITE1`, `SITE2`, and `ISN`
      - Click `Save`

### API equivalent (captured on ND 4.2.1, 2026-08-07)

One member per call — the endpoint rejects batches with
`"Only one member fabric can be added at a time"`:

```json
POST /api/v1/manage/fabrics/MSD/actions/addMembers
{"members": [{"name": "SITE1"}]}
```

Verify with `GET /api/v1/manage/fabrics/MSD/members` (note: the read side is `/members`;
the write side is `/actions/addMembers` — POST/PUT to `/members` itself returns 404).
