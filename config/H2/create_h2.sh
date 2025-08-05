#!/bin/bash

# Script to create a network tools container with libvirt LXC
# Container includes ping, traceroute, traffic generation tools, and zebra

set -e

CONTAINER_NAME="H2"
ROOTFS_PATH="/var/lib/lxc/${CONTAINER_NAME}/rootfs"
CONFIG_PATH="/var/lib/lxc/${CONTAINER_NAME}"
ISL_BRIDGE="BR_L2_H2"
MGMT_BRIDGE="BR_ND_MGMT"
ETH0_IP4="192.168.11.142"
ETH0_IP4_MASK="24"
ETH1_IP4="22.1.1.2"
ETH1_IP4_MASK="30"
GATEWAY_IP4="192.168.11.1"

echo "Creating network tools container: ${CONTAINER_NAME}"

# Create container directory structure
sudo mkdir -p "${CONFIG_PATH}"
sudo mkdir -p "${ROOTFS_PATH}"

# Create a minimal Ubuntu rootfs
echo "Creating Ubuntu rootfs..."
# More robust debootstrap with retries
for attempt in 1 2 3; do
    echo "Attempt $attempt: Creating Ubuntu rootfs..."
    if sudo debootstrap --arch=amd64 --verbose jammy "${ROOTFS_PATH}" http://us.archive.ubuntu.com/ubuntu/; then
        echo "Debootstrap successful on attempt $attempt"
        break
    else
        echo "Debootstrap failed on attempt $attempt"
        if [ $attempt -lt 3 ]; then
            echo "Cleaning up and retrying..."
            sudo rm -rf "${ROOTFS_PATH}"
            sudo mkdir -p "${ROOTFS_PATH}"
            sleep 5
        else
            echo "All debootstrap attempts failed"
            exit 1
        fi
    fi
done

# Chroot into the container and install packages
echo "Installing network tools and zebra..."
sudo chroot "${ROOTFS_PATH}" /bin/bash << 'EOF'
# Set locale to avoid perl warnings
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C
export LANG=C

# Update package list and add universe repository
apt update

# Install software-properties-common first to get add-apt-repository
apt install -y software-properties-common

# Add universe repository
add-apt-repository universe -y
apt update

# Install network tools (removed problematic packages)
apt install -y \
    iputils-ping \
    iputils-tracepath \
    mtr-tiny \
    netcat-openbsd \
    tcpdump \
    curl \
    wget \
    bind9-dnsutils \
    net-tools \
    iproute2 \
    iptables \
    bridge-utils \
    ethtool \
    socat \
    openssh-server \
    vim \
    nano \
    htop \
    frr \
    python3 \
    locales

# Generate locales to fix perl warnings
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8

# Try to install optional packages (don't fail if missing)
apt install -y nmap || echo "nmap not available, skipping"
apt install -y iperf3 || echo "iperf3 not available, skipping" 
apt install -y hping3 || echo "hping3 not available, skipping"
apt install -y vlan || echo "vlan not available, skipping"

# Configure FRR (includes zebra) - check if service exists
if systemctl list-unit-files | grep -q frr.service; then
    systemctl enable frr
else
    echo "FRR service not available, will start manually"
fi

# Create a simple zebra config
mkdir -p /etc/frr
cat > /etc/frr/daemons << 'FRRCFG'
# Zebra is required for any routing protocol
zebra=yes
# Enable OSPF if needed
ospfd=no
# Enable BGP if needed  
bgpd=no
# Enable other daemons as needed
ripd=no
ripngd=no
isisd=no
pimd=no
ldpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
pbrd=no
bfdd=no
fabricd=no
FRRCFG

# Basic zebra configuration
cat > /etc/frr/zebra.conf << 'ZEBRACFG'
! Zebra configuration
hostname H1
password zebra
enable password zebra
!
! Interface configuration
interface eth0
 description Management Interface
 ip address ${ETH0_IP4}/${ETH0_MASK}
!
interface eth1
 description Test Interface
 ip address ${ETH1_IP4}/${ETH1_IP4_MASK}
