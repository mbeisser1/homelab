[Homelab Wiki](https://mbeisser1.github.io/homelab/)

<details><summary>Thinking</summary>

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

