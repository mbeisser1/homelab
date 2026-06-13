# Cloudflare Tunnel + Nginx Proxy Manager Setup

## Table of contents

- [Cloudflare Tunnel + Nginx Proxy Manager Setup](#cloudflare-tunnel--nginx-proxy-manager-setup)
  - [Table of contents](#table-of-contents)
  - [Overview](#overview)
    - [Architecture](#architecture)
  - [Step 1: Configure Local DNS (dnsmasq)](#step-1-configure-local-dns-dnsmasq)
    - [Verify DNS resolution](#verify-dns-resolution)
  - [Step 2: Create Cloudflare API Token](#step-2-create-cloudflare-api-token)
  - [Step 3: Configure Cloudflare Tunnel](#step-3-configure-cloudflare-tunnel)
    - [Option A: Via config.yml (recommended)](#option-a-via-configyml-recommended)
    - [Option B: Via Cloudflare Dashboard](#option-b-via-cloudflare-dashboard)
  - [Step 4: Set Up Proxy Host in Nginx Proxy Manager](#step-4-set-up-proxy-host-in-nginx-proxy-manager)
  - [Step 5: Request Let's Encrypt Certificate](#step-5-request-lets-encrypt-certificate)
  - [Step 6: Verify Both Access Methods](#step-6-verify-both-access-methods)
    - [Remote access (through Cloudflare)](#remote-access-through-cloudflare)
    - [Local access (through local DNS)](#local-access-through-local-dns)
    - [Check if local traffic stays local](#check-if-local-traffic-stays-local)
  - [Docker Compose Example](#docker-compose-example)
  - [Mount SnapRAID pool (virtiofs)](#mount-snapraid-pool-virtiofs)
  - [Host Machine Setup (Ubuntu)](#host-machine-setup-ubuntu)
  - [Guest VM Setup](#guest-vm-setup)
  - [Restart Services](#restart-services)
  - [XWiki: local DNS (split DNS)](#xwiki-local-dns-split-dns)
    - [Summary](#summary)
    - [Problem](#problem)
    - [dnsmasq on the router](#dnsmasq-on-the-router)
    - [Cloudflare Tunnel ingress](#cloudflare-tunnel-ingress)
    - [Verification](#verification)

## Overview

Here's how to set up a Cloudflare Tunnel and Nginx Proxy Manager to access LAN services with working SSL certificates for both remote (internet) and local (LAN) access.

### Architecture

- Remote access: Cloudflare Tunnel → Nginx Proxy Manager → LAN service
- Local access: Local DNS → Nginx Proxy Manager → service

---

## Step 1: Configure Local DNS (dnsmasq)

`dnsmasq` runs on the [ASUS RT BE88U](router.md) router.

### Verify DNS resolution

```bash
nslookup stream.bitrealm.dev
```

Should return your local Nginx Proxy Manager IP.

---

## Step 2: Create Cloudflare API Token

Needed for Let's Encrypt DNS validation in Nginx Proxy Manager.

1. Go to **Cloudflare Dashboard** → **My Profile** → **API Tokens**
2. Click **Create Token**
3. Set permissions:
   - **Permissions:** Zone → DNS → Edit
   - **Zone Resources:** Include → Specific zone → Your domain
4. **Create Token** and copy the token (shown only once)

---

## Step 3: Configure Cloudflare Tunnel

Update your Cloudflare Tunnel to point to Nginx Proxy Manager on **port 8080** (the proxy port, not 8081).

### Option A: Via config.yml (recommended)

Edit `~/.cloudflared/config.yml` or your Docker config volume:

```yaml
tunnel: your-tunnel-name
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: yourdomain.com
    service: http://nginx-proxy-manager:80
  - hostname: "*.yourdomain.com"
    service: http://nginx-proxy-manager:80
  - service: http_status:404
```

Restart the tunnel:

```bash
docker-compose restart cloudflare-tunnel
```

### Option B: Via Cloudflare Dashboard

1. Go to **Tunnels** → Your tunnel → **Public Hostname**
2. Edit the hostname to point to: `http://192.168.1.100:80`
   - Replace with your Nginx Proxy Manager IP and **port 80**

---

## Step 4: Set Up Proxy Host in Nginx Proxy Manager

For each service you want to expose (e.g., `stream.bitrealm.dev`):

1. Go to **Proxy Hosts** → **Add Proxy Host**
2. **Domain Names:** Enter your subdomain (e.g., `stream.bitrealm.dev`)
3. **Scheme:** `http`
4. **Forward Hostname/IP:** Your service's local IP (e.g., `192.168.50.100`)
5. **Forward Port:** Your service's port (e.g., `8096`)
6. Go to **SSL tab**

---

## Step 5: Request Let's Encrypt Certificate

In the **SSL tab** of your Proxy Host:

1. **Certificate:** Select **Request a new SSL Certificate**
2. **DNS Provider:** Select **Cloudflare**
3. **Credentials File Content:** Paste your Cloudflare API token (from Step 2)
4. **Propagation Seconds:** Leave empty (uses default)
5. **Email Address:** Enter an email for Let's Encrypt notifications
6. **Check:** Agree to Let's Encrypt Terms of Service
7. **Force SSL:** Enable (optional but recommended)
8. Click **Save**

Wait 2-5 minutes for certificate validation and issuance.

---

## Step 6: Verify Both Access Methods

### Remote access (through Cloudflare)

- Access your domain from the internet
- Should work without certificate warnings

### Local access (through local DNS)

- Access your domain from a LAN device
- Should resolve to your local Nginx Proxy Manager IP
- Should stay completely local (not route through Cloudflare)
- Should work without certificate warnings

### Check if local traffic stays local

- Monitor Cloudflare Tunnel logs—LAN access should **not** appear
- Verify device is using correct DNS (should resolve to `192.168.1.100`)

---

## Docker Compose Example

```yaml
services:
  cloudflare-tunnel:
    image: cloudflare/cloudflared:latest
    container_name: cloudflare-tunnel
    restart: unless-stopped
    environment:
      - TUNNEL_NAME=your-tunnel-name
      - TUNNEL_TOKEN=$TUNNEL_TOKEN
    volumes:
      - ./config:/etc/cloudflared
    command: tunnel --no-autoupdate run

  nginx-proxy-manager:
    image: jc21/nginx-proxy-manager:latest
    container_name: nginx-proxy-manager
    restart: unless-stopped
    ports:
      - "80:80"
      - "81:81"
      - "443:443"
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
```

## Mount SnapRAID pool (virtiofs)

Use virtiofs for simplicity. (Could use 9p/Plan 9 but more complicated.)

- The guest root can modify files on the shared pool.
- UID/GID mapping passes through transparently. Permissions on `/pool` will be the same in the guest as on the host.
- Other VMs can also access the same `/pool` from the host. Concurrent access is safe for SnapRAID.

## Host Machine Setup (Ubuntu)

1. Install required packages:

   ```bash
   sudo apt update
   sudo apt install qemu-guest-agent libvirt-daemon-system virtiofsd
   ```

2. Create socket directory with proper permissions:

   ```bash
   sudo mkdir -p /var/run/virtiofsd
   sudo chown root:libvirt-qemu /var/run/virtiofsd
   sudo chmod 770 /var/run/virtiofsd
   ```

3. Edit VM configuration:

   ```bash
   virsh edit nas-hosted
   ```

4. Enable shared memory:

   ```xml
   <memory unit='KiB'>33554432</memory>
   <currentMemory unit='KiB'>33554432</currentMemory>

   <memoryBacking>
     <source type='memfd'/>
     <access mode='shared'/>
   </memoryBacking>
   ```

5. Add to `<devices>` section:

   ```xml
   <filesystem type='mount' accessmode='passthrough'>
     <driver type='virtiofs'/>
     <source dir='/pool'/>
     <target dir='shared_pool'/>
     <address type='pci' domain='0x0000' bus='0x07' slot='0x00' function='0x0'/>
   </filesystem>
   ```

## Guest VM Setup

1. Install required packages:

   ```bash
   sudo apt update
   sudo apt install qemu-guest-agent
   ```

2. Create mount point:

   ```bash
   sudo mkdir -p /pool
   ```

3. Mount the shared directory:

   ```bash
   sudo mount -t virtiofs shared_pool /pool
   ```

4. Add to `/etc/fstab`:

   ```fstab
   shared_pool /pool virtiofs rw,relatime 0 0
   ```

## Restart Services

1. On host, restart libvirt service:

   ```bash
   sudo systemctl restart libvirtd
   ```

2. On VM, restart the guest services:

   ```bash
   sudo systemctl restart qemu-guest-agent
   ```

## XWiki: local DNS (split DNS)

### Summary

Local requests to `xwiki.bitrealm.dev` were hairpinning through Cloudflare (public IPs from `nslookup`) instead of hitting the LAN host. Split DNS on the router fixes that: internal names resolve to the VM, other names under the zone still use public DNS, and the tunnel keeps working for remote users.

### Problem

`nslookup` showed Cloudflare anycast IPs (e.g. `172.67.x.x`, `104.21.x.x`) instead of `192.168.50.100`, so even LAN clients left the network for DNS-related paths. See [How to properly test a local DNS server locally](https://superuser.com/questions/1647407/how-to-properly-test-a-local-dns-server-locally).

### dnsmasq on the router

- `address=/xwiki.bitrealm.dev/192.168.50.100` — force this hostname to the internal NPM/service IP.
- `server=/bitrealm.dev/1.1.1.1` — forward other `bitrealm.dev` queries to public DNS as needed.

Reference: [Use nslookup to check DNS records](https://activedirectorypro.com/use-nslookup-check-dns-records/).

### Cloudflare Tunnel ingress

Ensure ingress sends the hostname to the internal service, for example:

```yaml
ingress:
  - hostname: xwiki.bitrealm.dev
    service: http://192.168.50.100
```

Validate the tunnel config when using a local config file, e.g. `docker exec cloudflared-tunnel cloudflared tunnel ingress validate`. See [Cloudflare Tunnel configuration file](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/).

### Verification

```bash
nslookup xwiki.bitrealm.dev 192.168.50.1
```

LAN clients should get `192.168.50.100`; external traffic still uses Cloudflare as intended.

This removes unnecessary round-trips for local users (latency drops from on the order of tens of ms to under 1 ms on LAN) while keeping remote access through the tunnel. The important part is that **local DNS wins first** for internal hostnames.
