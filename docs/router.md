# ASUS RT BE88U

Asus [product page](https://www.asus.com/us/networking-iot-servers/wifi-routers/asus-gaming-routers/rt-be88u/).

Internet is only 1G up/down, but there might be advantages for NFS and SAMBA if not mounting in VMs.

## Table of contents

- [Network ports](#network-ports)
- [Merlin firmware](#merlin-firmware)
- [Config options](#config-options)
  - [Network](#network)
  - [LAN](#lan)
  - [VPN](#vpn)
  - [Administration](#administration)
  - [dnsmasq](#dnsmasq)
- [Tailscale](#tailscale)

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

#### Example config

Paste at the top of `/jffs/configs/dnsmasq.conf.add`:

```
# dnsmasq.conf.add - LAN DNS overrides for bitrealm.dev
# File: /jffs/configs/dnsmasq.conf.add (survives reboot; do not use /etc/dnsmasq.conf)
# After edits: service restart_dnsmasq
#
# local=/domain/     - Answer for this domain locally; never forward to upstream DNS.
# address=/host/ip   - Static A record. /host/ also matches subdomains of host.
# address=/host/::1  - Optional. Maps hostname to IPv6 loopback so clients skip AAAA lookups.
# server=/domain/ip  - Forward all other queries for this domain to upstream DNS (here: Cloudflare).
#
# LAN homelab services -> nas-dev NPM (192.168.50.100)
# Tailscale services   -> nas-dev Tailscale IP (100.94.65.10); matches Cloudflare *.ts A record
# Unlisted bitrealm.dev names -> server= forwards to 1.1.1.1 (website, mail, etc.)

local=/dockge.bitrealm.dev/
address=/dockge.bitrealm.dev/192.168.50.100

local=/immich.bitrealm.dev/
address=/immich.bitrealm.dev/192.168.50.100

local=/stream.bitrealm.dev/
address=/stream.bitrealm.dev/192.168.50.100

local=/xwiki.bitrealm.dev/
address=/xwiki.bitrealm.dev/192.168.50.100

local=/backrest.bitrealm.dev/
address=/backrest.bitrealm.dev/192.168.50.100

local=/router.bitrealm.dev/
address=/router.bitrealm.dev/192.168.50.1

local=/printer.bitrealm.dev/
address=/printer.bitrealm.dev/192.168.50.200

local=/ts.bitrealm.dev/
address=/ts.bitrealm.dev/100.94.65.10

server=/bitrealm.dev/1.1.1.1
```

Add a matching NPM proxy host for each service hostname (both `<service>.bitrealm.dev` and `<service>.ts.bitrealm.dev` on the same host). See [Tailscale + NPM](tailscale.md).

#### SSH steps

```bash
# Connect to router
ssh bitadmin@192.168.50.1

# Edit dnsmasq config
vi /jffs/configs/dnsmasq.conf.add
```

```bash
service restart_dnsmasq
```

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
