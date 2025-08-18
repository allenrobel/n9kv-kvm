# Nexus9000v VM Monitoring Backend

## 1. Install Cockpit

Cockpit typically comes pre-installed with Ubuntu Server 24.04.2 LTS.  You can
check if it is installed on your server by accessing the following URL (replace
your_server with your server's IP or hostname...)

`https://your-server:9090`

If it's not installed, you can install it by following the steps at the Cockpit
project site.

https://cockpit-project.org/running.html#ubuntu

## 2. Copy the backend script into /usr/local/bin and make executable

```bash
cd $HOME/repos/n9kv-kvm/cockpit/usr/local/bin
sudo cp ./nexus9000v_monitor.py /usr/local/bin
sudo +x /usr/local/bin/nexus9000v_monitor.py
```

## 3. Verify the backend script is working

- sudo python3 /usr/local/bin/nexus9000v_monitor.py --table

```bash
arobel@glide:~/repos/n9kv-kvm$ source .venv/bin/activate
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$ source env/env.sh
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$ sudo python3 /usr/local/bin/nexus9000v_monitor.py --table
[sudo] password for arobel:
2025-08-18 19:56:36,752 - INFO - Scanning for Nexus 9000v VMs...
2025-08-18 19:56:36,962 - INFO - Found VM: SP1 (PID: 27110)
2025-08-18 19:56:37,112 - INFO - Found VM: SP2 (PID: 27170)
2025-08-18 19:56:37,271 - INFO - Found VM: LE1 (PID: 27263)
2025-08-18 19:56:37,422 - INFO - Found VM: LE2 (PID: 27356)
2025-08-18 19:56:37,563 - INFO - Found VM: BG1 (PID: 45334)
2025-08-18 19:56:37,694 - INFO - Found VM: BG2 (PID: 45383)
VM NAME              PID      CPU%     MEM(MB)    UPTIME          STATUS
--------             ---      ----     -------    -------         ------
SP1                  27110    75.7     12294      2d 19h 35m      running
SP2                  27170    76.5     12192      2d 19h 35m      running
LE1                  27263    168.0    12386      2d 19h 35m      running
LE2                  27356    80.5     12134      2d 19h 34m      running
BG1                  45334    80.5     12212      2d 13h 10m      running
BG2                  45383    81.2     12106      2d 13h 10m      running
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$
```

## 4. Add a service for persistent monitoring across host reboots

```bash
sudo cp ./nexus9000v-monitor.service /etc/systemd/system/nexus9000v-monitor.service
sudo cp ./nexus9000v-monitor.timer /etc/systemd/system/nexus9000v-monitor.timer
```

## 5. Set proper permissions

```bash
sudo chmod 644 /etc/systemd/system/nexus9000v-monitor.service
sudo chmod 644 /etc/systemd/system/nexus9000v-monitor.timer
```

## 6. Reload systemd and enable the timer

```bash
sudo systemctl daemon-reload
sudo systemctl enable nexus9000v-monitor.timer
sudo systemctl start nexus9000v-monitor.timer
```

## 7. Check status

```bash
sudo systemctl status nexus9000v-monitor.timer
sudo systemctl list-timers nexus9000v-monitor.timer
```

```bash
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$ sudo systemctl status nexus9000v-monitor.timer
● nexus9000v-monitor.timer - Run Nexus 9000v VM Monitor every 30 seconds
     Loaded: loaded (/etc/systemd/system/nexus9000v-monitor.timer; enabled; preset: enabled)
     Active: active (running) since Sun 2025-08-17 23:05:17 UTC; 20h ago
    Trigger: n/a
   Triggers: ● nexus9000v-monitor.service

Aug 17 23:05:17 glide systemd[1]: Started nexus9000v-monitor.timer - Run Nexus 9000v VM Monitor every 30 seconds.
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$ sudo systemctl list-timers nexus9000v-monitor.timer
NEXT                        LEFT LAST                         PASSED UNIT                     ACTIVATES
Mon 2025-08-18 20:00:00 UTC   4s Mon 2025-08-18 19:59:32 UTC 22s ago nexus9000v-monitor.timer nexus9000v-monitor.service

1 timers listed.
Pass --all to see loaded but inactive timers, too.
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$
```

## 8. View logs

```bash
sudo journalctl -u nexus9000v-monitor.service -f
```

```bash
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$ sudo journalctl -u nexus9000v-monitor.service -f
Aug 18 19:59:11 glide systemd[1]: Finished nexus9000v-monitor.service - Nexus 9000v VM Monitor.
Aug 18 19:59:11 glide systemd[1]: nexus9000v-monitor.service: Consumed 1.007s CPU time.
Aug 18 19:59:32 glide systemd[1]: Starting nexus9000v-monitor.service - Nexus 9000v VM Monitor...
Aug 18 19:59:33 glide systemd[1]: nexus9000v-monitor.service: Deactivated successfully.
Aug 18 19:59:33 glide systemd[1]: Finished nexus9000v-monitor.service - Nexus 9000v VM Monitor.
Aug 18 19:59:33 glide systemd[1]: nexus9000v-monitor.service: Consumed 1.085s CPU time.
Aug 18 20:00:14 glide systemd[1]: Starting nexus9000v-monitor.service - Nexus 9000v VM Monitor...
Aug 18 20:00:16 glide systemd[1]: nexus9000v-monitor.service: Deactivated successfully.
Aug 18 20:00:16 glide systemd[1]: Finished nexus9000v-monitor.service - Nexus 9000v VM Monitor.
Aug 18 20:00:16 glide systemd[1]: nexus9000v-monitor.service: Consumed 1.119s CPU time.
^C
(n9kv-kvm) arobel@glide:~/repos/n9kv-kvm$
```