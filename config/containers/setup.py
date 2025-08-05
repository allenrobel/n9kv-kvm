#!/usr/bin/env python3
"""
Setup script for modular container management system
"""

import subprocess
import sys
from pathlib import Path

def install_system_dependencies():
    """Install required system packages"""
    packages = [
        'debootstrap',
        'libvirt-daemon-driver-lxc', 
        'libvirt-daemon-system',
        'bridge-utils',
        'python3-pip'
    ]
    
    print("Installing system dependencies...")
    try:
        subprocess.run(['sudo', 'apt', 'update'], check=True)
        subprocess.run(['sudo', 'apt', 'install', '-y'] + packages, check=True)
        subprocess.run(['sudo', 'systemctl', 'restart', 'libvirtd'], check=True)
        print("✓ System dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install system dependencies: {e}")
        return False

def install_python_dependencies():
    """Install Python dependencies"""
    print("Installing Python dependencies...")
    try:
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'jinja2>=3.1.0'
        ], check=True)
        print("✓ Python dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install Python dependencies: {e}")
        return False

def main():
    print("Container Management System Setup")
    print("=" * 40)
    
    if not install_system_dependencies():
        return 1
    
    if not install_python_dependencies():
        return 1
    
    print(f"\n{'='*50}")
    print("Setup completed successfully!")
    print(f"{'='*50}")
    print("\nUsage:")
    print("  python3 main.py --check         # Check requirements")
    print("  python3 main.py create-h1       # Create H1 container")
    print("  python3 main.py create-h2       # Create H2 container")
    print("\nFeatures:")
    print("  ✓ Modular, SOLID-compliant architecture")
    print("  ✓ Full type hints and error handling")
    print("  ✓ VLAN support with bridge filtering")
    print("  ✓ FRR/Zebra routing protocol support")
    print("  ✓ Comprehensive network testing tools")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())