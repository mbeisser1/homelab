# Homelab

## Documentation

- [NAS Workstation](docs/nas_workstation.md)
  - [Router](docs/router.md)
  - [User Setup](docs/new_user.md)
  - [Postfix Mail](docs/postfix_mail.md)
  - [Jellyfin](docs/jellyfin.md)
- Virtual Machines
  - [Windows 11](docs/windows11.md)
  - [Hosted Services](docs/hosted_services_vm.md)

## Table of Contents

- [Homelab](#homelab)
  - [Documentation](#documentation)
  - [Table of Contents](#table-of-contents)
  - [Hardware](#hardware)
    - [NAS-DEV (2025)](#nas-dev-2025)
    - [Parts](#parts)
    - [inxi output](#inxi-output)
  - [GPU allocation](#gpu-allocation)
    - [Intel Arc A310](#intel-arc-a310)
    - [NVIDIA RTX 3090](#nvidia-rtx-3090)
  - [Virtual machines](#virtual-machines)
    - [Windows 11 VM](#windows-11-vm)
    - [Linux VM](#linux-vm)
  - [Previous setup](#previous-setup)
    - [NAS (2015)](#nas-2015)
      - [Hard drives](#hard-drives)
    - [Gaming PC (2016)](#gaming-pc-2016)

## Hardware

### NAS-DEV (2025)

- Ubuntu host OS (native Linux) - daily driver
- Intel Arc A310 - host display + Jellyfin transcoding
- RTX 3090 - PRIME offload for Unreal Engine on host, passthrough to Windows VM when gaming
- Windows 11 VM - gaming with RTX 3090 passthrough, accessed via Looking Glass + SPICE + Scream
- Linux VM - self-hosted services (Nextcloud, XWiki, etc.) without GPU

- Ubuntu Host OS (native Linux)
  - Dev
    - Unreal 5 - offload to RTX 3090 (no windows VM)
  - Docker
    - Jellyfin
      - Use Arc A310 for transcoding
      - Connect externally via tailscale
  - VMs
    - Hosted Services (Ubuntu 24.04)
      - Connected to Hetzner vps via Wireguard
      - Docker
        - XWiki
        - Nextcloud
        - Joplin
        - OnlyOffice
        - Cockpit
        - Wireguard
    - Gaming (Windows 11)
      - RTX 3090 pass through, accessed via Looking Glass + SPICE + Scream?
      - Office
- Hetzner VPS
  - Hosts bitrealm.dev
  - Reverse proxy for hosted services

### Parts

ASRock X870 TAICHI CREATOR AM5 ATX Motherboard
AMD Ryzen 9 7950X (16-core)
NEMIX RAM 64GB (2x32GB) DDR5 5600MHz ECC UDIMM x 2 (128GB total) - Running 4400 MT/s (no bios tweaking)
CORSAIR HX1500i Modular Ultra-Low Noise ATX Power Supply, 80 PLUS Platinum
LSI SAS 9300-8i 8-Port HBA Card
SAMSUNG 990 PRO SSD 1TB (M.2 2280)
SAMSUNG 990 PRO SSD 4TB (M.2 2280)
20TB 7200rpm SATA Hard Drive (Various, 8 total)
RTX 3090 Founders Edition
Sparkle Intel Arc A310 Omni - 4GB GDDR6

I put the 8 SATA drives in a snapraid pool with mergerfs

<details>

<summary>Linux hardware listing</summary>

### inxi output

```txt
mbeisser@nas-dev:~$ sudo inxi -Fnn
System:
  Host: nas-dev Kernel: 6.14.0-34-generic arch: x86_64 bits: 64
  Desktop: Cinnamon v: 6.4.8 Distro: Ubuntu 25.04 (Plucky Puffin)
Machine:
  Type: Desktop Mobo: ASRock model: X870 Taichi Creator
    serial: M8P-J7M00100085 UEFI: American Megatrends LLC. v: 3.50
    date: 09/18/2025
CPU:
  Info: 16-core model: AMD Ryzen 9 7950X bits: 64 type: MT MCP cache:
    L2: 16 MiB
  Speed (MHz): avg: 4934 min/max: 545/5883 cores: 1: 4934 2: 4934 3: 4934
    4: 4934 5: 4934 6: 4934 7: 4934 8: 4934 9: 4934 10: 4934 11: 4934 12: 4934
    13: 4934 14: 4934 15: 4934 16: 4934 17: 4934 18: 4934 19: 4934 20: 4934
    21: 4934 22: 4934 23: 4934 24: 4934 25: 4934 26: 4934 27: 4934 28: 4934
    29: 4934 30: 4934 31: 4934 32: 4934
Graphics:
  Device-1: NVIDIA GA102 [GeForce RTX 3090] driver: vfio-pci v: N/A
  Device-2: Intel DG2 [Arc A310] driver: i915 v: kernel
  Device-3: Advanced Micro Devices [AMD/ATI] Raphael driver: amdgpu
    v: kernel
  Device-4: Sunplus Innovation FHD Camera Microphone
    driver: snd-usb-audio,uvcvideo type: USB
  Display: x11 server: X.Org v: 21.1.16 driver: X:
    loaded: amdgpu,modesetting unloaded: fbdev,vesa dri: iris gpu: i915
    resolution: 2560x1080~60Hz
  API: EGL v: 1.5 drivers: iris,radeonsi,swrast
    platforms: gbm,x11,surfaceless,device
  API: OpenGL v: 4.6 compat-v: 4.5 vendor: intel mesa
    v: 25.0.7-0ubuntu0.25.04.2 renderer: Mesa Intel Arc A310 Graphics (DG2)
  Info: Tools: api: clinfo, eglinfo, glxinfo gpu: gputop, intel_gpu_top,
    lsgpu x11: xdriinfo, xdpyinfo, xprop, xrandr
Audio:
  Device-1: NVIDIA GA102 High Definition Audio driver: vfio-pci
  Device-2: Intel DG2 Audio driver: snd_hda_intel
  Device-3: Advanced Micro Devices [AMD/ATI] Rembrandt Radeon High
    Definition Audio driver: snd_hda_intel
  Device-4: Advanced Micro Devices [AMD] Family 17h/19h/1ah HD Audio
    driver: N/A
  Device-5: Sunplus Innovation FHD Camera Microphone
    driver: snd-usb-audio,uvcvideo type: USB
  Device-6: GN Netcom Jabra SPEAK 410 USB driver: jabra,snd-usb-audio,usbhid
    type: USB
  Device-7: Generic USB Audio driver: hid-generic,snd-usb-audio,usbhid
    type: USB
  API: ALSA v: k6.14.0-34-generic status: kernel-api
Network:
  Device-1: Realtek RTL8922AE 802.11be PCIe Wireless Network Adapter
    driver: rtw89_8922ae
  IF: nic-wifi state: down mac: 58:02:05:d4:84:4c
  Device-2: Realtek RTL8126 5GbE driver: r8169
  IF: nic-5g state: down mac: 9c:6b:00:ab:ba:b1
  Device-3: Aquantia AQtion AQC113 NBase-T/IEEE 802.3an Ethernet [Antigua
    10G] driver: atlantic
  IF: nic-10g state: up speed: 2500 Mbps duplex: full mac: 9c:6b:00:ab:ba:a0
  IF-ID-1: br0 state: up speed: 2500 Mbps duplex: unknown
    mac: 4e:66:de:4f:69:f4
  IF-ID-2: docker0 state: down mac: ca:1f:d7:ff:b4:98
  IF-ID-3: virbr0 state: down mac: 52:54:00:20:cb:02
Bluetooth:
  Device-1: IMC Networks Bluetooth Radio driver: btusb type: USB
  Report: hciconfig ID: hci0 state: up address: 58:02:05:D4:84:4D bt-v: 5.3
Drives:
  Local Storage: total: 112.78 TiB used: 74.01 TiB (65.6%)
  ID-1: /dev/nvme0n1 vendor: Samsung model: SSD 990 PRO 4TB size: 3.64 TiB
  ID-2: /dev/sda vendor: Seagate model: ST20000NE000-3G5101 size: 18.19 TiB
  ID-3: /dev/sdb vendor: Western Digital model: WD201KFGX-68BKJN0
    size: 18.19 TiB
  ID-4: /dev/sdc vendor: Western Digital model: WD201KFGX-68BKJN0
    size: 18.19 TiB
  ID-5: /dev/sdd vendor: Seagate model: ST20000NM002C-3X6103 size: 18.19 TiB
  ID-6: /dev/sde vendor: Seagate model: ST20000NM007D-3DJ103 size: 18.19 TiB
  ID-7: /dev/sdf vendor: Seagate model: ST20000NE000-3G5101 size: 18.19 TiB
Partition:
  ID-1: / size: 3.58 TiB used: 185.97 GiB (5.1%) fs: ext4 dev: /dev/nvme0n1p2
  ID-2: /boot/efi size: 1.05 GiB used: 6.1 MiB (0.6%) fs: vfat
    dev: /dev/nvme0n1p1
Swap:
  ID-1: swap-1 type: file size: 8 GiB used: 0 KiB (0.0%) file: /swap.img
Sensors:
  System Temperatures: cpu: 41.8 C mobo: N/A gpu: amdgpu temp: 38.0 C
  Fan Speeds (rpm): fan-1: 1507
Info:
  Memory: total: 128 GiB note: est. available: 124.82 GiB used: 4.6 GiB (3.7%)
  Processes: 605 Uptime: 18m Shell: Sudo inxi: 3.3.37
```
</details>

## GPU allocation

### Intel Arc A310

- **Role**: Host display and transcoding
- **Permanently assigned to**: Ubuntu host
- **Usage**:
  - Primary display output (monitor connection)
  - Desktop environment rendering
  - Jellyfin hardware transcoding (QuickSync) - native linux host
  - Always available for host

### NVIDIA RTX 3090

- **Default state**: Available to host via PRIME render offload
- **Host usage**: Unreal Engine 5 development, Blender, CUDA workloads
- **Gaming mode**: Passed through to Windows 11 VM (exclusive access)

## Virtual machines

### Windows 11 VM

- **GPU**: RTX 3090 (full PCI passthrough when VM is running)
- **Access method**:
  - **Video**: Looking Glass (low-latency frame capture, displayed on Ubuntu desktop)
  - **Input**: SPICE (keyboard/mouse via Looking Glass window, Scroll Lock to release)
- **Monitor**: Stays connected to Arc A310, views Windows via Looking Glass window
- **Usage**: Unreal Engine 5 development, Gaming
- **Benefits**: **No dual-booting** - Everything accessible simultaneously  

### Linux VM

- **GPU**: None (CPU only)
- **Services**: Nextcloud, XWiki, and other web-based self-hosted applications
- **Reason for separation**: Isolation from primary Ubuntu environment - Self-hosted apps in separate VM for security  
- **Access**: SSH, web interfaces (no GUI needed)
- **Usage**: Self-Hosting

## Previous setup

I had 2 old machines; A NAS and a gaming PC. The power supply on the NAS died, and the only way to turn the PC on was to get down and press the power button conveniently hidden below the graphics card on the motherboard.

### NAS (2015)

| Component | Model / Details | Notes | Price $ (USD) |
|-----------|-----------------|-------|--------------------|
| **Case** | [U-NAS NSC-810A](https://www.u-nas.com/xcart/cart.php?target=product&product_id=17640)| Mini-ITX, 8-bay NAS chassis | 220 |
| **PSU** | [SeaSonic SS-350M1U 350 W](https://www.newegg.com/seasonic-usa-ss-350m1u-atx12v-eps12v-350-w-80-plus-gold-certified-power-supply/p/N82E16817151116?Item=N82E16817151116&PID=4897915) | 1U form factor| 65 |
| **Motherboard** | [Supermicro X10SLL-F](https://www.supermicro.com/en/products/motherboard/X10SLL-F) | Mini-ITX, IPMI remote management, basic fan control in bios, no sensors in lmsensors | 215 |
| **CPU** | [Intel Xeon E3-1230 v3](https://www.intel.com/content/www/us/en/products/sku/75054/intel-xeon-processor-e31230-v3-8m-cache-3-30-ghz/specifications.html) | 4C/8T, no integrated GPU | 265 |
| **CPU Cooler** | [Noctua NH-L9i, Low-Profile](https://www.newegg.com/noctua-nh-l9i/p/N82E16835608029?Item=N82E16835608029) | | 50  |
| **Exhaust Fans** | 2x [Noctua NF-F12 PWM, 4-Pin ](https://www.newegg.com/noctua-nf-f12-pwm-case-fan/p/N82E16835608026?Item=N82E16835608026) | | 40 |
| **RAM** | 4×8 GB DDR3-1600 ECC UDIMM | 32 GB total ECC memory | 225 |
| **Storage** | 6×20 TB SATA HDD (various) | snapraid + mergerfs | |
| **GPU** | None |  |  |
| **Total (without drives)** |  |  | 1,080  |

The machine was a great introduction to data hoarding and self‑hosting. However, the system had no iGPU for Jellyfin transcoding, no space for a dedicated graphics card, some cooling issues, and then the power supply died. 

#### Hard drives

Recently replaced all drives.

|Label     |Size (TB) |Make            |Model        |ID                    |Date Purchased |Cost (USD) |
| -------- |:--------:|:--------------:|:-----------:|:--------------------:|:-------------:|:---------:|
|**VOL1**  |20        |Seagate         |IronWolf Pro |ST20000NE000‑3G5101   |2025‑01‑31     |290        |
|**VOL2**  |20        |Western Digital |Red          |WDC WD201KFGX‑68BKJN0 |2022‑11‑28     |341        |
|**VOL3**  |20        |Western Digital |Red          |WDC WD201KFGX‑68BKJN0 |2022‑11‑28     |341        |
|**PAR1**  |20        |Seagate         |Exos X20     |ST20000NM007D‑3DJ103  |2025‑08‑22     |240        |
|**VOL4**  |20        |MDD             |NAS          |—                     |2025‑10‑15     |290        |
|**Dead**  |20        |Seagate         |Exos X20     |ST20000NM007D‑3DJ103  |2025‑08‑22     |240        |
|**PAR2**  |20        |Seagate         |IronWolf Pro |ST20000NE000‑3G5101   |2025‑01‑31     |290        |
|**Total** |          |                |             |                      |               |**2,032**  |

### Gaming PC (2016)
| Component | Model / Details | Notes | Cost (USD) |
|------------|-----------------|--------|-------------|
| **Case** | [Corsair Obsidian Series 450D (CC‑9011049‑WW)](https://www.corsair.com/us/en/p/pc-cases/cc-9011049-ww/obsidian-series-450d-mid-tower-pc-case-cc-9011049-ww) | Mid‑tower ATX | 116 |
| **Motherboard** | [ASUS Z170-A](https://www.amazon.com/dp/B012NH05UW)  | ATX, DDR4 | 155 |
| **CPU** | [Intel Core i7‑6700K](https://www.amazon.com/dp/B012M8LXQW) | 4 cores / 8 threads, 4.0 GHz base (4.2 GHz boost), LGA 1151 | 340 |
| **CPU Cooler** | [Cooler Master Hyper 212 EVO (RR-212E-20PK-R2)](https://www.amazon.com/dp/B005O65JXI) |  | 30 |
| **RAM** | [G.SKILL Ripjaws V Series DDR4 RAM (F4-2400C15D-32GVR)](https://www.amazon.com/dp/B018OB5RB8) | (2x16GB) 32GB 2400MT/s  | 130 |
| **GPU** | NVIDIA GeForce RTX 3090 | Founders Edition 24GB GDDR6   | 900 |
| **GPU Cables** | [12P to 2× 8P PCIe adapter](https://www.amazon.com/dp/B08Z5QYMFR) | 300 cm | 20 |
| **PSU** | [CORSAIR HX1000](https://www.amazon.com/dp/B07RX2DRXQ) | 1000 W, 80+ Platinum, fully modular | 170 |
| **Wifi** | [ASUS Wi-Fi PCI Express Adapter (PCE-AC56)](https://www.amazon.com/dp/B00JNA337K) | | 63 |
| **HDD** | [WD Blue 4TB - 5400 RPM SATA (WD40EZRZ)](https://www.amazon.com/dp/B013HNYV8I) | | 125 |
| **Blu-Ray** | [LG WH16NS40 SATA 16x Blu-ray Disc Rewriter](https://www.amazon.com/dp/B00E7B08MS) | | 60  |
| **Total** |  |  | 2109 |