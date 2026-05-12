# New user setup

This page lists the first steps needed when rebuilding a linux box.

## Bash

```bash
# .bashrc
HISTCONTROL=ignoreboth:erasedups

# for setting history length see HISTSIZE and HISTFILESIZE in bash(1)
HISTSIZE=10000
HISTFILESIZE=20000
```

## Sudo

```bash
sudo apt install neovim
sudo update-alternatives --config editor

sudo visudo

# Allow members of group sudo to execute any command
%sudo   ALL=(ALL:ALL) NOPASSWD:ALL
```

## Groups

The `hosted` group is needed for docker volumes, snapraid, and samba.
The `docker` group is needed for docker.

```bash
# Create group
sudo groupadd -g 20250 hosted
sudo groupadd docker

# Change primary group
sudo usermod -g hosted $USER

# Add to secondary group
sudo usermod -aG docker $USER

# Can start new shell with new group, but reboot
newgrp hosted
```

## Docker

Install via: [Docker Engine on Ubuntu (repository install)](https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository)
