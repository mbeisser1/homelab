# Network

```mermaid
graph LR
  LAN[LAN] -->|WireGuard| VPS[VPS]
  VPS --> Caddy[Caddy]
  Caddy --> Services[Services (Nextcloud, Wiki, etc.)]
```