!
! Static routes
ip route 0.0.0.0/0 ${GATEWAY_IP4} dev eth0
!
log file /var/log/frr/zebra.log
!
line vty
ZEBRACFG

# Set proper permissions (check if frr user exists)
if id "frr" &>/dev/null; then
    chown frr:frr /etc/frr/zebra.conf
    chmod 640 /etc/frr/zebra.conf
else
    echo "FRR user not found, using root ownership"
    chmod 644 /etc/frr/zebra.conf
fi

# Create a network testing script
cat > /usr/local/bin/network-test << 'TESTSCRIPT'
#!/bin/bash
# Network testing script

show_help() {
    echo "Network Testing Tools Container"
    echo "Available commands:"
    echo "  ping <target>          - Ping a target"
    echo "  trace <target>         - Tracepath to target" 
    echo "  mtr <target>           - MTR (traceroute + ping)"
    echo "  iperf-server [port]    - Start iperf3 server (default port 5201)"
    echo "  iperf-client <target>  - Run iperf3 client to target"
    echo "  scan <target>          - Nmap scan target"
    echo "  zebra-cli              - Connect to zebra CLI"
    echo "  show-routes            - Show routing table"
    echo "  show-interfaces        - Show network interfaces"
    echo "  traffic-gen <target>   - Generate traffic with hping3"
    echo "  mgmt-ping <target>     - Ping via management interface"
    echo "  test-ping <target>     - Ping via test interface"
    echo "  show-config            - Show current network configuration"
}

case "$1" in
    "ping")
        ping -c 4 "$2"
        ;;
    "trace")
        tracepath "$2"
        ;;
    "mtr")
        mtr -c 10 "$2"
        ;;
    "iperf-server")
        PORT=${2:-5201}
        echo "Starting iperf3 server on port $PORT"
        iperf3 -s -p "$PORT"
        ;;
    "iperf-client")
        iperf3 -c "$2"
        ;;
    "scan")
        nmap -sP "$2"
        ;;
    "zebra-cli")
        vtysh
        ;;
    "show-routes")
        echo "=== Kernel routing table ==="
        ip route show
        echo ""
        echo "=== FRR routing table ==="
        vtysh -c "show ip route"
        ;;
    "show-interfaces")
        echo "=== Network interfaces ==="
        ip addr show
        echo ""
        echo "=== Interface statistics ==="
        ip -s link show
        ;;
    "traffic-gen")
        hping3 -S -p 80 -c 10 "$2"
        ;;
    "mgmt-ping")
        ping -I eth0 -c 4 "$2"
        ;;
    "test-ping")
        ping -I eth1 -c 4 "$2"
        ;;
    "show-config")
        echo "=== Container Network Configuration ==="
        echo "Management Interface (eth0): ${ETH0_IP4}/${ETH0_IP4_MASK} -> ${MGMT_BRIDGE}"
        echo "Test Interface (eth1): ${ETH1_IP4}/${ETH1_IP4_MASK} -> ${ISL_BRIDGE}"
        echo ""
        echo "=== Current Interface Status ==="
        ip addr show
        echo ""
        echo "=== Current Routes ==="
        ip route show
        ;;
    *)
        show_help
        ;;
esac
TESTSCRIPT

chmod +x /usr/local/bin/network-test

# Create startup script
cat > /usr/local/bin/container-init << 'INITSCRIPT'
#!/bin/bash
# Container initialization script

# Configure network interfaces
echo "Configuring network interfaces..."

# Configure eth0 (management interface)
ip addr add ${ETH0_IP4}/${ETH0_IP4_MASK} dev eth0
ip link set eth0 up

# Configure eth1 (test interface)
ip addr add ${ETH1_IP4}/${ETH1_IP4_MASK} dev eth1
ip link set eth1 up

# Add default route via management interface
ip route add default via ${GATEWAY_IP4} dev eth0

echo "Network configuration:"
ip addr show
ip route show

# Start FRR (check if service exists)
if systemctl list-unit-files | grep -q frr.service; then
    service frr start
