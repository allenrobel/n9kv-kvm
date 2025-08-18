# Linux Bridge Statistics Monitor

A Cockpit web interface for monitoring Linux bridge statistics, including RX/TX packet counts, byte counts, errors, and dropped packets.

## Features

- Real-time monitoring of all Linux bridges on the system
- RX/TX statistics with human-readable byte formatting
- Interface listing for each bridge
- STP (Spanning Tree Protocol) state monitoring
- Auto-refresh functionality
- Error and dropped packet monitoring
- Clean, responsive web interface

## Installation

1. Copy the files to the appropriate directories:
   ```bash
   sudo cp -r usr/share/cockpit/bridges /usr/share/cockpit/
   sudo cp usr/local/bin/bridge_monitor.py /usr/local/bin/
   sudo chmod +x /usr/local/bin/bridge_monitor.py
   sudo cp usr/local/bin/bridge-monitor.service /etc/systemd/system/
   sudo cp usr/local/bin/bridge-monitor.timer /etc/systemd/system/
   ```

2. Enable and start the systemd timer for optimal performance:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable bridge-monitor.timer
   sudo systemctl start bridge-monitor.timer
   ```

3. Restart Cockpit:
   ```bash
   sudo systemctl restart cockpit
   ```

4. Access the Bridge Statistics page in Cockpit at:
   `https://your-server:9090`

## Performance Optimization

The bridge monitor uses a systemd timer service that runs every 30 seconds to collect statistics and cache them in `/tmp/bridge-status.json`. This approach:

- **Reduces CPU usage** - No persistent processes running
- **Improves responsiveness** - Cockpit reads cached data instead of executing scripts
- **Provides consistent updates** - Data refreshes automatically in the background

You can check the service status with:
```bash
sudo systemctl status bridge-monitor.timer
sudo systemctl status bridge-monitor.service
```

## Command Line Usage

The bridge monitor can also be used from the command line:

```bash
# Show all bridges in table format
/usr/local/bin/bridge_monitor.py --table

# Show specific bridge
/usr/local/bin/bridge_monitor.py --bridge BR_LE1_HO1 --table

# Output JSON for scripting
/usr/local/bin/bridge_monitor.py --json
```

## Statistics Collected

For each bridge, the monitor collects:
- **Name**: Bridge interface name
- **Status**: UP/DOWN state
- **RX Statistics**: Bytes, packets, errors, dropped
- **TX Statistics**: Bytes, packets, errors, dropped
- **Interfaces**: List of attached interfaces
- **STP State**: Spanning Tree Protocol enabled/disabled

## Data Sources

The monitor uses standard Linux networking tools:
- `ip -s link show` for interface statistics
- `bridge link` for bridge topology
- `/sys/class/net/*/bridge/` for STP state
- `/sys/class/net/*/brif/` for interface listing

## Requirements

- Python 3.8+
- Linux with bridge-utils
- Cockpit web console
- Root or appropriate permissions for network monitoring

## Files

- `bridge_monitor.py` - Python backend script
- `index.html` - Main web interface
- `bridge-monitor.js` - JavaScript frontend logic
- `bridge-monitor.css` - Styling
- `manifest.json` - Cockpit module manifest