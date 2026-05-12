# Jellyfin Setup

# User and Groups
Check [user setup](User-Setup).

Ensure the user primary group is `hosted` to match the `mergerfs` pool permissions. (Samba shares `/pool` as well!)
```sh
id mbeisser
uid=1000(mbeisser) gid=20250(hosted) groups=20250(hosted),123(docker)
```

The render group allows unprivileged access to GPU devices. We'll add to the Jellyfin container
```sh
getent group render | cut -d: -f3
```

# GPU
Intel Arc A310
- [Intel supported gpus](https://dgpu-docs.intel.com/devices/hardware-table.html#gpus-with-supported-drivers)
- [Intel Linux Driver instructions](https://dgpu-docs.intel.com/driver/client/overview.html)

An HWE kernel is not required.
| PCI IDs | Name | Architecture | Codename | Kernel | EU Number |
|---------|------|--------------|----------|--------|-----------|
| 56A6 | Intel Arc A310 Graphics | Xe-HPG | Alchemist | 6.2 | 96 |

Install the drivers
```sh
sudo apt-get update
sudo apt-get install -y software-properties-common

# Add the intel-graphics PPA
sudo add-apt-repository -y ppa:kobuk-team/intel-graphics

# Install the compute-related packages
sudo apt-get install -y libze-intel-gpu1 libze1 intel-metrics-discovery intel-opencl-icd clinfo intel-gsc

# Install the media-related packages.
sudo apt-get install -y intel-media-va-driver-non-free libmfx-gen1 libvpl2 libvpl-tools libva-glx2 va-driver-all vainfo

# For pytorch (optional)
sudo apt-get install -y libze-dev intel-ocloc

# hardware ray tracing support
sudo apt-get install -y libze-intel-gpu-raytracing
```
Verify drivers:
```sh
clinfo | grep "Device Name"
```
Check GPU usage:
```sh
sudo intel_gpu_top
```

# Docker
- [Docker Hub images](https://hub.docker.com/r/jellyfin/jellyfin/)
- [Docker compose](https://github.com/mbeisser1/homelab/tree/main/nas/docker/jellyfin)

We don't want to run the container as root. That screws up our permissions.

Make docker volume directories.
```sh
mkdir -p ~/hosted/docker/jellyfin/{config,cache}
```

Find the correct device:
```sh
# Be sure to list the `renderer` and `card` in the compose file.
ls -la /dev/dri/by-path/
lshw -C display
```

Jellyfin access: 
```
http://127.0.0.1:8096 
```

Check if Jellyfin can see the GPU:
```sh
docker exec jellyfin /usr/lib/jellyfin-ffmpeg/vainfo
```

| Jellyfin Codec  | VAProfile Name       | Decode (VLD) | Encode (EncSliceLP) |
|-----------------|----------------------|--------------|-----------------------|
| H.264 (AVC)     | VAProfileH264*       | Yes          | Yes                   |
| H.265 (HEVC)    | VAProfileHEVC*       | Yes          | Yes                   |
| H.265 10-bit    | VAProfileHEVCMain10  | Yes          | Yes                   |
| VP9             | VAProfileVP9*       | Yes          | Yes                   |
| AV1             | VAProfileAV1Profile0  | Yes          | Yes                   |
| MPEG-2          | VAProfileMPEG2*      | Yes          | No                    |
| VC-1            | VAProfileVC1*       | Yes          | No                    |


# Jellyfin Config
## Options
- Don't enable nfo's if the filesystem mount is read-only.
- Make sure to enable hardware decoding for Trickplay

## Transcoding
Hardware Acceleration: Intel Quicksync (QSV)

Enable hardware decoding for:
- ✅ H264
- ✅ HEVC
- ✅ MPEG2
- ✅ VC1
- ❌ VP8
- ✅ VP9
- ✅ AV1
- ✅ HEVC 10bit
- ✅ VP9 10bit
- ✅ HEVC RExt 8/10bit
- ✅ HEVC RExt 12bit
- ✅ Prefer OS native DXVA or VA-API hardware decoders

Hardware encoding options
- ✅ Enable hardware encoding
- ✅ Enable Intel Low-Power H.264 hardware encoder
- ✅ Enable Intel Low-Power HEVC hardware encoder

Encoding format options
- ✅ Allow encoding in HEVC format
- ✅ Allow encoding in AV1 format