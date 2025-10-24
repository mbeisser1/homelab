[Homelab Wiki](https://mbeisser1.github.io/homelab/)

**Hardware:**
- Ubuntu host OS (native Linux)
- Intel Arc A310 - host display + Jellyfin transcoding
- RTX 3090 - PRIME offload for Unreal Engine on host, passthrough to Windows VM when gaming
- Windows 11 VM - gaming with RTX 3090 passthrough, accessed via Looking Glass + SPICE + Scream
- Linux VM - self-hosted services (Nextcloud, XWiki, etc.) without GPU

# Complete Setup Summary

## System Architecture

**Host OS: Ubuntu 24.04 LTS (Native Linux)**
- Primary daily driver and development environment
- Handles 80% of your workflow

---

## GPU Allocation

### **Intel Arc A310**
- **Role**: Host display and compute
- **Permanently assigned to**: Ubuntu host
- **Usage**:
  - Primary display output (monitor connection)
  - Desktop environment rendering
  - Jellyfin hardware transcoding (QuickSync)
  - Always available for host

### **NVIDIA RTX 3090**
- **Default state**: Available to host via PRIME render offload
- **Host usage**: Unreal Engine 5 development, Blender, CUDA workloads
- **Gaming mode**: Passed through to Windows 11 VM (exclusive access)
- **Switching mechanism**: Libvirt hooks automatically bind/unbind when VM starts/stops

---

## Virtual Machines

### **Windows 11 VM** (Gaming)
- **GPU**: RTX 3090 (full PCI passthrough when VM is running)
- **Access method**: 
  - **Video**: Looking Glass (low-latency frame capture, displayed on Ubuntu desktop)
  - **Input**: SPICE (keyboard/mouse via Looking Glass window, Scroll Lock to release)
  - **Audio**: Scream (network audio streaming, ~10-20ms latency)
- **Monitor**: Stays connected to Arc A310, views Windows via Looking Glass window

### **Linux VM** (Self-Hosting)
- **GPU**: None (CPU only)
- **Services**: Nextcloud, XWiki, and other web-based self-hosted applications
- **Reason for separation**: Isolation from primary Ubuntu environment
- **Access**: SSH, web interfaces (no GUI needed)

---

## Workflow

### **Daily Development (Default State)**
```
Ubuntu Desktop (Arc A310) → You work here
      ↓
RTX 3090 available for PRIME offload
      ↓
Launch Unreal Engine with: __NV_PRIME_RENDER_OFFLOAD=1
```

### **Gaming Session**
```
1. Close apps using RTX 3090 (Unreal, Blender, etc.)
2. Start Windows VM → RTX 3090 automatically binds to vfio-pci
3. Launch Looking Glass client on Ubuntu
4. Start Scream audio receiver
5. Click Looking Glass window to capture input
6. Game within the Looking Glass window
7. When done: Shut down VM → RTX 3090 returns to host
```

### **Media Streaming**
```
Jellyfin runs natively on Ubuntu host
      ↓
Arc A310 handles hardware transcoding (QuickSync)
      ↓
Services remain available 24/7
```

---

## Key Benefits

✅ **No dual-booting** - Everything accessible simultaneously  
✅ **Seamless workflow** - Stay in Ubuntu desktop, access Windows as a window  
✅ **Hardware efficiency** - Both GPUs utilized based on workload  
✅ **Service isolation** - Self-hosted apps in separate VM for security  
✅ **Always-on transcoding** - Jellyfin available regardless of VM state  
✅ **Native Linux performance** - 80% of your work runs at full speed  

---

## Next Steps for Implementation

1. **Install Ubuntu 24.04** with KVM/QEMU support
2. **Enable IOMMU** in BIOS (AMD-Vi for Ryzen)
3. **Install required packages**:
   ```bash
   sudo apt install qemu-kvm libvirt-daemon-system virt-manager \
   looking-glass-client scream ovmf
   ```
4. **Configure RTX 3090 for dynamic binding** (libvirt hooks)
5. **Create Windows 11 VM** with RTX 3090 passthrough
6. **Set up Looking Glass** shared memory device
7. **Install Scream** in Windows VM
8. **Create self-hosting Linux VM** for services
9. **Install and configure Jellyfin** on Ubuntu host with Arc A310
