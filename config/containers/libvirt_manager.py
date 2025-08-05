#!/usr/bin/env python3
"""
Libvirt XML generation and domain management
"""

import logging
from pathlib import Path
from typing import List

from jinja2 import Template

from interfaces import CommandExecutor
from models import ContainerSpec

logger = logging.getLogger(__name__)


class LibvirtXMLGenerator:
    """Generates libvirt XML configuration"""

    def __init__(self, executor: CommandExecutor) -> None:
        self.executor: CommandExecutor = executor

    def generate_xml(
        self, spec: ContainerSpec, rootfs_path: Path, output_file: Path
    ) -> None:
        """Generate libvirt XML configuration"""
        emulator_path: str = self._find_libvirt_emulator()

        xml_template = Template(
            """<?xml version="1.0" encoding="UTF-8"?>
<domain type='lxc'>
  <n>{{ spec.name }}</n>
  <memory unit='KiB'>{{ spec.memory_kb }}</memory>
  <currentMemory unit='KiB'>{{ spec.memory_kb }}</currentMemory>
  <vcpu placement='static'>{{ spec.vcpus }}</vcpu>
  <os>
    <type arch='x86_64'>exe</type>
    <init>/usr/local/bin/container-init</init>
  </os>
  <clock offset='utc'/>
  <on_poweroff>restart</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>
  <devices>
    <emulator>{{ emulator_path }}</emulator>
    <filesystem type='mount' accessmode='passthrough'>
      <source dir='{{ rootfs_path }}'/>
      <target dir='/'/>
    </filesystem>
    <interface type='bridge'>
      <source bridge='{{ spec.management_interface.bridge }}'/>
      <model type='virtio'/>
      <mac address='{{ spec.management_interface.mac_address }}'/>
    </interface>
    <interface type='bridge'>
      <source bridge='{{ spec.test_interface.bridge }}'/>
      <model type='virtio'/>
      <mac address='{{ spec.test_interface.mac_address }}'/>
    </interface>
    <console type='pty'>
      <target type='lxc' port='0'/>
    </console>
  </devices>
</domain>
"""
        )

        xml_content: str = xml_template.render(
            spec=spec, emulator_path=emulator_path, rootfs_path=str(rootfs_path)
        )

        with open(output_file, "w") as f:
            f.write(xml_content)

        logger.info(f"Generated XML configuration: {output_file}")

    def _find_libvirt_emulator(self) -> str:
        """Find libvirt LXC emulator path"""
        emulator_paths: List[str] = [
            "/usr/lib/libvirt/libvirt_lxc",
            "/usr/libexec/libvirt_lxc",
        ]

        for path in emulator_paths:
            if Path(path).exists():
                return path

        raise RuntimeError("Could not find libvirt_lxc emulator")


class LibvirtDomainManager:
    """Manages libvirt domain operations"""

    def __init__(self, executor: CommandExecutor) -> None:
        self.executor: CommandExecutor = executor

    def define_domain(self, xml_file: Path) -> None:
        """Define domain from XML file"""
        try:
            self.executor.run(
                ["sudo", "virsh", "-c", "lxc:///", "define", str(xml_file)]
            )
            logger.info(f"Domain defined from {xml_file}")
        except Exception as e:
            raise RuntimeError(f"Failed to define domain: {e}")

    def undefine_domain(self, domain_name: str) -> None:
        """Remove domain definition"""
        try:
            self.executor.run(
                ["sudo", "virsh", "-c", "lxc:///", "undefine", domain_name], check=False
            )  # Don't fail if domain doesn't exist
            logger.info(f"Domain {domain_name} undefined (if it existed)")
        except Exception:
            pass  # Domain might not exist, which is fine
