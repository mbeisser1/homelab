# Network

```mermaid
graph LR
  NAS[NAS] <-->|WireGuard| VPS[VPS]
  VPS --> Caddy[Caddy]
  Caddy --> Services[Services: Nextcloud, Wiki, etc.]
```
