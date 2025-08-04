#!/bin/bash

# Container management script for libvirt LXC

CONTAINER_NAME="H1"
LXC_URI="lxc:///"
XML=$CONTAINER_NAME.xml

show_help() {
    echo "Container Management Script"
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  create              - Create the container (run setup script first)"
    echo "  start               - Start the container"
    echo "  stop                - Stop the container"
    echo "  console             - Connect to container console"
    echo "  status              - Show container status"
    echo "  autostart [on|off]  - Enable/disable autostart"
    echo "  destroy             - Remove container definition"
    echo "  ip                  - Show container IP address"
    echo "  exec <command>      - Execute command in container"
    echo "  list                - List all LXC containers"
    echo ""
    echo "Network testing (inside container):"
    echo "  test mgmt-ping <target>    - Ping via management interface"
    echo "  test test-ping <target>    - Ping via test interface"
    echo "  test iperf-server          - Start iperf3 server"
    echo "  test zebra                 - Access zebra CLI"
    echo "  test show-config           - Show network configuration"
    echo ""
    echo "Example workflow:"
    echo "  1. Run ./create_h1.sh first"
    echo "  2. $0 start"
    echo "  3. $0 console"
}

case "$1" in
    "create")
        echo "Defining container from XML..."
        if [ -f "$XML" ]; then
            sudo virsh -c $LXC_URI define "$XML"
            echo "Container '$CONTAINER_NAME' defined successfully"
        else
            echo "ERROR: $XML not found"
            echo "Run ./create_h1.sh first"
            exit 1
        fi
        ;;
    
    "start")
        echo "Starting container '$CONTAINER_NAME'..."
        sudo virsh -c $LXC_URI start $CONTAINER_NAME
        echo "Container started. Use '$0 console' to connect."
        ;;
    
    "stop")
        echo "Stopping container '$CONTAINER_NAME'..."
        sudo virsh -c $LXC_URI shutdown $CONTAINER_NAME
        ;;
    
    "console")
        echo "Connecting to container console..."
        echo "Press Ctrl+] to disconnect"
        sudo virsh -c $LXC_URI console $CONTAINER_NAME
        ;;
    
    "status")
        sudo virsh -c $LXC_URI dominfo $CONTAINER_NAME
        ;;
    
    "autostart")
        if [ "$2" = "off" ]; then
            sudo virsh -c $LXC_URI autostart --disable $CONTAINER_NAME
            echo "Autostart disabled for '$CONTAINER_NAME'"
        else
            sudo virsh -c $LXC_URI autostart $CONTAINER_NAME
            echo "Autostart enabled for '$CONTAINER_NAME'"
        fi
        ;;
    
    "destroy")
        echo "Removing container definition..."
        sudo virsh -c $LXC_URI undefine $CONTAINER_NAME
        echo "Container '$CONTAINER_NAME' undefined"
        echo "Note: Rootfs still exists at /var/lib/lxc/$CONTAINER_NAME/"
        ;;
    
    "ip")
        echo "Container network information:"
        sudo virsh -c $LXC_URI domifaddr $CONTAINER_NAME 2>/dev/null || {
            echo "Container may not be running or IP not assigned via DHCP"
            echo "Try connecting to console and running 'ip addr show'"
        }
        ;;
    
    "exec")
        if [ -z "$2" ]; then
            echo "Usage: $0 exec <command>"
            exit 1
        fi
        shift
        echo "Executing command in container: $*"
        # Note: libvirt LXC doesn't have direct exec like Docker
        # You'll need to use console or SSH
        echo "Use '$0 console' and run the command manually"
        echo "Or configure SSH access to the container"
        ;;
    
    "list")
        echo "LXC containers:"
        sudo virsh -c $LXC_URI list --all
        ;;
    
    "test")
        case "$2" in
            "mgmt-ping")
                if [ -z "$3" ]; then
                    echo "Usage: $0 test mgmt-ping <target>"
                    exit 1
                fi
                echo "Connect to console and run: network-test mgmt-ping $3"
                ;;
            "test-ping")
                if [ -z "$3" ]; then
                    echo "Usage: $0 test test-ping <target>"
                    exit 1
                fi
                echo "Connect to console and run: network-test test-ping $3"
                ;;
            "iperf-server")
                echo "Connect to console and run: network-test iperf-server"
                ;;
            "zebra")
                echo "Connect to console and run: network-test zebra-cli"
                ;;
            "show-config")
                echo "Connect to console and run: network-test show-config"
                ;;
            *)
                echo "Available tests: mgmt-ping, test-ping, iperf-server, zebra, show-config"
                ;;
        esac
        ;;
    
    *)
        show_help
        exit 1
        ;;
esac