#!/usr/bin/env python3
"""
Unified CLI for container management system
"""

import argparse
import logging
import sys
from pathlib import Path

from executor import SystemCommandExecutor
from factory import ContainerSystemFactory
from requirements import RequirementsChecker
from config_loader import ConfigLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Unified Network Container Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py --check                                    # Check requirements
  python3 main.py --config access_mode_containers.yaml H1   # Create H1 from access mode config
  python3 main.py --config trunk_mode_containers.yaml H2    # Create H2 from trunk mode config
        """,
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML configuration file"
    )

    parser.add_argument(
        "container",
        nargs="?",
        help="Container name to create (e.g., H1, H2)"
    )

    parser.add_argument(
        "--check", action="store_true", help="Check system requirements only"
    )

    parser.add_argument(
        "--list-containers", 
        action="store_true", 
        help="List available containers in the config file"
    )

    args = parser.parse_args()

    # Create dependencies
    executor = SystemCommandExecutor()
    requirements_checker = RequirementsChecker(executor)

    try:
        # Load configuration
        config_loader = ConfigLoader(args.config)
        
        # List containers if requested (no requirements check needed)
        if args.list_containers:
            available_containers = config_loader.get_available_containers()
            print(f"Available containers in {args.config}:")
            for container in available_containers:
                print(f"  - {container}")
            return 0

        # Check requirements for actual container operations
        if args.check:
            return 0 if requirements_checker.check_all_requirements() else 1

        if not requirements_checker.check_all_requirements():
            return 1

        # Validate container argument
        if not args.container:
            available_containers = config_loader.get_available_containers()
            parser.error(f"Container name is required. Available containers: {', '.join(available_containers)}")

        # Check if container exists in config
        available_containers = config_loader.get_available_containers()
        if args.container not in available_containers:
            logger.error(f"Container '{args.container}' not found in config. Available: {', '.join(available_containers)}")
            return 1

        # Create orchestrator and container spec
        orchestrator = ContainerSystemFactory.create_orchestrator()
        spec = config_loader.create_container_spec(args.container)

        # Create the container
        logger.info(f"Creating container '{args.container}' from config '{args.config}'")
        orchestrator.create_container(spec)
        logger.info(f"Successfully created container '{args.container}'")
        return 0

    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"Container creation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())