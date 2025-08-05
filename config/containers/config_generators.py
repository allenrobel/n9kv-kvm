#!/usr/bin/env python3
"""
Configuration file generators
"""

from pathlib import Path
from jinja2 import Template

from interfaces import ConfigurationGenerator, CommandExecutor
from models import ContainerSpec

class FRRConfigGenerator(ConfigurationGenerator):
    """Generates FRR configuration files"""
    
    def __init__(self, executor: CommandExecutor) -> None:
        self.executor: CommandExecutor = executor
    
    def generate(self, spec: ContainerSpec, output_path: Path) -> None:
        """Generate FRR configuration"""
        frr_path: Path = output_path / "etc" / "frr"
        
        self._create_frr_directory(frr_path)
        self._generate_daemons_config(frr_path)
        self._generate_zebra_config(spec, frr_path)
    
    def _create_frr_directory(self, frr_path: Path) -> None:
        """Create FRR configuration directory"""
        self.executor.run(['sudo', 'mkdir', '-p', str(frr_path)])
    
    def _generate_daemons_config(self, frr_path: Path) -> None:
        """Generate FRR daemons configuration"""
        daemons_config = """zebra=yes
ospfd=no
bgpd=no
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
"""
        
        daemons_file: Path = frr_path / "daemons"
        self.executor.run(['sudo', 'tee', str(daemons_file)], 
                         input_text=daemons_config)
    
    def _generate_zebra_config(self, spec: ContainerSpec, frr_path: Path) -> None:
        """Generate Zebra configuration"""
        zebra_template = Template("""
! Zebra configuration
hostname {{ spec.name }}
password zebra
enable password zebra
!
! Management interface
interface {{ spec.management_interface.name }}
 description {{ spec.management_interface.description }}
 ip address {{ spec.management_interface.ip_address }}/{{ spec.management_interface.netmask }}
!
{% for vlan in spec.vlans %}
! VLAN {{ vlan.vlan_id }} interface
interface {{ spec.test_interface.name }}.{{ vlan.vlan_id }}
 description {{ vlan.description }}
 ip address {{ vlan.ip_address }}/{{ vlan.netmask }}
!
{% endfor %}
! Static routes
ip route 0.0.0.0/0 {{ spec.gateway_ip }}
!
log file /var/log/frr/zebra.log
!
line vty
""")
        
        zebra_config: str = zebra_template.render(spec=spec)
        zebra_file: Path = frr_path / "zebra.conf"
        
        self.executor.run(['sudo', 'tee', str(zebra_file)], 
                         input_text=zebra_config)
        self.executor.run(['sudo', 'chmod', '644', str(zebra_file)])

