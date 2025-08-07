#!/usr/bin/env python3
"""
Main CLI for container management system
"""

import argparse
import logging
import sys

from executor import SystemCommandExecutor
from factory import ContainerSystemFactory
from models import ContainerSpec, NetworkInterface, VLANConfig
from requirements import RequirementsChecker

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ContainerSpecFactory:
    """Factory for creating container specifications"""

    @staticmethod
    def create_h1_spec() -> ContainerSpec:
        """Create H1 container specification"""
        return ContainerSpec(
            name="H1",
            management_interface=NetworkInterface(
                name="eth0",
                ip_address="192.168.12.141",
                netmask="24",
                bridge="BR_ND_DATA",
                mac_address="00:00:41:00:00:01",
                description="Management Interface",
            ),
            test_interface=NetworkInterface(
                name="eth1",
                ip_address="11.1.2.141",
                netmask="24",
                bridge="BR_L1_H1",
                mac_address="00:00:41:00:00:02",
                description="Test Interface",
            ),
            vlans=[],
            gateway_ip="192.168.12.1",
        )

    @staticmethod
    def create_h2_spec() -> ContainerSpec:
        """Create H2 container specification"""
        return ContainerSpec(
            name="H2",
            management_interface=NetworkInterface(
                name="eth0",
                ip_address="192.168.12.142",
                netmask="24",
                bridge="BR_ND_DATA",
                mac_address="00:00:42:00:00:01",
                description="Management Interface",
            ),
            test_interface=NetworkInterface(
                name="eth1",
                ip_address="11.1.2.142",
                netmask="24",
                bridge="BR_L2_H2",
                mac_address="00:00:42:00:00:02",
                description="Test Interface",
            ),
            vlans=[],
            gateway_ip="192.168.12.1",
        )


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Modular Network Container Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py --check         # Check requirements
  python3 main.py create-h1       # Create H1 container
  python3 main.py create-h2       # Create H2 container
        """,
    )

    parser.add_argument(
        "action",
        nargs="?",
        choices=["create-h1", "create-h2"],
        help="Action to perform",
    )

    parser.add_argument(
        "--check", action="store_true", help="Check system requirements only"
    )

    args = parser.parse_args()

    # Create dependencies
    executor = SystemCommandExecutor()
    requirements_checker = RequirementsChecker(executor)

    # Check requirements
    if args.check or not requirements_checker.check_all_requirements():
        return 0 if args.check and requirements_checker.check_all_requirements() else 1

    if not args.action:
        parser.print_help()
        return 1

    try:
        # Create orchestrator and container spec
        orchestrator = ContainerSystemFactory.create_orchestrator()

        if args.action == "create-h1":
            spec = ContainerSpecFactory.create_h1_spec()
        elif args.action == "create-h2":
            spec = ContainerSpecFactory.create_h2_spec()
        else:
            logger.error(f"Unknown action: {args.action}")
            return 1

        # Create the container
        orchestrator.create_container(spec)
        return 0

    except Exception as e:
        logger.error(f"Container creation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
