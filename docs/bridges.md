# Setup Bridges

## Configure qemu to allow the bridges used in this project

You may have to create the `/etc/qemu` directory first.

```bash
# Check if the directory exists
ls -ld /etc/qemu
# If it doesn't exist, create it.
sudo mkdir /etc/qemu
```

If `/etc/qemu/bridge.conf` already exists on your host, then append
the contents of `./config/bridges/bridge.conf` to your existing file.

```bash
# Check if /etc/qemu/bridge.conf exists
sudo cat /etc/qemu/bridge.conf
# If it does exist, append to it, rather than overwrite it.
sudo cat $HOME/repos/n9kv-kvm/config/bridges/bridge.conf >> /etc/qemu/bridge.conf
# Verify things look OK
sudo cat /etc/qemu/bridge.conf
```

It `/etc/qemu/bridge.conf` doesn't exist, create it.

```bash
sudo cp $HOME/repos/n9kv-kvm/config/bridges/bridge.conf /etc/qemu/bridge.conf
sudo chmod 600 /etc/qemu/bridge.conf
```

## Configure netplan

Inspect and edit the following file to ensure it will work
for you.

```bash
$HOME/repos/n9kv-kvm/config/bridges/99-bridges.yaml
```

In particular, verify that:

- The physical interface exists. You'll likely need to change
  the interface name (`enp34s0f0` below) to match your host
  (see the `link` parameter for `Vlan11` and `Vlan12` below).
  To check your interfaces e.g. `ip link show`.
- Vlans 11 and 12 are not already associated with your
  interface (the `id` parameter for `Vlan11` and `Vlan12` below).
- The bridge names (e.g. `BR_ND_MGMT`, `BR_ER_S1`, etc) don't conflict
  with existing bridges on your host.
- The ip addresses (`192.168.11.1/24` and `192.168.12.1/24`) don't
  conflict with other addresses on your host, or with addresses in
  your network that your host needs to reach.

```yaml
  vlans:
    Vlan11:
      id: 11
      link: enp34s0f0
      optional: true
    Vlan12:
      id: 12
      link: enp34s0f0
      optional: true
```

## Copy the bridges configuration into /etc/netplan

```bash
cd $HOME/repos/n9kv-kvm/config/bridges
sudo cp ./99-bridges.yaml /etc/netplan
sudo chmod 600 /etc/netplan/99-bridges.yaml
```

## Apply the bridges configuration

```bash
netplan try
netplan apply
```

The above commands might result in a warning similar to below.

```bash
** (process:37526): WARNING **: 18:03:28.923: Permissions for /etc/netplan/00-installer-config.yaml are too open. Netplan configuration should NOT be accessible by others.
```

If so, modify the permissions of the files in `/etc/netplan` as follows
and try to apply the bridges configuration again.

```bash
sudo chown root /etc/netplan/*
sudo chmod 600 /etc/netplan/*
```

If the above commands result in messages like the following, you can ignore them.

```bash
(.venv) arobel@cvd-3:~/repos/n9kv-kvm/config/bridges$ sudo netplan try
BR_ER_S2: reverting custom parameters for bridges and bonds is not supported
BR_ER_S1: reverting custom parameters for bridges and bonds is not supported
BR_ND_DATA: reverting custom parameters for bridges and bonds is not supported
BR_ND_MGMT: reverting custom parameters for bridges and bonds is not supported
BR_S2_L1: reverting custom parameters for bridges and bonds is not supported
br0: reverting custom parameters for bridges and bonds is not supported
BR_S1_L1: reverting custom parameters for bridges and bonds is not supported

Please carefully review the configuration and use 'netplan apply' directly.
```

## Verify netplan was applied correctly

- ip link show type bridge | grep BR_

Some bridges (e.g. `BR_ER_S1`) will show `state DOWN`. This is expected until we bringup,
the nexus9000v switches.

```bash
(.venv) arobel@cvd-3:~/repos/n9kv-kvm/config/bridges$ ip link show type bridge | grep BR_
10: BR_ER_S1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 9216 qdisc noqueue state DOWN mode DEFAULT group default qlen 1000
11: BR_ER_S2: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 9216 qdisc noqueue state DOWN mode DEFAULT group default qlen 1000
12: BR_ND_DATA: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default qlen 1000
13: BR_ND_MGMT: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default qlen 1000
14: BR_S1_L1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 9216 qdisc noqueue state DOWN mode DEFAULT group default qlen 1000
15: BR_S2_L1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 9216 qdisc noqueue state DOWN mode DEFAULT group default qlen 1000
(.venv) arobel@cvd-3:~/repos/n9kv-kvm/config/bridges$
```
