#!/bin/bash
# WireGuard health check

sudo wg show | awk '
/interface:/{iface=$2}
/public key:/{peer=$3}
/latest handshake:/{h=$3" "$4" "$5}
/transfer:/{rx=$2" "$3; tx=$5" "$6;
  printf "Interface: %s\nPeer: %s\n Last Handshake: %s\n RX: %s\n TX: %s\n\n", iface, peer, h, rx, tx }'
