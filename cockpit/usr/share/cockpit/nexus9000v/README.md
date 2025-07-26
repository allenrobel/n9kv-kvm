# Cockpit Nexus9000v Monitoring UI files.

First, setup the backend python script (see $HOME/repos/n9kv-kvm/cockpit/usr/local/bin/README.md).

Then follow the steps below.

## Selecting a theme (dark or light)

### For dark theme

```bash
cp nexus-monitor-dark-theme.css nexus-monitor.css
```

### For light theme

```bash
cp nexus-monitor-light-theme.css nexus-monitor.css
```

### Copy all files into Cockpit

```bash
sudo mkdir /usr/share/cockpit/nexus9000v
sudo cp $HOME/repos/n9kv-kvm/cockpit/usr/share/cockpit/nexus9000v/* /usr/share/cockpit/nexus9000v
```

