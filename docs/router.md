# ASUS RT BE88U

Asus [product page](https://www.asus.com/us/networking-iot-servers/wifi-routers/asus-gaming-routers/rt-be88u/).

Internet is only 1G up/down, but there might be advantages for NFS and SAMBA if not mounting in VMs.

## Network ports

| Port Type     | Speed | Quantity | Function               |
| ------------- | ----- | -------- | ---------------------- |
| Multi-Gigabit | 10G   | 1        | WAN/LAN (Switchable)   |
| Multi-Gigabit | 2.5G  | 1        | WAN/LAN (Switchable)   |
| SFP+          | 10G   | 1        | SFP+ (Transceiver)     |
| Gigabit       | 2.5G  | 4        | LAN                    |
| Gigabit       | 1G    | 4        | LAN                    |

**Total: 11 ports** (10 RJ45 + 1 SFP+)

Power Consumption: ~10 Watts

## Merlin firmware

Latest Stable: [3006.102.5](https://www.asuswrt-merlin.net/)
Date: 2025-10-04

Download and install for `dnsmasq`.

## Config options

### Network

#### Main network

- WIFI7 Mode - No
- MLO Frounthaul - No

#### Guest network pro

- Make a new guest network so the VLAN will work correctly, i.e. the main network can talk to devices on the guest network but not vice versa.
- Access Intranet - No
- Set AP Isolated - Yes

### LAN

- Setup dhcp range
- Set DNS (don't set at WAN level)
  - 9.9.9.9 (quad nine)
  - 1.1.1.1 (cloud flare)

| Client Name               | MAC Address       | IP Address     |
| ------------------------- | ----------------- | -------------- |
| NAS Workstation (10G NIC) | 4E:66:DE:4F:69:F4 | 192.168.50.100 |
| Windows 11 VM             | VM assigned       | 192.168.50.110 |
| NAS Hosted                | VM assigned       | 192.168.50.120 |
| Brother Printer HL-2280DW | 00:80:92:CB:6B:AE | 192.168.50.200 |

### VPN

#### VPN Fusion

- Add NordVPN
  - Generate new token: Home > NordVPN > Access token
- Apply to all devices - No
  - Add devices as needed

### Administration

#### System

- Enable JFFS custom scripts and configs
  (This allows dnsmasq changes to survive reboots)

### dnsmasq

LAN split DNS for `bitrealm.dev` homelab services. Overrides public Cloudflare DNS so LAN clients resolve service hostnames to `nas-dev` (`192.168.50.100`) where Nginx Proxy Manager runs. Remote access over Tailscale uses `<service>.ts.bitrealm.dev` instead - see [Tailscale + NPM](tailscale.md).

**Prerequisite:** Enable JFFS custom scripts and configs under [Administration → System](#administration) so changes survive reboots.

#### SSH steps

```bash
# Connect to router
ssh bitadmin@192.168.50.1

# Edit dnsmasq config (append one block per service)
vi /jffs/configs/dnsmasq.conf.add
```

```
address=/stream.bitrealm.dev/192.168.50.100
address=/stream.bitrealm.dev/::1   # disable ipv6 locally for this hostname
```

```bash
service restart_dnsmasq
```

Add a matching NPM proxy host for each `address=` entry (e.g. `stream.bitrealm.dev` without the `.ts` suffix).

- Use `/jffs/configs/dnsmasq.conf.add` (not `/etc/dnsmasq.conf` - changes won't survive reboot)
- Entries automatically merge with the firmware's default configuration
- Changes persist across reboots and firmware updates
- LAN DNS servers are set under [LAN](#lan) (9.9.9.9, 1.1.1.1); `address=` overrides apply before upstream resolution

#### Verify

```bash
nslookup stream.bitrealm.dev 192.168.50.1
```

Should return `192.168.50.100`, not a Cloudflare anycast IP.

## Tailscale

IP forwarding is what allows your Linux machine to act as a router by passing network traffic between different networks.

[2](https://www.twingate.com/blog/glossary/ip-forwarding)

### Why it matters for Tailscale

By default, Linux systems are configured to only handle traffic destined for themselves. When IP forwarding is disabled, your machine will drop any packets that aren't addressed directly to it.

When you advertise routes in Tailscale, you're essentially telling your machine to become a subnet router—a gateway that forwards traffic between your Tailscale network and your local network (or other subnets).

[3](https://tailscale.com/kb/1019/subnets)
[1](https://tailscale.com/kb/1406/quick-guide-subnets)

```bash
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
```
