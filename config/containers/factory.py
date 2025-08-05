#!/usr/bin/env python3
"""
Factory for creating container system components
"""

from typing import List

from bridge import BridgeVLANManager
from config_generators import (
    ContainerInitScriptGenerator,
    FRRConfigGenerator,
    NetworkTestScriptGenerator,
)
from executor import SystemCommandExecutor
from filesystem import FileSystemManager
from interfaces import ConfigurationGenerator
from libvirt_manager import LibvirtDomainManager, LibvirtXMLGenerator
from orchestrator import ContainerOrchestrator
from packages import PackageInstaller
from rootfs import RootfsBuilder


class ContainerSystemFactory:
    """Factory for creating container system components"""

    @staticmethod
    def create_orchestrator() -> ContainerOrchestrator:
        """Create fully configured container orchestrator"""
        executor = SystemCommandExecutor()
        fs_manager = FileSystemManager()
        bridge_manager = BridgeVLANManager(executor)
        rootfs_builder = RootfsBuilder(executor, fs_manager)
        package_installer = PackageInstaller(executor, fs_manager)

        config_generators: List[ConfigurationGenerator] = [
            FRRConfigGenerator(executor),
            NetworkTestScriptGenerator(executor),
            ContainerInitScriptGenerator(executor),
        ]

        xml_generator = LibvirtXMLGenerator(executor)
        domain_manager = LibvirtDomainManager(executor)

        return ContainerOrchestrator(
            executor=executor,
            fs_manager=fs_manager,
            bridge_manager=bridge_manager,
            rootfs_builder=rootfs_builder,
            package_installer=package_installer,
            config_generators=config_generators,
            xml_generator=xml_generator,
            domain_manager=domain_manager,
        )
