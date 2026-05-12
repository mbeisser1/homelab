# NAS Workstation Overview

I wanted a single workstation that could:

- daily driver
  - software development including unreal 5
- gaming machine
- NAS
- run hosted services (expose via vps)

## Evoluent Vertical Mouse 4

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
