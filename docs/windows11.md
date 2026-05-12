# GPU Passthrough Setup - Ubuntu 25.04

## System

- CPU: AMD Ryzen 9 7950x
- Display GPU: Intel Arc A310
- Passthrough GPU: NVIDIA RTX 3090 (10de:2204, 10de:1aef)
- Host OS: Ubuntu 25.04
- Guest OS: Windows 11

## Prerequisites

- IOMMU enabled in BIOS
- GPU to pass through must NOT be the display GPU
- NVIDIA drivers must NOT be installed on the host

---

## 1. Configure GRUB

```bash
# sudo vim /etc/default/grub
# Edit GRUB_CMDLINE_LINUX_DEFAULT to:

GRUB_CMDLINE_LINUX_DEFAULT=&quot;quiet splash amd_iommu=on iommu=pt vfio-pci.ids=10de:2204,10de:1aef&quot;
```

> Note: Use `intel_iommu=on` for Intel CPU, `amd_iommu=on` for AMD CPU.

```bash
sudo update-grub
```

---

## 2. Blacklist NVIDIA Host Drivers

```bash
# sudo vim /etc/modprobe.d/blacklist-nvidia.conf

blacklist nouveau
blacklist nvidia
blacklist nvidia_drm
blacklist nvidia_modeset
blacklist nvidia_uvm
blacklist nvidiafb
```

---

## 3. Configure vfio-pci Module

```bash
# sudo vim /etc/modprobe.d/vfio.conf

options vfio-pci ids=10de:2204,10de:1aef
softdep nvidia pre: vfio-pci
```

---

## 4. Load vfio Modules Early in Initramfs

```bash
# sudo vim /etc/initramfs-tools/modules
# Add at the end:

vfio
vfio_iommu_type1
vfio_pci
```

---

## 5. Remove NVIDIA Host Drivers

```bash
sudo apt remove --purge &#x27;nvidia-*&#x27;
```

---

## 6. Rebuild Initramfs and Reboot

```bash
sudo update-initramfs -u -k all
sudo reboot
```

---

## 7. Install Virtualization Software

```bash
sudo apt update
sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virt-manager ovmf
```

```bash
sudo usermod -aG libvirt $USER
sudo usermod -aG kvm $USER
```

Log out and back in for group changes to take effect.

---

## 8. Create the Windows 11 VM

1. Open virt-manager
2. Create a new VM with the following settings:
   - Firmware: UEFI/OVMF (required for Windows 11 and GPU passthrough)
   - Allocate appropriate RAM and CPU cores
   - Attach a Windows 11 ISO

---

## 9. Add PCI Devices to the VM

In virt-manager, open VM hardware details:

1. Click Add Hardware > PCI Host Device
2. Add: `0000:01:00.0 NVIDIA Corporation GA102 [GeForce RTX 3090]`
3. Click Add Hardware > PCI Host Device again
4. Add: `0000:01:00.1 NVIDIA Corporation GA102 High Definition Audio`

---

## 10. Connect to the VM

1. Start the VM in virt-manager
2. Double-click the VM to open the Spice console
3. Click inside the window to interact
4. Press Ctrl+Alt to release mouse/keyboard from the VM

---

## 11. Install NVIDIA Drivers in Windows

1. Boot the Windows 11 VM
2. Open Device Manager - the RTX 3090 will appear with a warning
3. Download and install NVIDIA drivers from nvidia.com inside the VM
4. Reboot the VM
5. Connect a physical monitor to the RTX 3090 output for direct GPU display



-----------------------------------------

# Looking Glass B7 Setup — Ubuntu Host + Windows 11 VM (GPU Passthrough)

## Environment

- Host: Ubuntu 25.10
- Guest: Windows 11
- Host GPU (display): Intel Arc A310
- Passthrough GPU: NVIDIA GeForce RTX 3090
- Hypervisor: libvirt/QEMU
- Looking Glass: B7

---

## 1. Hardware

Plug a headless dummy plug (HDMI or DisplayPort) into the RTX 3090 on the
physical machine. Without this, Windows will find no active display output on
the passed-through GPU and the host application will fail to capture.

---

## 2. Windows VM — Looking Glass Host Config

Inside the Windows 11 VM, edit or create:

    C:\Program Files\Looking Glass (host)\looking-glass-host.ini

Add the following to force the host to use the RTX 3090:

    [dxgi]
    adapter=NVIDIA GeForce RTX 3090

Use the adapter name exactly as it appears in Windows Device Manager.

---

## 3. Linux Host — VM XML Configuration

### 3a. SPICE Graphics (Unix Socket)

Edit the VM XML:

    virsh edit win11

Replace the existing &lt;graphics&gt; entry with:

    &lt;graphics type=&#x27;spice&#x27;&gt;
      &lt;listen type=&#x27;socket&#x27; socket=&#x27;/var/run/libvirt/qemu/win11.sock&#x27;/&gt;
      &lt;image compression=&#x27;off&#x27;/&gt;
    &lt;/graphics&gt;

### 3b. Input Devices

Ensure the following input devices are present in the XML:

    &lt;input type=&#x27;tablet&#x27; bus=&#x27;usb&#x27;&gt;
      &lt;address type=&#x27;usb&#x27; bus=&#x27;0&#x27; port=&#x27;1&#x27;/&gt;
    &lt;/input&gt;
    &lt;input type=&#x27;keyboard&#x27; bus=&#x27;virtio&#x27;/&gt;
    &lt;input type=&#x27;mouse&#x27; bus=&#x27;virtio&#x27;/&gt;

After editing, restart the VM:

    virsh destroy win11
    virsh start win11