class NetworkTestScriptGenerator(ConfigurationGenerator):
    """Generates network testing script"""
    
    def __init__(self, executor: CommandExecutor) -> None:
        self.executor: CommandExecutor = executor
    
    def generate(self, spec: ContainerSpec, output_path: Path) -> None:
        """Generate network testing script"""
        script_template = Template("""#!/bin/bash
# Network testing script for {{ spec.name }}

show_help() {
    echo "Network Testing Tools Container - {{ spec.name }}"
    echo "Available commands:"
    echo "  ping <target>              - Ping a target"
    echo "  trace <target>             - Tracepath to target"
    echo "  mtr <target>               - MTR (traceroute + ping)"
    echo "  iperf-server [port]        - Start iperf3 server"
    echo "  iperf-client <target>      - Run iperf3 client to target"
    echo "  scan <target>              - Nmap scan target"
    echo "  zebra-cli                  - Connect to zebra CLI"
    echo "  show-routes                - Show routing table"
    echo "  show-interfaces            - Show network interfaces"
    echo "  show-vlans                 - Show VLAN interfaces"
    echo "  traffic-gen <target>       - Generate traffic with hping3"
    echo "  mgmt-ping <target>         - Ping via management interface"
{% for vlan in spec.vlans %}
    echo "  vlan{{ vlan.vlan_id }}-ping <target>      - Ping via VLAN {{ vlan.vlan_id }} interface"
{% endfor %}
    echo "  show-config                - Show current network configuration"
}

case "$1" in
    "ping") ping -c 4 "$2" ;;
    "trace") tracepath "$2" ;;
    "mtr") mtr -c 10 "$2" ;;
    "iperf-server")
        PORT=$${2:-5201}
        echo "Starting iperf3 server on port $$PORT"
        iperf3 -s -p "$$PORT" ;;
    "iperf-client") iperf3 -c "$2" ;;
    "scan") nmap -sP "$2" ;;
    "zebra-cli") vtysh ;;
    "show-routes")
        echo "=== Kernel routing table ==="
        ip route show
        echo ""
        echo "=== FRR routing table ==="
        vtysh -c "show ip route" ;;
    "show-interfaces")
        echo "=== Network interfaces ==="
        ip addr show
        echo ""
        echo "=== Interface statistics ==="
        ip -s link show ;;
    "show-vlans")
        echo "=== VLAN interfaces ==="
{% for vlan in spec.vlans %}
        ip addr show {{ spec.test_interface.name }}.{{ vlan.vlan_id }} 2>/dev/null || echo "{{ spec.test_interface.name }}.{{ vlan.vlan_id }} not configured"
{% endfor %}
        ;;
    "traffic-gen") hping3 -S -p 80 -c 10 "$2" ;;
    "mgmt-ping") ping -I {{ spec.management_interface.name }} -c 4 "$2" ;;
{% for vlan in spec.vlans %}
    "vlan{{ vlan.vlan_id }}-ping") ping -I {{ spec.test_interface.name }}.{{ vlan.vlan_id }} -c 4 "$2" ;;
{% endfor %}
    "show-config")
        echo "=== Container Network Configuration ==="
        echo "Management Interface ({{ spec.management_interface.name }}): {{ spec.management_interface.ip_address }}/{{ spec.management_interface.netmask }} -> {{ spec.management_interface.bridge }}"
{% for vlan in spec.vlans %}
        echo "VLAN {{ vlan.vlan_id }} Interface ({{ spec.test_interface.name }}.{{ vlan.vlan_id }}): {{ vlan.ip_address }}/{{ vlan.netmask }} -> {{ spec.test_interface.bridge }}"
{% endfor %}
        echo ""
        echo "=== Current Interface Status ==="
        ip addr show
        echo ""
        echo "=== Current Routes ==="
        ip route show ;;
    *) show_help ;;
esac
""")
        
        script_content: str = script_template.render(spec=spec)
        script_path: Path = output_path / "usr" / "local" / "bin" / "network-test"
        
        self.executor.run(['sudo', 'mkdir', '-p', str(script_path.parent)])
        self.executor.run(['sudo', 'tee', str(script_path)], 
                         input_text=script_content)
        self.executor.run(['sudo', 'chmod', '+x', str(script_path)])

class ContainerInitScriptGenerator(ConfigurationGenerator):
    """Generates container initialization script"""
    
    def __init__(self, executor: CommandExecutor) -> None:
        self.executor: CommandExecutor = executor
    
    def generate(self, spec: ContainerSpec, output_path: Path) -> None:
        """Generate container init script"""
        init_template = Template("""#!/bin/bash
# Container initialization script for {{ spec.name }}

echo "Initializing container {{ spec.name }}..."

# Configure management interface
echo "Configuring management interface..."
ip addr add {{ spec.management_interface.ip_address }}/{{ spec.management_interface.netmask }} dev {{ spec.management_interface.name }}
ip link set {{ spec.management_interface.name }} up

# Configure VLAN interfaces
{% for vlan in spec.vlans %}
echo "Configuring VLAN {{ vlan.vlan_id }} interface..."
ip link add link {{ spec.test_interface.name }} name {{ spec.test_interface.name }}.{{ vlan.vlan_id }} type vlan id {{ vlan.vlan_id }}
ip addr add {{ vlan.ip_address }}/{{ vlan.netmask }} dev {{ spec.test_interface.name }}.{{ vlan.vlan_id }}
ip link set {{ spec.test_interface.name }}.{{ vlan.vlan_id }} up
{% endfor %}

# Bring up base test interface
ip link set {{ spec.test_interface.name }} up

# Add default route
ip route add default via {{ spec.gateway_ip }} dev {{ spec.management_interface.name }}

echo "Network configuration complete:"
ip addr show

# Start FRR
if systemctl list-unit-files | grep -q frr.service; then
    service frr start
    echo "FRR started"
else
    echo "Starting zebra manually"
    /usr/lib/frr/zebra -d -f /etc/frr/zebra.conf || echo "Zebra not available"
fi

# Start SSH daemon
service ssh start
echo "SSH daemon started"

echo "Container {{ spec.name }} initialized successfully"

# Keep container running
exec /bin/bash
""")
        
        init_content: str = init_template.render(spec=spec)
        init_path: Path = output_path / "usr" / "local" / "bin" / "container-init"
        
        self.executor.run(['sudo', 'tee', str(init_path)], 
                         input_text=init_content)
        self.executor.run(['sudo', 'chmod', '+x', str(init_path)])