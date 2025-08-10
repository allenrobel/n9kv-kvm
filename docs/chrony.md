# Install and Configure chrony

## Skip if not needed

If you already have an external time server, feel free to skip the below and use
your external server during Nexus Dashboard installation.

## Install chrony

ND requires a reachable NTP service.  `chrony` is very lightweight so will
serve our purposes nicely. To install `chrony`, do the following.

```bash
sudo apt install chrony
```

## Configure chrony

The chrony configuration file is located here:

`/etc/chrony/chrony.conf`

The only things we need to add/modify in the chrony configuration are:

- `allow`
  - Enable chrony to function as an Network Time Protocol server
  - Limit NTP reponses to the the subnet ranges for our project
- `local stratum 15`
  - Synchronize to any time source with a lower (i.e. a better) stratum than 15
- `server` Use this if you want to use a specific NTP server as a time source
  - iburst is optional and tells chrony to send a burst of NTP requests to the
    time source for faster synchronization
- `pool` Use this if you want to use a pool of servers as a time source

In my case, there's an NTP server in the lab so I'm using that.

```bash
server 10.1.2.3 iburst
allow 192.168.11.0/24
allow 192.168.12.0/24
local stratum 15
```

Once you've edited `/etc/chrony/chrony.conf` with your changes, restart the
service (or stop and start it).  You may have to stop/start twice if you are
using a server instead of a pool (don't ask me why!).

## Start chrony

```bash
sudo service chrony stop
sudu service chrony start
```

## Verify chrony Status

Check the status

- sudo chrony status

You should see in the startup log that a source was selected e.g.

```bash
sudo service chrony status
<stuff removed>
Jul 28 00:02:35 cvd-2 chronyd[202142]: Selected source 10.1.2.3
```

## Manage chrony

You can use the `chronyc` command to monitor `chrony`.  For example,
if `Leap status` shows `Not synchronized`, then chrony has not yet
synced with your chosen time source.

```bash
(n9kv-kvm) arobel@cvd-2:~/repos/n9kv-kvm$ chronyc tracking
Reference ID    : 0A12BE01 (_gateway)
Stratum         : 4
Ref time (UTC)  : Mon Jul 28 00:04:46 2025
System time     : 0.000004790 seconds fast of NTP time
Last offset     : +0.000015556 seconds
RMS offset      : 0.000008368 seconds
Frequency       : 1.498 ppm fast
Residual freq   : +0.079 ppm
Skew            : 0.040 ppm
Root delay      : 0.001343844 seconds
Root dispersion : 0.002986593 seconds
Update interval : 64.4 seconds
Leap status     : Normal
(n9kv-kvm) arobel@cvd-2:~/repos/n9kv-kvm$
```
