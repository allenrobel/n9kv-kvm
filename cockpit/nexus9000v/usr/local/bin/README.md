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

## 3. Test to see that it's working

- sudo python3 /usr/local/bin/nexus9000v_monitor.py --table

```bash
root@cvd-2:~# sudo python3 /usr/local/bin/nexus9000v_monitor.py --table
2025-07-26 02:39:06,594 - INFO - Scanning for Nexus 9000v VMs...
2025-07-26 02:39:06,781 - INFO - Found VM: ER (PID: 30813)
VM NAME              PID      CPU%     MEM(MB)    UPTIME          STATUS    
--------             ---      ----     -------    -------         ------    
ER                   30813    43.4     14162      1d 1h 37m       running   
root@cvd-2:~# 
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

## 8. View logs

```bash
sudo journalctl -u nexus9000v-monitor.service -f
```
