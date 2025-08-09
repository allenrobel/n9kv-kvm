# Install dnsmasq

Nexus Dashboard requires a reachable DNS server.  Since we are assuming that everything
is local to your host on non-public IPs, we'll use dnsmasq since it's pretty
light weight.

```bash
sudo apt update
sudo apt install dnsmasq
```

## Edit /etc/dnsmasq.conf

We'll need to modify some lines in `/etc/dnsmasq.conf`

We'll modify this with just enough changes for our project. Specifically:

- `port=` Listen on the standard port 53
- `server=` Configure upstream DNS servers to forward queries to
  - Cloudflare (1.1.1.1)
  - Google (8.8.8.8)
- `no-hosts` do not read /etc/hosts
- `listen-address=` Bind to and listen for requests from Vlan11 and Vlan12 interfaces
  - For reasons I don't understand, using `interface=` multiple times resulted in dnsmasq errors...
  - Hence, using `listen-address` instead.  This results in the same functionality.
- `no-dhcp-interface` Disable dnsmasq DHCP on all interfaces (ND provides this service)
- `cache-size` Specify cache size (default is 150)

```bash
port=53
no-hosts
server=1.1.1.1
server=8.8.8.8
cache-size=1000
listen-address=192.168.11.1
listen-address=192.168.12.1
no-dhcp-interface=*
```

## Edit /etc/default/dnsmasq

This file is specific to Ubuntu.  Uncomment and set the following options in this file.

- `IGNORE_RESOLVCONF`
  - Even though we set `server=` above, this is not enough on Ubuntu
  - We also need to set `IGNORE_RESOLVCONF=yes` so that dnsmasq does not try to read a non-existent /run/dnsmasq/resolv.conf
- `DNSMASQ_EXCEPT`
  - Without setting `DNSMASQ_EXCEPT="lo"` you'll get the following error in `service dnsmasq status`
  - resolvconf[6641]: Failed to set DNS configuration: Link lo is loopback device.

```bash
IGNORE_RESOLVCONF=yes
DNSMASQ_EXCEPT="lo"
```

## Start the dnsmasq service

```bash
sudo service dnsmasq start
```

## Check service dnsmasq status for any errors

- sudo service dnsmasq status

```bash
arobel@cvd-2:~$ sudo service dnsmasq status
[sudo] password for arobel:
● dnsmasq.service - dnsmasq - A lightweight DHCP and caching DNS server
     Loaded: loaded (/usr/lib/systemd/system/dnsmasq.service; enabled; preset: enabled)
     Active: active (running) since Mon 2025-07-28 02:44:27 UTC; 17min ago
    Process: 210061 ExecStartPre=/usr/share/dnsmasq/systemd-helper checkconfig (code=exited, status=0/SUCCESS)
    Process: 210067 ExecStart=/usr/share/dnsmasq/systemd-helper exec (code=exited, status=0/SUCCESS)
    Process: 210074 ExecStartPost=/usr/share/dnsmasq/systemd-helper start-resolvconf (code=exited, status=0/SUCCESS)
   Main PID: 210072 (dnsmasq)
      Tasks: 1 (limit: 618896)
     Memory: 840.0K (peak: 3.6M)
        CPU: 79ms
     CGroup: /system.slice/dnsmasq.service
             └─210072 /usr/sbin/dnsmasq -x /run/dnsmasq/dnsmasq.pid -u dnsmasq -I lo -7 /etc/dnsmasq.d,.dpkg-dist,.dpkg-old,.dpkg>

Jul 28 02:44:27 cvd-2 dnsmasq[210072]: started, version 2.90 cachesize 1000
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: compile time options: IPv6 GNU-getopt DBus no-UBus i18n IDN2 DHCP DHCPv6 no-Lua TFTP connt>
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: using nameserver 1.1.1.1#53
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: using nameserver 8.8.8.8#53
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: reading /etc/resolv.conf
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: using nameserver 1.1.1.1#53
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: using nameserver 8.8.8.8#53
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: using nameserver 127.0.0.53#53
Jul 28 02:44:27 cvd-2 dnsmasq[210072]: cleared cache
Jul 28 02:44:27 cvd-2 systemd[1]: Started dnsmasq.service - dnsmasq - A lightweight DHCP and caching DNS server.
arobel@cvd-2:~$
```
