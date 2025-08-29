# Cockpit Nexus9000v Monitoring UI files

First, [install Cockpit](https://cockpit-project.org/running.html#ubuntu) if it is not already installed, and
[setup the backend python script](https://github.com/allenrobel/n9kv-kvm/blob/main/cockpit/usr/local/bin/README.md)

Cockpit typically comes pre-installed with Ubuntu Server 24.04.2 LTS.  You can
check if it is installed on your server by accessing the following URL (replace
your_server with your server's IP or hostname...)

`https://your-server:9090`

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
cd $HOME/repos/n9kv-kvm/cockpit/usr/share/cockpit/nexus9000v/
sudo cp * /usr/share/cockpit/nexus9000v
```
