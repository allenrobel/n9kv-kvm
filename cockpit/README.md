# Nexus9000v Monitoring with Cockpit

[Cockpit](https://cockpit-project.org) is a web-based graphical interface for
managing and monitoring servers.  It's completely optional so, if it's not
your thing, feel free to ignore this section.

The files in this directory include:

1. Backend Python script to collect/display Nexus 9000v status
2. Frontend Javascript and css files to add a Nexus 9000v VMs page to Cockpit
3. systemd service files to enable persistent monitoring

In the end, you'll have something in Cockpit that looks like below.
Nexus 9000v are added and removed dynamically as you create and destroy
them so, once setup, it's pretty low maintenance.

![Cockpit Monitoring](cockpit.png)
