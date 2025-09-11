# Stage 1: Build Caddy with Cloudflare DNS plugin
FROM caddy:2-builder AS builder

RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare

# Stage 2: Create final image
FROM caddy:2

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