Note: virsh destroy is a force power-off only. It does not delete any data.

---

## 4. Windows VM — SPICE Guest Tools

Install the virtio-win guest tools inside Windows 11. This provides the
SPICE agent (vdagent) required for mouse and keyboard input to work.

Download from: https://github.com/virtio-win/virtio-win-pkg-scripts

---

## 5. Linux Host — Looking Glass Client Config

Edit the client config:

    vim ~/.config/looking-glass/client.ini

    [input]
    escapeKey=97
    autoCapture=yes

    [spice]
    host=/var/run/libvirt/qemu/win11.sock
    port=0

Important: Use the raw socket path. Do not use the unix:/// URI prefix —
it causes the connection to fail silently.

escapeKey=97 maps to Right Ctrl. This is the key that toggles input capture.

---

## 6. Start Looking Glass

Inside the Windows VM, ensure the Looking Glass Host service is running:

    services.msc -&gt; Looking Glass Host -&gt; Start

On the Linux host:

    looking-glass-client

Press Right Ctrl to capture mouse and keyboard input.

---

## Notes

- The Intel Arc being listed as the renderer in client logs is normal. It is
  the display GPU on the host and is used only to render the Looking Glass
  window. Capture still runs on the RTX 3090.

- The SPICE socket is recreated each time the VM starts. If the VM is
  restarted, the socket will reappear automatically.

- The client and host must be the same Looking Glass release version (both B7).
```

---------------------------------

# Install Windows 11 VM on KVM with Virt-Manager

## Prerequisites

- Download the Windows 11 ISO from Microsoft
- Download the VirtIO drivers ISO from: https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso

---

## Step 1: Create the VM

1. Open virt-manager and click "Create a new virtual machine"
2. Select "Local install media (ISO image or CDROM)"
3. Click "Browse" and select your Windows 11 ISO
4. Set OS type to "Microsoft Windows 11" if not auto-detected
5. Set RAM to at least 4096 MB (8192 MB recommended)
6. Set CPUs to at least 2
7. Set disk size to at least 64 GB
8. Check "Customize configuration before install" before clicking Finish

---

## Step 2: Customize Hardware

In the customization window:

1. Under "Overview", set Firmware to "UEFI x86_64: /usr/share/edk2/ovmf/OVMF_CODE.fd" (or similar UEFI path)
2. Click "Add Hardware" and add a TPM:
   - Type: Emulated
   - Model: TIS
   - Version: 2.0
3. Click "Add Hardware" and add a second storage device:
   - Device type: CDROM device
   - Select the VirtIO drivers ISO
4. Click on the existing disk and change "Disk bus" to VirtIO
5. Click on the NIC and change "Device model" to virtio
6. Click "Begin Installation"

---

## Step 3: Install Windows

1. Boot into the Windows installer
2. At the "Where do you want to install Windows?" screen, click "Load driver"
3. Click "Browse" and navigate to the VirtIO CDROM drive
4. Select the folder: viostor\w11\amd64
5. Click OK and install the driver
6. Your virtual disk will now appear - select it and continue the installation
7. At the network screen, click "I don't have internet" to skip (drivers not yet loaded)
8. Complete the Windows 11 setup

---

## Step 4: Install VirtIO Drivers

1. Once Windows is booted, open File Explorer
2. Navigate to the VirtIO CDROM drive
3. Run "virtio-win-guest-tools.exe"
4. Follow the installer - this installs all remaining VirtIO drivers including the network driver
5. Reboot when prompted

---

## Step 5: Verify Network

After rebooting, Windows should automatically connect to the internet via the NAT network. No additional configuration is needed.


-----------------------------

# VM Audio Passthrough via PipeWire/PulseAudio (Ubuntu 25.04)

## Overview

On Ubuntu 25.04, PipeWire handles audio with a PulseAudio compatibility shim (`pipewire-pulse`). QEMU VMs can pass audio through this stack, but only if the VM process runs as the same user that owns the PipeWire socket.

---

## Step 1: Enable PipeWire User Services

Ensure `pipewire` and `pipewire-pulse` are enabled and running for your user:

```bash
systemctl --user enable --now pipewire.service pipewire-pulse.service
```

Verify they are running:

```bash
systemctl --user status pipewire.service pipewire-pulse.service
pactl info
```

`pactl info` should show a server string pointing to `/run/user/<UID>/pulse/native` and a name like `PulseAudio (on PipeWire ...)`.

---

## Step 2: Configure libvirt to Run QEMU as Your User

By default, libvirt runs QEMU as `libvirt-qemu`, which cannot access your user's PipeWire socket. Fix this by editing the QEMU config:

```bash
sudo vim /etc/libvirt/qemu.conf
```

Set the following values (replace `mbeisser` and `hosted` with your username and group):

```
user = &quot;mbeisser&quot;
group = &quot;hosted&quot;
```

Restart libvirt to apply the change:

```bash
sudo systemctl restart libvirtd
```

---

## Step 3: Configure VM Audio in XML

Edit your VM's XML definition:

```bash
EDITOR=vim virsh edit your-vm-name
```

Add or replace the audio and sound blocks with the following. The `<audio>` element must appear before `<video>`:

```xml
<audio id='1' type='pulseaudio'/>
<sound model='ich9'>
  <audio id='1'/>
  <address type='pci' domain='0x0000' bus='0x00' slot='0x1b' function='0x0'/>
</sound>

```

---

## How It Works

- `pipewire-pulse` provides a PulseAudio-compatible socket at `/run/user/<UID>/pulse/native`.
- QEMU, now running as your user, can reach that socket.
- VM audio set to `type='pulseaudio'` routes through PipeWire to your physical audio output.
