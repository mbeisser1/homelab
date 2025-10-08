[Homelab Wiki](https://mbeisser1.github.io/homelab/)

<details><summary>Thinking</summary>

Perfect! The user wants me to summarize the entire setup we've discussed. Let me organize this clearly:

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


==================================================================






The user wants two separate markdown documents:
1. Steps for getting Intel A310 GPU passthrough working on Proxmox (host-level configuration)
2. Steps for creating the Ubuntu VM with correct options

I need to make these concise, accurate, and copy-pasteable. I'll focus on what they actually did/will do, not all the options we discussed.

For document 1 (GPU passthrough setup):
- Identify GPU PCI IDs
- Blacklist Intel drivers
- Create vfio.conf
- Update initramfs and reboot
- Verify it worked

For document 2 (Ubuntu VM creation):
- All the tabs and settings they chose
- Adding GPU via hardware or config file
- First boot and driver installation

Let me make these clear and actionable.

</details>

# Document 1: Intel A310 GPU Passthrough Setup on Proxmox

```markdown
# Intel Arc A310 GPU Passthrough Configuration for Proxmox

## Hardware Information
- **GPU:** Intel Arc A310
- **PCI Address:** 05:00
- **GPU Device ID:** 8086:56a6
- **Audio Device ID:** 8086:4f92

## Prerequisites
- IOMMU enabled in BIOS (AMD-Vi for AMD CPUs)
- Proxmox 9 installed
- Another GPU available for Proxmox console (7950X iGPU in this case)

---

## Step 1: Identify Intel A310 PCI Information

```bash
lspci -nn | grep -i intel
```

**Expected output:**
```
05:00.0 VGA compatible controller [0300]: Intel Corporation DG2 [Arc A310] [8086:56a6] (rev 05)
06:00.0 Audio device [0403]: Intel Corporation DG2 Audio Controller [8086:4f92]
```

**Note:** PCI address is `05:00`, GPU ID is `8086:56a6`, Audio ID is `8086:4f92`

---

## Step 2: Blacklist Intel Drivers

**Edit Proxmox blacklist file:**
```bash
nano /etc/modprobe.d/pve-blacklist.conf
```

**Add these lines:**
```
# Blacklist Intel A310 drivers for passthrough
blacklist i915
blacklist snd_hda_intel
blacklist snd_hda_codec_hdmi
```

**Save:** Ctrl+X, Y, Enter

---

## Step 3: Create VFIO Configuration

**Create vfio.conf:**
```bash
nano /etc/modprobe.d/vfio.conf
```

**Add (using your specific device IDs):**
```
# Bind Intel Arc A310 to vfio-pci for passthrough to Ubuntu VM
# GPU: 8086:56a6, Audio: 8086:4f92
options vfio-pci ids=8086:56a6,8086:4f92
```

**Save:** Ctrl+X, Y, Enter

---

## Step 4: Update Initramfs and Reboot

```bash
update-initramfs -u -k all
reboot
```

---

## Step 5: Verify GPU is Bound to VFIO-PCI

**After reboot, check:**
```bash
lspci -nnk -d 8086:56a6
```

**Expected output:**
```
05:00.0 VGA compatible controller [0300]: Intel Corporation DG2 [Arc A310] [8086:56a6] (rev 05)
        Subsystem: Device [172f:4240]
        Kernel driver in use: vfio-pci
        Kernel modules: i915, xe
```

**✅ Success indicator:** `Kernel driver in use: vfio-pci`

---

## Troubleshooting

**If GPU is not bound to vfio-pci:**
1. Double-check device IDs in vfio.conf match `lspci -nn` output exactly
2. Verify blacklist entries are correct
3. Run `update-initramfs -u -k all` again
4. Reboot and re-check

**If still not working:**
```bash
# Check if IOMMU is enabled
dmesg | grep -e DMAR -e IOMMU -e AMD-Vi

# Check IOMMU groups
find /sys/kernel/iommu_groups/ -type l | grep 05:00
```

---

## Configuration Files Summary

**Files modified:**
- `/etc/modprobe.d/pve-blacklist.conf` - Blacklisted Intel drivers
- `/etc/modprobe.d/vfio.conf` - Bound GPU to vfio-pci

**Commands used:**
- `update-initramfs -u -k all` - Applied changes
- `reboot` - Loaded new configuration
```

---

# Document 2: Ubuntu VM Creation with GPU Passthrough

```markdown
# Ubuntu VM Setup with Intel A310 GPU Passthrough

## VM Configuration Summary

**VM ID:** 102 (or your choice)  
**VM Name:** Ubuntu-Services  
**Purpose:** Desktop VM for services (Jellyfin, Docker), development, and daily Linux use

---

## Creating the VM in Proxmox GUI

### General Tab
- **VM ID:** 102
- **Name:** Ubuntu-Services

### OS Tab
- **ISO image:** ubuntu-24.04-desktop-amd64.iso
- **Type:** Linux
- **Version:** 6.x - 2.6 Kernel

### System Tab
- **Graphics card:** Default
- **Machine:** q35
- **BIOS:** OVMF (UEFI)
- **Add EFI Disk:** Yes
- **Pre-Enroll keys:** No (unchecked)
- **SCSI Controller:** VirtIO SCSI single
- **QEMU Agent:** Yes (checked)
- **Add TPM:** No (unchecked)

### Disks Tab
- **Bus/Device:** SCSI
- **Storage:** local-lvm (or your storage)
- **Disk size:** 150 GiB (adjust as needed)
- **Cache:** Default (No cache)
- **Discard:** Yes
- **IO thread:** Yes
- **Async IO:** io_uring
- **Backup:** Yes

### CPU Tab
- **Type:** host
- **Sockets:** 1
- **Cores:** 10
- **Enable NUMA:** No

### Memory Tab
- **Memory:** 65536 MiB (64GB)
- **Minimum memory:** 2048 MiB
- **Ballooning Device:** Yes

### Network Tab
- **Bridge:** vmbr0
- **Model:** VirtIO (paravirtualized)
- **Firewall:** No (unchecked)

**Do NOT start the VM yet!**

---

## Adding Intel A310 GPU Passthrough

### Method 1: Via Proxmox GUI

1. Select the VM (102)
2. Go to **Hardware** tab
3. Click **Add** → **PCI Device**
4. Select your Intel A310 (`0000:05:00`)
5. Check: **Primary GPU**
6. Check: **PCI-Express**
7. Click **Add**

### Method 2: Via Command Line (Alternative)

**Edit VM configuration:**
```bash
nano /etc/pve/qemu-server/102.conf
```

**Add these lines:**
```
hostpci0: 0000:05:00,pcie=1,x-vga=1
cpu: host,hidden=1
args: -cpu host,kvm=off
vga: none
```

**Save:** Ctrl+X, Y, Enter

---

## Final VM Configuration File

**Your `/etc/pve/qemu-server/102.conf` should look like:**
```
args: -cpu host,kvm=off
bios: ovmf
boot: order=scsi0
cores: 10
cpu: host,hidden=1
efidisk0: local-lvm:vm-102-disk-0,efitype=4m,size=4M
hostpci0: 0000:05:00,pcie=1,x-vga=1
machine: q35
memory: 65536
name: Ubuntu-Services
net0: virtio=XX:XX:XX:XX:XX:XX,bridge=vmbr0
scsi0: local-lvm:vm-102-disk-1,aio=io_uring,discard=on,iothread=1,size=150G
scsihw: virtio-scsi-single
sockets: 1
vga: none
```

---

## First Boot and Installation

### Physical Setup
1. **Connect HDMI cable** from Intel A310 to monitor
2. **Switch monitor** to A310 input

### Start VM and Install Ubuntu
1. Click **Start** in Proxmox GUI
2. Ubuntu installer should appear on monitor connected to A310
3. Install Ubuntu normally
4. Complete installation and reboot

---

## Post-Installation: Intel GPU Drivers

**After Ubuntu boots, open Terminal (Ctrl+Alt+T):**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Intel GPU drivers and tools
sudo apt install -y \
    intel-gpu-tools \
    intel-media-va-driver-non-free \
    vainfo \
    mesa-utils \
    linux-firmware

# Reboot to load drivers
sudo reboot
```

---

## Verify GPU is Working

**After reboot:**

```bash
# Check GPU is detected
lspci | grep -i vga
# Should show: Intel Corporation DG2 [Arc A310]

# Test GPU monitoring
sudo intel_gpu_top
# Should show live GPU stats

# Verify hardware acceleration support
vainfo
# Should list H.264, HEVC, VP9, AV1 codecs

# Check OpenGL
glxinfo | grep "OpenGL renderer"
# Should show: Mesa Intel(R) Arc(tm) A310 Graphics
```

---

## Optional: Auto-Start Configuration

**Make VM start automatically with Proxmox:**

```bash
# Enable auto-start for Ubuntu VM (ID 102)
qm set 102 --onboot 1

# Set startup order (if you have multiple VMs)
# Start after Windows VM with 30 second delay
qm set 102 --startup order=2,up=30
```

---

## Resource Allocation Summary

**With this configuration:**
- **CPU:** 10 cores (20 threads) of Ryzen 9 7950X
- **RAM:** 64GB
- **GPU:** Intel Arc A310 (dedicated, full passthrough)
- **Storage:** 150GB+ (adjustable)
- **Network:** VirtIO on vmbr0

**Shared with:**
- Windows VM: 4-6 cores, 32GB RAM, RTX 3090
- Proxmox Host: Remaining cores, 32GB RAM, 7950X iGPU

---

## Troubleshooting

### No display output on monitor
- Verify HDMI is connected to Intel A310, not motherboard
- Check monitor is on correct input
- Try adding `,rombar=0` to hostpci0 line: `hostpci0: 0000:05:00,pcie=1,x-vga=1,rombar=0`

### GPU not detected in Ubuntu
```bash
# On Proxmox host, verify GPU is still bound to vfio-pci
lspci -nnk -d 8086:56a6
# Should show: Kernel driver in use: vfio-pci
```

### Black screen after GRUB
- In GRUB menu, press 'e'
- Add `nomodeset` to kernel line
- Boot and install proper drivers

### VM won't start
- Check VM logs: `/var/log/pve/qemu-server/102.log`
- Verify GPU isn't bound to another VM
- Ensure OVMF (UEFI) is selected, not SeaBIOS
```

---

**Both documents are now ready for copy/paste! Save them for future reference.** 📝

