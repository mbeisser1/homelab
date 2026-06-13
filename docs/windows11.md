# Windows 11 gaming VM (KVM, GPU passthrough, Looking Glass)

Single flow: prepare the Ubuntu host for VFIO, create and install Windows 11 with VirtIO, attach the RTX 3090, then use Looking Glass (and optionally PipeWire audio). Replace `win11` with your libvirt domain name if it differs.

## Table of contents

- [Overview and hardware](#overview-and-hardware)
- [Part 1: Host — IOMMU, VFIO, and initramfs](#part-1-host--iommu-vfio-and-initramfs)
- [Part 2: Host — QEMU and libvirt](#part-2-host--qemu-and-libvirt)
- [Part 3: Create the VM and install Windows 11](#part-3-create-the-vm-and-install-windows-11)
- [Part 4: GPU passthrough](#part-4-gpu-passthrough)
- [Part 5: Looking Glass B7](#part-5-looking-glass-b7)
- [Part 6: `qemu.conf`, device ACLs, and VM audio (Ubuntu 25.10)](#part-6-qemuconf-device-acls-and-vm-audio-ubuntu-2510)
- [Quick PCI reference (example only)](#quick-pci-reference-example-only)

## Overview and hardware

| Item | Details |
| --- | --- |
| CPU | AMD Ryzen 9 7950X |
| Host display GPU | Intel Arc A310 |
| Passthrough GPU | NVIDIA GeForce RTX 3090 (`10de:2204`, `10de:1aef`) |
| Host OS | Ubuntu 25.10 (this write-up matches this host) |
| Guest OS | Windows 11 |
| Hypervisor | libvirt / QEMU |
| Remote display | Looking Glass B7 (example config below) |

### Prerequisites

- IOMMU enabled in the BIOS.
- The GPU you pass through is **not** the display GPU.
- **No** proprietary NVIDIA drivers on the host (use vfio for the passthrough card).

---

## Part 1: Host — IOMMU, VFIO, and initramfs

### 1. GRUB kernel parameters

Edit `/etc/default/grub` and set `GRUB_CMDLINE_LINUX_DEFAULT` (keep your other flags if needed):

```bash
# sudo vim /etc/default/grub
```

```text
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash amd_iommu=on iommu=pt vfio-pci.ids=10de:2204,10de:1aef"
```

Use `intel_iommu=on` on Intel CPUs instead of `amd_iommu=on`.

```bash
sudo update-grub
```

### 2. Blacklist NVIDIA modules on the host

Create `/etc/modprobe.d/blacklist-nvidia.conf`:

```text
blacklist nouveau
blacklist nvidia
blacklist nvidia_drm
blacklist nvidia_modeset
blacklist nvidia_uvm
blacklist nvidiafb
```

### 3. Bind the GPU to vfio-pci

Create `/etc/modprobe.d/vfio.conf`:

```text
options vfio-pci ids=10de:2204,10de:1aef
softdep nvidia pre: vfio-pci
```

### 4. Load VFIO modules in the initramfs

Append to `/etc/initramfs-tools/modules`:

```text
vfio
vfio_iommu_type1
vfio_pci
```

### 5. Remove NVIDIA driver packages from the host

```bash
sudo apt remove --purge 'nvidia-*'
```

### 6. Rebuild initramfs and reboot

```bash
sudo update-initramfs -u -k all
sudo reboot
```

After reboot, confirm the GPU is on `vfio-pci` (e.g. `lspci -nnk`).

---

## Part 2: Host — QEMU and libvirt

```bash
sudo apt update
sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virt-manager ovmf
```

```bash
sudo usermod -aG libvirt $USER
sudo usermod -aG kvm $USER
```

Log out and back in so the new groups apply.

---

## Part 3: Create the VM and install Windows 11

### Downloads

- [Windows 11 ISO](https://www.microsoft.com/software-download/windows11) from Microsoft.
- [VirtIO drivers ISO](https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso) (stable `virtio-win.iso`).

### New VM in virt-manager

1. **Create a new virtual machine** → **Local install media (ISO)** → choose the Windows 11 ISO.
2. Set OS type to **Microsoft Windows 11** if it is not detected automatically.
3. Allocate at least **4096 MB RAM** (8192 MB recommended), at least **2 vCPUs**, and at least **64 GB** disk.
4. Enable **Customize configuration before install** before finishing.

### Firmware, TPM, storage, and network

In the customization dialog:

1. **Overview** → set firmware to **UEFI** (OVMF), e.g. `UEFI x86_64: /usr/share/edk2/ovmf/OVMF_CODE.fd` or the path your distro provides.
2. **Add Hardware** → **TPM** → emulated **TIS**, version **2.0** (Windows 11 requirement).
3. **Add Hardware** → **Storage** → **CDROM** → attach the **VirtIO drivers** ISO as a second CD.
4. Select the **main disk** → set **Disk bus** to **VirtIO**.
5. Select the **NIC** → set **Device model** to **virtio**.
6. **Begin installation**.

Use virt-manager’s console for the installer; **Ctrl+Alt** releases the mouse and keyboard from the guest.

### Windows installer (storage driver)

1. Boot the installer; at **Where do you want to install Windows?** choose **Load driver**.
2. Browse the VirtIO CD → open **`viostor\w11\amd64`** → install the driver.
3. The VirtIO disk should appear; install to it.
4. On the network step you can choose **I don’t have internet** until guest tools are installed.
5. Finish the out-of-box experience.

### VirtIO guest tools (inside Windows)

After first boot:

1. Open the VirtIO CD in File Explorer.
2. Run **`virtio-win-guest-tools.exe`** and complete the wizard (includes network and other virtio drivers).
3. Reboot when prompted.

Confirm the VM has network (NAT is typical with virt-manager defaults).

---

## Part 4: GPU passthrough

Do this after Windows and VirtIO are stable. PCI addresses (`0000:01:00.x`) are examples — pick your devices in virt-manager.

1. Shut the VM down (not snapshot-only suspend if you are changing hardware).
2. **Add Hardware** → **PCI Host Device** → add the RTX 3090 **video** function (e.g. `0000:01:00.0 NVIDIA GA102 [GeForce RTX 3090]`).
3. **Add Hardware** → **PCI Host Device** again → add the matching **HD Audio** function (e.g. `0000:01:00.1`).

Boot Windows, open **Device Manager**, install the NVIDIA driver package from NVIDIA’s site inside the guest, and reboot.

**Physical monitor (optional):** you can connect a display to the RTX outputs for troubleshooting or native display instead of Looking Glass.

**Headless / Looking Glass:** plug an **HDMI or DisplayPort dummy plug** into the 3090 on the host. Without an active output, Windows may not expose a desktop the host client can capture.

---

## Part 5: Looking Glass B7

Host and guest **must** use the same Looking Glass release (example: both B7).

### Windows — host service config

Edit or create:

`C:\Program Files\Looking Glass (host)\looking-glass-host.ini`

```ini
[dxgi]
adapter=NVIDIA GeForce RTX 3090
```

Use the exact adapter name from **Device Manager**.

### Linux — SPICE on a Unix socket

```bash
virsh edit win11
```

Replace the existing `<graphics>` block with:

```xml
<graphics type='spice'>
  <listen type='socket' socket='/var/run/libvirt/qemu/win11.sock'/>
  <image compression='off'/>
</graphics>
```

Ensure these inputs exist (adjust `port` if they clash with other USB devices):

```xml
<input type='tablet' bus='usb'>
  <address type='usb' bus='0' port='1'/>
</input>
<input type='keyboard' bus='virtio'/>
<input type='mouse' bus='virtio'/>
```

Apply changes:

```bash
virsh destroy win11
virsh start win11
```

`destroy` is a **forced power-off** of the domain; it does not delete disks.

### Windows — SPICE / virtio guest tools

Install **virtio-win** guest tools so the SPICE **vdagent** runs (needed for pointer/keyboard through SPICE / Looking Glass integration).

Download: [virtio-win-pkg-scripts / virtio-win](https://github.com/virtio-win/virtio-win-pkg-scripts).

### Linux — Looking Glass client

`~/.config/looking-glass/client.ini`:

```ini
[input]
escapeKey=97
autoCapture=yes

[spice]
host=/var/run/libvirt/qemu/win11.sock
port=0
```

Use the **raw socket path** above. Do **not** prefix with `unix://` — that can fail silently.

`escapeKey=97` is **Right Ctrl** and toggles input capture.

### Run it

In Windows: **services.msc** → **Looking Glass Host** → start (set to automatic if you like).

On Linux:

```bash
looking-glass-client
```

#### Notes

- Seeing **Intel Arc** as the renderer in client logs is normal; Arc is the host’s display GPU for the LG window. Capture still comes from the 3090 in the guest.
- The SPICE socket is recreated when the VM starts.
- Matching **B7** (or same version) on client and host is required.

---

## Part 6: `qemu.conf`, device ACLs, and VM audio (Ubuntu 25.10)

PipeWire still serves audio on **`pipewire-pulse`**, but **who runs QEMU** decides how the guest reaches that socket.

On this host, libvirt runs QEMU as **root** so you do not have to align the libvirt user with your login. That is convenient but **every VM has root-level access to host devices the process can open** — use only trusted disk images and lock down the host as you would any privileged service. A smaller blast-radius approach is to run QEMU as your desktop user (see below) so you do not need a hard-coded `PULSE_SERVER`.

### PipeWire (desktop user)

Ensure the user where you actually log in (the one whose session plays audio) has PipeWire running:

```bash
systemctl --user enable --now pipewire.service pipewire-pulse.service
```

```bash
systemctl --user status pipewire.service pipewire-pulse.service
pactl info
```

`pactl info` should show a server on `/run/user/<UID>/pulse/native` and a name like **PulseAudio (on PipeWire …)**. Use that **UID** in the next section (`id -u`).

### This host: `/etc/libvirt/qemu.conf`

```conf
user = "root"
group = "root"

cgroup_device_acl = [
  "/dev/null",
  "/dev/full",
  "/dev/zero",
  "/dev/random",
  "/dev/urandom",
  "/dev/ptmx",
  "/dev/kvm",
  "/dev/kvmfr0"
]

env = ["PULSE_SERVER=unix:/run/user/1000/pulse/native"]
```

- **`/dev/kvmfr0`** — Looking Glass **IVSHMEM** (`kvmfr`); QEMU must be allowed to open it. Drop this entry if you are not using LG’s `/dev/kvmfr0` node.
- **`cgroup_device_acl`** — Extends which device nodes QEMU may open under cgroup rules; include `kvmfr0` when Looking Glass uses IVSHMEM on that node.
- **`PULSE_SERVER`** — Points QEMU’s PulseAudio client at **your** session socket (`1000` = example; set to `id -u` for the user that runs PipeWire). Root-owned QEMU cannot use `$XDG_RUNTIME_DIR`, so the socket path is pinned explicitly.

```bash
sudo systemctl restart libvirtd
```

### Alternative: non-root QEMU (no `PULSE_SERVER` env)

If you set `user` / `group` to your login and primary group (for example a user in `libvirt-qemu` / `kvm` patterns your distro documents), QEMU runs with your **UID** and can usually open `/run/user/<UID>/pulse/native` without `env`. You may still need **`/dev/kvmfr0`** in `cgroup_device_acl` when using Looking Glass.

### VM XML — audio device

```bash
EDITOR=vim virsh edit win11
```

Place **`<audio>` before `<video>`**. Example:

```xml
<audio id='1' type='pulseaudio'/>
<sound model='ich9'>
  <audio id='1'/>
  <address type='pci' domain='0x0000' bus='0x00' slot='0x1b' function='0x0'/>
</sound>
```

### How it fits together

- With **root QEMU**, `PULSE_SERVER` forces the PulseAudio backend to talk to the **interactive user’s** PipeWire stack instead of root’s (which has no session socket).
- **`pipewire-pulse`** still implements the server QEMU speaks to; the guest’s `type='pulseaudio'` audio goes out your normal desktop output.

---

## Quick PCI reference (example only)

Use `lspci -nn` and virt-manager’s PCI list to pick the correct functions for your board. Typical 3090 pair:

- `0000:01:00.0` — VGA / 3D controller  
- `0000:01:00.1` — HD Audio controller  

Your bus/slot numbers may differ.