else
    echo "FRR service not available, starting zebra manually"
    /usr/lib/frr/zebra -d -f /etc/frr/zebra.conf || echo "Zebra not available"
fi

# Start SSH daemon
service ssh start

# Keep container running
exec /bin/bash
INITSCRIPT

chmod +x /usr/local/bin/container-init

# Clean up
apt clean
rm -rf /var/lib/apt/lists/*

echo "Container rootfs prepared successfully"
EOF

# Find the correct libvirt_lxc emulator path
LIBVIRT_LXC_PATH=$(find /usr -name "libvirt_lxc" 2>/dev/null | head -1)
if [ -z "$LIBVIRT_LXC_PATH" ]; then
    # Try common locations
    if [ -f "/usr/lib/libvirt/libvirt_lxc" ]; then
        LIBVIRT_LXC_PATH="/usr/lib/libvirt/libvirt_lxc"
    elif [ -f "/usr/libexec/libvirt_lxc" ]; then
        LIBVIRT_LXC_PATH="/usr/libexec/libvirt_lxc"
    else
        echo "ERROR: Could not find libvirt_lxc emulator"
        echo "Please install: sudo apt install libvirt-daemon-driver-lxc"
        exit 1
    fi
fi
echo "Using libvirt_lxc emulator at: $LIBVIRT_LXC_PATH"

# Create libvirt XML configuration
echo "Creating libvirt XML configuration..."
cat > "/tmp/${CONTAINER_NAME}.xml" << EOF
<domain type='lxc'>
  <name>${CONTAINER_NAME}</name>
  <memory unit='KiB'>1048576</memory>
  <currentMemory unit='KiB'>1048576</currentMemory>
  <vcpu placement='static'>2</vcpu>
  <os>
    <type arch='x86_64'>exe</type>
    <init>/usr/local/bin/container-init</init>
  </os>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>${LIBVIRT_LXC_PATH}</emulator>
    <filesystem type='mount' accessmode='passthrough'>
      <source dir='${ROOTFS_PATH}'/>
      <target dir='/'/>
    </filesystem>
    <interface type='bridge'>
      <source bridge='${MGMT_BRIDGE}'/>
      <model type='virtio'/>
      <mac address='00:00:42:00:00:01'/>
    </interface>
    <interface type='bridge'>
      <source bridge='${ISL_BRIDGE}'/>
      <model type='virtio'/>
      <mac address='00:00:42:00:00:02'/>
    </interface>
    <console type='pty'>
      <target type='lxc' port='0'/>
    </console>
  </devices>
</domain>
EOF

echo "Libvirt XML configuration created at /tmp/${CONTAINER_NAME}.xml"

# Define the container in libvirt
echo "Defining container in libvirt..."
# Remove existing domain if it exists
sudo virsh -c lxc:/// undefine ${CONTAINER_NAME} 2>/dev/null || true
sudo virsh -c lxc:/// define "/tmp/${CONTAINER_NAME}.xml"

echo ""
echo "Container '${CONTAINER_NAME}' created successfully!"
echo ""
echo "Network Configuration:"
echo "  eth0: ${ETH0_IP4}/${ETH0_IP4_MASK} -> ${MGMT_BRIDGE} (Management)"
echo "  eth1: ${ETH1_IP4}/${ETH1_IP4_MASK} -> ${ISL_BRIDGE} (Test Interface)"
echo ""
echo "To start the container:"
echo "  sudo virsh -c lxc:/// start ${CONTAINER_NAME}"
echo ""
echo "To connect to the container console:"
echo "  sudo virsh -c lxc:/// console ${CONTAINER_NAME}"
echo ""
echo "To autostart the container on boot:"
echo "  sudo virsh -c lxc:/// autostart ${CONTAINER_NAME}"
echo ""
echo "Inside the container, use 'network-test' command for quick network testing"
echo "Available tests:"
echo "  network-test show-config      - Show network configuration"
echo "  network-test mgmt-ping <ip>   - Ping via management interface"
echo "  network-test test-ping <ip>   - Ping via test interface"
echo "  network-test zebra-cli        - Access zebra CLI for routing"