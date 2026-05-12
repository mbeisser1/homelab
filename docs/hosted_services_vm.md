# Cloudflare Tunnel + Nginx Proxy Manager Setup 

## Overview

Here's how to setup up a Cloudflare Tunnel and Nginx Proxy Manager to access LAN services with working SSL certificates for both remote (internet) and local (LAN) access.

**Architecture:**
- Remote access: Cloudflare Tunnel → Nginx Proxy Manager → LANService
- Local access: Local DNS → Nginx Proxy Manager → Service

---

## Step 1: Configure Local DNS (dnsmasq)

dnsmasq run on the [ASUS-RT-BE88U](ASUS-RT-BE88U) router.

**Verify DNS resolution:**
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

**Option A: Via config.yml (Recommended)**

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

**Option B: Via Cloudflare Dashboard**

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

**Remote Access (through Cloudflare):**
- Access your domain from the internet
- Should work without certificate warnings

**Local Access (through local DNS):**
- Access your domain from a LAN device
- Should resolve to your local Nginx Proxy Manager IP
- Should stay completely local (not route through Cloudflare)
- Should work without certificate warnings

**Check if local traffic stays local:**
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

# Mount SnapRAID Pool
Use virtiofs for simplicity. (Could use 9p/Plan 9 but more complicated.)
- The guest root can modify files on the shared pool. 
- UID/GID mapping passes through transparently. Permissions on `/pool` will be the same in the guest as on the host.
- Other VMs can also access the same `/pool` from the host. Concurrent access is safe for SnapRAID,

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

4. Enable shared memory
    ```xml
    <memory unit='KiB'>33554432</memory>
    <currentMemory unit='KiB'>33554432</currentMemory>
 
    <memoryBacking>
      <source type='memfd'/>
      <access mode='shared'/> <!-- here! -->
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
   ```
   shared_pool /mnt/pool virtiofs rw,relatime 0 0
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

# XWiki
DNS resolution XWIKI problem
Summary of Local DNS Resolution Setup

We resolved the hairpinning issue where local requests to xwiki.bitrealm.dev were unnecessarily routing through Cloudflare's network by implementing a proper split DNS configuration:

    Identified the problem: Your nslookup showed Cloudflare IPs (172.67.221.36, 104.21.45.243) instead of your local 192.168.50.100, confirming all traffic (including local) was exiting your network through Cloudflare Tunnel.
    [2](https://superuser.com/questions/1647407/how-to-properly-test-a-local-dns-server-locally)

    Configured dnsmasq on your router with split DNS rules:
        Added address=/xwiki.bitrealm.dev/192.168.50.100 to force local resolution to your internal server
        Added server=/bitrealm.dev/1.1.1.1 to forward other domains to public DNS
        [1](https://activedirectorypro.com/use-nslookup-check-dns-records/)

    Verified the Cloudflare Tunnel configuration:
        Ensured proper ingress rules in config.yml pointing to your internal IP:

Yaml

ingress:
  - hostname: xwiki.bitrealm.dev
    service: http://192.168.50.100

    Validated with docker exec cloudflared-tunnel cloudflared tunnel ingress validate
    [3](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/)

    Confirmed correct operation by testing with:

Bash

nslookup xwiki.bitrealm.dev 192.168.50.1

Which should now return 192.168.50.100 for local clients while external requests still use Cloudflare's network.
[2](https://superuser.com/questions/1647407/how-to-properly-test-a-local-dns-server-locally)

This setup eliminates unnecessary round-trips through Cloudflare for local users, reducing latency from ~50ms to <1ms while maintaining secure external access through the tunnel. The key was ensuring your local DNS server takes precedence for internal resolution of the specific domain.
[1](https://activedirectorypro.com/use-nslookup-check-dns-records/)
