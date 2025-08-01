# NDFC Bringup

Nexus Dashboard 3.2 hosts other applications, such as Nexus Dashboard
Fabric Controller (NDFC).  Below, we'll perform the initial configuration
for NDFC.

## Login

When logging into Nexus Dashboard, you'll land on the Nexus Dashboard
journey screen.  We need first to configure NDFC.  To do this.

- Click the `Admin Console` dropdown menu and select `Fabric Controller`

![NDFC First Access](./images/ndfc/00_first_access.png)

## Introductory Screen

On first connection to the `Fabric Controller` application, you'll see an introductory screen.

- Optionally, click `No not show this message again.`
- Click `Get Started`

![NDFC Introductory Screen](./images/ndfc/01_introduction.png)

## Journey Screen

On the Journey screen, highlight Service Setup, and click `Go`

![Journey Screen](./images/ndfc/02_journey.png)

## Operational Modes Screen

On the `Operational Modes` screen:

- Click `LAN`
- Click `Next`

![Operational Modes Screen](./images/ndfc/03_operational_modes.png)

## Feature Selection Screen

On the `Feature Selection` screen

- Choose `Fabric Management Basic` for the lower memory footprint.
- Click `Next`

![Feature Selection Screen](./images/ndfc/04_feature_selection.png)

## Summary Screen

On the `Summary` screen,

- Review your choices
- Click `Submit`

![Summary Screen](./images/ndfc/05_summary.png)

## Controller Service Setup Screen

- Click `Back to Journey`

![Controller Service Setup Screen](./images/ndfc/06_controller_service_setup.png)

## Journey Screen Revisited

At this point, Fabric Controller is configuring and starting its services, so the side bar does not list all choices yet.

Wait some time, click `Refresh` in the upper-right corner of the page.

![Controller Service Setup Screen](./images/ndfc/07_journey.png)

## Features Updated - Reload Page

You should see a message at the top of the page.

"Some features have been updated. Reload the page to see latest changes."

Rather than click `Refresh` here, the message is asking to reload your browser.

In Chrome, that's Ctrl+R, or click the reload icon to the left of the URL field.

![Features Updated Message](./images/ndfc/08_featues_updated.png)

## Introduction or Set Credentials

After reloading your browser, you may encounter the introductory screen again,
and/or a warning to set device credentials required for interacting with your
nexus9000v instances.   Depending whether the introduction is presented again,
and the order these are presented, one may be covered by the other.

So, perform the following in whatever order these dialogs are presented.

- Click `Set credentials` if the warning dialog is displayed.
- Check the `Do not show this message again.` box (optional), and click `Get Started`

![Intro Covering Set Credentials](./images/ndfc/09_intro_set_credentials_behind.png)

OR

![Set Credentials Covering Intro](./images/ndfc/10_set_credentials_intro_behind.png)

## LAN Credentials Management

Clicking `Set Credentials` will bring up the `LAN Credentials Management` screen.

- Click the blue `Set` button.

![LAN Credentials Management](./images/ndfc/11_lan_credentials_management.png)

## Set Credentials Dialog

- `Username` nexus9000v username (most likely admin)
- `Password` nexus9000v password you plan to assign when bringing these up
- `Confirm Password`
- `Robot` check this since we're assuming this is just a lab with a single user.
- Click `Save`

![Set Credentials Dialog](./images/ndfc/12_set_credentials.png)

## Success Dialog

- Click `OK`

![Set Credentials Dialog](./images/ndfc/13_success.png)

NDFC is now configured.
