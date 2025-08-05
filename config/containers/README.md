# Modular Network Container Management System

A Python-based system for creating and managing libvirt LXC containers with VLAN support, following SOLID principles and enterprise best practices.

## Architecture

### 🏗️ **SOLID Principles Applied**

- **Single Responsibility**: Each class has one focused purpose
- **Open/Closed**: Extensible through interfaces and factories
- **Liskov Substitution**: All implementations are interchangeable
- **Interface Segregation**: Minimal, focused interfaces
- **Dependency Inversion**: High-level modules depend on abstractions

### 📁 **Module Structure**

```bash
├── models.py              # Data models (VLANConfig, ContainerSpec)
├── interfaces.py          # Protocols and abstract base classes
├── executor.py            # Command execution implementation
├── filesystem.py          # File system operations
├── bridge.py              # Bridge VLAN management
├── rootfs.py              # Container rootfs creation
├── packages.py            # Package installation
├── config_generators.py   # Configuration file generators
├── libvirt_manager.py     # Libvirt XML and domain management
├── orchestrator.py        # Main orchestration logic
├── factory.py             # Dependency injection factory
├── requirements.py        # System requirements checking
├── main.py                # CLI entry point
├── setup.py               # Installation script
└── README.md              # This documentation
```

## Features

### 🌐 **Network Configuration**

- **Dual-homed containers**: Management + test interfaces
- **VLAN support**: 802.1Q tagging with bridge filtering
- **Automatic bridge configuration**: VLAN filtering enabled
- **Per-VLAN IP addressing**: Clean separation of traffic

### 🔧 **Container Capabilities**

- **FRR/Zebra routing**: OSPF, BGP support ready
- **Comprehensive testing tools**: ping, traceroute, mtr, iperf3, nmap
- **VLAN-specific testing**: Per-VLAN ping and traffic generation
- **SSH access**: Remote management capability

### 💻 **Development Quality**

- **Full type hints**: Complete type safety
- **Comprehensive logging**: Detailed operation tracking
- **Error handling**: Graceful failure recovery
- **Modular testing**: Each component easily unit testable

## Quick Start

### 1. Installation

```bash
# Clone/download the files to a directory
# Run the setup script
python3 setup.py
```

### 2. Verify Installation

```bash
python3 main.py --check
```

### 3. Create Containers

```bash
# Create H1 container
python3 main.py create-h1

# Create H2 container  
python3 main.py create-h2
```

## Container Specifications

### H1 Container

- **Management**: 192.168.11.141/24 on BR_ND_MGMT
- **VLAN 2**: 11.1.2.141/24 on BR_L1_H1 (eth1.2)
- **VLAN 3**: 11.1.3.141/30 on BR_L1_H1 (eth1.3)

### H2 Container

- **Management**: 192.168.11.142/24 on BR_ND_MGMT
- **VLAN 2**: 11.1.2.142/30 on BR_L1_H1 (eth1.2)
- **VLAN 3**: 11.1.3.142/30 on BR_L1_H1 (eth1.3)

## Usage Examples

### Container Management

```bash
# Start container
sudo virsh -c lxc:/// start H1

# Connect to console (use Ctrl+] to disconnect)
sudo virsh -c lxc:/// console H1

# Check status
sudo virsh -c lxc:/// list

# Stop container
sudo virsh -c lxc:/// shutdown H1
```

### Network Testing (Inside Container)

```bash
# Show configuration
network-test show-config

# Test management connectivity
network-test mgmt-ping 192.168.11.1

# Test VLAN connectivity
network-test vlan2-ping 11.1.1.2    # Ping H2 on VLAN 2
network-test vlan3-ping 11.1.1.6    # Ping H2 on VLAN 3

# Show VLAN interfaces
network-test show-vlans

# Access routing configuration
network-test zebra-cli

# Traffic generation
network-test iperf-server            # Start server
network-test iperf-client 11.1.1.2  # Connect to target
```

### Bridge VLAN Verification

```bash
# Check bridge VLAN configuration
bridge vlan show dev BR_L1_H1

# Should show VLANs 2 and 3 configured
```

## Extension Guide

### Adding New Container Types

#### 1. **Create specification** in `main.py`

```python
@staticmethod
def create_h3_spec() -> ContainerSpec:
    return ContainerSpec(
        name="H3",
        management_interface=NetworkInterface(...),
        test_interface=NetworkInterface(...),
        vlans=[...],
        gateway_ip="192.168.11.1"
    )
```

