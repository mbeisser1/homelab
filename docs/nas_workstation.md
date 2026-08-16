# NAS Workstation Overview

I wanted a single workstation that could:

- daily driver
  - software development including unreal 5
- gaming machine
- NAS
- run hosted services (expose via vps)

## Table of contents

- [Evoluent Vertical Mouse 4](#evoluent-vertical-mouse-4)

## Evoluent Vertical Mouse 4

### X11
![Evoluent VerticalMouse 4 button labels](../evoluent_mouse_buttons_labeled.png)

```bash
$ xinput
⎡ Virtual core pointer                                   id=2  [master pointer  (3)]
⎜   ↳ Virtual core XTEST pointer                         id=4  [slave  pointer  (2)]
⎜   ↳ Logitech USB Multimedia Keyboard Consumer Control  id=8  [slave  pointer  (2)]
⎜   ↳ Kingsis Peripherals Evoluent VerticalMouse 4       id=11 [slave  pointer  (2)]

$ lsusb | grep -i evol
Bus 001 Device 007: ID 1a7c:0191 Evoluent VerticalMouse 4
```

```bash
# Map right click to middle button
# Map nothing to right button
# Map middle click to mouse wheel press
$ xinput set-button-map "Kingsis Peripherals Evoluent VerticalMouse 4" 1 3 0 4 5 6 7 8 2 10
```

```text
# Make file: /usr/share/X11/xorg.conf.d/90-evoluent.conf
Section "InputClass"
        Identifier      "Evoluent"
        MatchUSBID      "1a7c:0191"
        Option "ButtonMapping" "1 3 0 4 5 6 7 8 2 10"
EndSection
```
### Wayland

`xinput set-button-map` is an X11 command and does not remap the physical device under Wayland.  
Use a udev hwdb rule to remap the mouse at the evdev level.

- Device: SONiX Evoluent VerticalMouse 4
- Bus: `0003` (Not the physical USB number from `lsusb`)
- Vendor: `1a7c`
- Product: `0191`

```bash
mbeisser@nas-dev:~$ sudo evtest
No device specified, trying to scan all of /dev/input/event*
Available devices:
<snip>
/dev/input/event6:      SONiX Evoluent VerticalMouse D
<snip>
Select the device event number [0-21]: 6
Input driver version is 1.0.1
Input device ID: bus 0x3 vendor 0x1a7c product 0x197 version 0x100
Input device name: "SONiX Evoluent VerticalMouse D"
Supported events:
```

#### Final Button Mapping

| Physical button | Scan code | Result |
|---|---:|---|
| Left click | `90001` | Left click — unchanged |
| Right click | `90002` | Right click — unchanged |
| Middle thumb | `90003` | Right click (`btn_right`) |
| Top thumb | `90004` | Forward (`btn_forward`) |
| Upper thumb | `90005` | Middle click (`btn_middle`) |
| Bottom thumb | `90006` | Back (`btn_side`) |

#### Installation

Create or edit the hwdb rule:

```bash
sudo vim /etc/udev/hwdb.d/99-evoluent.hwdb
```

Paste this exact content:

```text
evdev:input:b0003v1A7Cp0191*
 ID_INPUT_KEY=1
 ID_INPUT_KEYBOARD=1
 KEYBOARD_KEY_90003=btn_right
 KEYBOARD_KEY_90004=btn_forward
 KEYBOARD_KEY_90005=btn_middle
 KEYBOARD_KEY_90006=btn_side
```

Build the hardware database and reload the rule:

```bash
sudo systemd-hwdb update
sudo udevadm trigger
```

Unplug and replug the mouse. Reboot if the mapping still does not apply.
