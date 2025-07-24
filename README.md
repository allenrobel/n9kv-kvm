# Summary

Bringup a small VXLAN lab with Cisco Nexus Dashboard and Cisco Nexus9000v (n9kv) using QEMU.

## Cloning this Repository

```bash
git clone https://github.com/allenrobel/n9kv-kvm.git
```

## Topology

- Two fabrics
  - ISN (inter-site network)
    - 1x Edge Router (ER)
  - VXLAN (VxLAN)
    - 2x Border Spines (S1, S2)
    - 1x Leaf (L1)

```mermaid
graph TB
    subgraph ISN["ISN Fabric (Inter-Site Network)"]
        ER[Edge Router - ER]
    end
    
    subgraph VXLAN["VXLAN Fabric"]
        S1[Border Spine - S1]
        S2[Border Spine - S2]
        L1[Leaf - L1]
        
        %% VXLAN fabric connections
        S1 --- L1
        S2 --- L1
    end
    
    %% Inter-fabric connection
    ER --- S1
    ER --- S2
    
    %% Styling
    classDef fabricBox fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef edgeRouter fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef borderSpine fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef leaf fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    
    class ER edgeRouter
    class S1,S2 borderSpine
    class L1 leaf
```

## Project Structure

```bash
(n9kv-kvm) arobel@Allen-M4 n9kv-kvm % tree .
.
├── ansible
│   ├── dynamic_inventory.py
│   ├── interface_mac_addresses_ER.yaml
│   ├── interface_mac_addresses_L1.yaml
│   ├── interface_mac_addresses_S1.yaml
│   └── interface_mac_addresses_S2.yaml
├── bridges
│   ├── bridges_config.sh
│   ├── bridges_down.sh
│   └── bridges_monitor.sh
├── env
├── env_base.sh
├── main.py
├── pyproject.toml
├── qemu
│   ├── n9kv_qemu_ER.sh
│   ├── n9kv_qemu_L1.sh
│   ├── n9kv_qemu_S1.sh
│   └── n9kv_qemu_S2.sh
├── README.md
├── show_nd_interfaces
└── uv.lock

5 directories, 35 files
(n9kv-kvm) arobel@Allen-M4 n9kv-kvm %
```