#### 2. **Add CLI option** in `main.py`

```python
parser.add_argument('action', choices=['create-h1', 'create-h2', 'create-h3'])
```

### Adding New Configuration Generators

#### 1. **Create generator class**

```python
class MyConfigGenerator(ConfigurationGenerator):
    def generate(self, spec: ContainerSpec, output_path: Path) -> None:
        # Implementation
```

#### 2. **Register in factory**

```python
config_generators.append(MyConfigGenerator(executor))
```

## System Requirements

- **OS**: Ubuntu 20.04+ or Debian 11+
- **Python**: 3.10+
- **Privileges**: sudo access for container operations
- **Memory**: 4GB+ recommended for multiple containers
- **Disk**: 2GB+ free space per container

## Dependencies

### System Packages

- `debootstrap` - Ubuntu rootfs creation
- `libvirt-daemon-driver-lxc` - LXC support for libvirt
- `libvirt-daemon-system` - Libvirt system daemon
- `bridge-utils` - Bridge management tools

### Python Packages

- `jinja2>=3.1.0` - Template engine for configuration generation

## Troubleshooting

### Common Issues

#### 1. Permission Denied Errors

```bash
# Ensure user is in libvirt group
sudo usermod -aG libvirt $USER
# Log out and back in for changes to take effect
```

#### 2. Bridge Not Found

```bash
# Create required bridges manually if they don't exist
sudo ip link add name BR_ND_MGMT type bridge
sudo ip link add name BR_L1_H1 type bridge
sudo ip link set BR_ND_MGMT up
sudo ip link set BR_L1_H1 up
```

#### 3. VLAN Filtering Issues

```bash
# Check if VLAN filtering is enabled
bridge vlan show

# Manually enable if needed
sudo ip link set BR_L1_H1 type bridge vlan_filtering 1
```

#### 4. Container Won't Start

```bash
# Check libvirt logs
sudo journalctl -u libvirtd -f

# Verify container definition
sudo virsh -c lxc:/// dumpxml H1
```

#### 5. Network Connectivity Issues

- Verify bridge configuration: `brctl show`
- Check VLAN interfaces inside container: `ip addr show`
- Verify routing table: `ip route show`

### Debug Mode

Enable debug logging by modifying the logging level in any module:

```python
logging.basicConfig(level=logging.DEBUG)
```

## Performance Considerations

### Resource Usage

- **Memory**: Each container uses ~1GB RAM by default
- **CPU**: 2 vCPUs per container (adjustable in ContainerSpec)
- **Storage**: ~2GB per container rootfs

### Scaling

- **Maximum containers**: Limited by host resources
- **Network performance**: Depends on bridge configuration
- **VLAN limits**: 4094 VLANs supported per bridge

## Security Considerations

### Default Security

- Containers run with default LXC security
- SSH enabled with default credentials
- No firewall rules configured

### Production Hardening

```bash
# Change default passwords
# Inside container:
passwd root
passwd admin

# Configure SSH keys instead of passwords
# Configure iptables rules
# Enable AppArmor/SELinux profiles
```

## Contributing

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for all functions and variables
- Write docstrings for all public methods
- Maintain SOLID principles

### Testing

```bash
# Run type checking
mypy *.py

# Run unit tests (when implemented)
python -m pytest tests/
```

### Adding Features

1. Create feature branch
2. Implement following SOLID principles
3. Add type hints and documentation
4. Test thoroughly
5. Submit pull request

## License

This project is provided as-is for educational and development purposes.

## Changelog

### v2.0.0 - Modular Architecture

- **Breaking**: Refactored monolithic system into focused modules
- **Added**: Full SOLID principles compliance
- **Added**: Comprehensive type hints throughout
- **Added**: Modular configuration generators
- **Added**: Factory pattern for dependency injection
- **Improved**: Error handling and logging
- **Improved**: Code maintainability and testability

### v1.0.0 - Initial Python Version

- **Added**: Python-based container creation
- **Added**: VLAN support with bridge filtering
- **Added**: FRR/Zebra integration
- **Added**: Network testing tools
- **Added**: Template-based configuration generation

---

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Review system requirements and dependencies
3. Enable debug logging for detailed error information
4. Check libvirt and system logs for additional context

---

*This system provides a solid foundation for network testing environments with clean, maintainable, and extensible Python code following enterprise best practices.*
