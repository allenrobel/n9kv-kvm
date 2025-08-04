# Install libvirt LXC support

```bash
sudo apt update
sudo apt install libvirt-daemon-driver-lxc libvirt-daemon-system
```

# Restart libvirt to load LXC driver

```bash
sudo systemctl restart libvirtd
```

# Verify LXC driver is available

```bash
sudo virsh -c lxc:/// list
```
