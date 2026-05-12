# Creating a Network Bridge for KVM/QEMU VMs on Ubuntu with NetworkManager

## Overview

This guide covers creating a network bridge on an Ubuntu host using NetworkManager/netplan,
then connecting a Windows 11 KVM/QEMU VM to it so the VM has direct access to the physical
network. This is preferable to NAT (the default libvirt network) because the VM appears as
a regular device on your network with full access to network resources including host services.

---

## Prerequisites

- Ubuntu host using NetworkManager (not systemd-networkd)
- KVM/QEMU and libvirt installed
- A physical network interface connected to your network (this guide uses `nic-10g`)
- A Windows 11 VM already created in libvirt

---

## Step 1: Verify You Are Using NetworkManager

```bash
cat /etc/netplan/*.yaml | grep renderer
```

If the output shows `renderer: NetworkManager`, proceed with this guide. If it shows
`renderer: networkd`, you are using systemd-networkd and this guide does not apply.

---

## Step 2: Identify Your Physical Network Interface

```bash
ip addr
```

Note the following for your primary interface:
- Interface name (e.g., `nic-10g`, `eth0`, `enp3s0`)
- Current IP address
- MAC address

---

## Step 3: Disable Cloud-Init Network Management

This prevents cloud-init from overwriting your network configuration on reboot.

```bash
sudo vim /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
```

Add:

```yaml
network: {config: disabled}
```

---

## Step 4: Create the Bridge Netplan Configuration

```bash
sudo vim /etc/netplan/02-bridge.yaml
```

Add the following, replacing `nic-10g` with your interface name:

```yaml
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    nic-10g:
      dhcp4: no
      dhcp6: no
  bridges:
    br0:
      interfaces: [nic-10g]
      dhcp4: yes
      dhcp6: no
```

If you prefer a static IP instead of DHCP:

```yaml
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    nic-10g:
      dhcp4: no
      dhcp6: no
  bridges:
    br0:
      interfaces: [nic-10g]
      addresses: [192.168.50.100/24]
      routes:

- to: default
          via: 192.168.50.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
```

---

## Step 5: Set Correct File Permissions

Netplan requires configuration files to not be world-readable:

```bash
sudo chmod 600 /etc/netplan/*.yaml
```

---

## Step 6: Apply the Configuration

Test first (reverts automatically after 120 seconds if not confirmed):

```bash
sudo netplan try
```

Press Enter to accept if everything looks correct. Or apply directly:

```bash
sudo netplan apply
```

---

## Step 7: Verify the Bridge

Check that `br0` is up and has an IP address:

```bash
ip addr show br0
```

Expected output:
- State: `UP`
- An IP address on your network

Check that the physical interface is enslaved to the bridge:

```bash
ip addr show nic-10g
```

Expected output:
- No IP address on this interface
- `master br0` shown in the output

Verify NetworkManager connections:

```bash
nmcli connection show
```

You should see `netplan-br0` and `netplan-nic-10g` listed as active connections.

---

## Step 8: Update Router DHCP Reservation (If Applicable)

If your router assigns a static IP to the host based on MAC address, you need to update
the reservation because the bridge has a different MAC than the physical interface.

Get the bridge MAC address:

```bash
ip link show br0 | grep link/ether
```

Log into your router and update the DHCP reservation to use the bridge MAC address.

Then renew the DHCP lease on the host:

```bash
sudo nmcli connection down netplan-br0
sudo nmcli connection up netplan-br0
ip addr show br0
```

Verify the host received the correct IP address.

---

## Step 9: Update the VM Network Configuration

Shut down the VM:

```bash
virsh shutdown your-vm-name
```

Edit the VM XML:

```bash
virsh edit your-vm-name
```

Find the `<interface>` block and replace it entirely with:

```xml
<interface type='bridge'>
  <mac address='52:54:00:a9:40:15'/>
  <source bridge='br0'/>
  <model type='virtio'/>
  <driver name='vhost' queues='6'/>
</interface>
```

Keep your existing MAC address. Adjust `queues` to match your CPU core count if desired.

Start the VM:

```bash
virsh start your-vm-name
```

---

## Step 10: Configure Windows Networking

The VM should receive a DHCP address on your physical network. To set a static IP instead,
run the following in Windows PowerShell as Administrator:

```powershell
# List adapters to find the correct interface name
Get-NetAdapter

# Set static IP
New-NetIPAddress -InterfaceAlias &quot;Ethernet&quot; -IPAddress 192.168.50.150 -PrefixLength 24 -DefaultGateway 192.168.50.1

# Set DNS
Set-DnsClientServerAddress -InterfaceAlias &quot;Ethernet&quot; -ServerAddresses 192.168.50.1, 8.8.8.8
```

---

## Step 11: Test Connectivity

From Windows PowerShell:

```powershell
# Test gateway
ping 192.168.50.1

# Test host
ping 192.168.50.100

# Test internet
ping 8.8.8.8

# Map a Samba share on the host
net use P: \\192.168.50.100\ShareName
```

---

## Troubleshooting

**Bridge does not get an IP after applying netplan:**

```bash
sudo nmcli connection down netplan-nic-10g
sudo nmcli connection up netplan-br0
ip addr show br0
```

**Physical interface still has an IP address:**

```bash
sudo netplan apply
ip addr
```

Verify `nic-10g` shows `master br0` and has no IP address of its own.

**VM does not get an IP on the physical network:**

Verify the bridge is UP:

```bash
ip addr show br0
```

Verify the VM is using the bridge:

```bash
virsh dumpxml your-vm-name | grep -A5 interface
```

Restart the VM:

```bash
virsh shutdown your-vm-name &amp;&amp; virsh start your-vm-name
```

**Lost network access after applying netplan:**

If you used `netplan try`, wait 120 seconds and the configuration will revert automatically.
If you used `netplan apply`, reboot the host to restore the previous configuration, then
check your YAML for indentation errors (YAML is whitespace-sensitive).

---

## Result

After completing this guide:

- `br0` is the host's active network interface with an IP on your physical network
- `nic-10g` is enslaved to `br0` and has no IP of its own
- The Windows VM is connected to `br0` and appears as a regular device on your network
- The VM has full access to host services (Samba, etc.) and all other network devices
