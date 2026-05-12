# Complete Setup Summary - Original Plan

**Hardware:**
- Ubuntu host OS (native Linux) - daily driver
- Intel Arc A310 - host display + Jellyfin transcoding
- RTX 3090 - PRIME offload for Unreal Engine on host, passthrough to Windows VM when gaming
- Windows 11 VM - gaming with RTX 3090 passthrough, accessed via Looking Glass + SPICE + Scream
- Linux VM - self-hosted services (Nextcloud, XWiki, etc.) without GPU

---

## GPU Allocation

### **Intel Arc A310**
- **Role**: Host display and transcoding
- **Permanently assigned to**: Ubuntu host
- **Usage**:
  - Primary display output (monitor connection)
  - Desktop environment rendering
  - Jellyfin hardware transcoding (QuickSync) - native linux host
  - Always available for host

### **NVIDIA RTX 3090**
- **Default state**: Available to host via PRIME render offload
- **Host usage**: Unreal Engine 5 development, Blender, CUDA workloads
- **Gaming mode**: Passed through to Windows 11 VM (exclusive access)

---

## Virtual Machines

### **Windows 11 VM**
- **GPU**: RTX 3090 (full PCI passthrough when VM is running)
- **Access method**: 
  - **Video**: Looking Glass (low-latency frame capture, displayed on Ubuntu desktop)
  - **Input**: SPICE (keyboard/mouse via Looking Glass window, Scroll Lock to release)
- **Monitor**: Stays connected to Arc A310, views Windows via Looking Glass window
- **Usage**: Unreal Engine 5 development, Gaming
- **Benefits**: **No dual-booting** - Everything accessible simultaneously  

### **Linux VM**
- **GPU**: None (CPU only)
- **Services**: Nextcloud, XWiki, and other web-based self-hosted applications
- **Reason for separation**: Isolation from primary Ubuntu environment - Self-hosted apps in separate VM for security  
- **Access**: SSH, web interfaces (no GUI needed)
- **Usage**: Self-Hosting