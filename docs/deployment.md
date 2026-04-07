# Deployment

## GCP Host

- SSH target: `bitor@34.175.126.128`
- Auth: default SSH keypair configured for current user
- Nginx binary: `/usr/sbin/nginx`

## Runtime Topology

- Single Go binary listening on `127.0.0.1:8080`
- Public domains: `telemetria.bot.nu`, `car-setup.com`
- Nginx on `:80` and `:443`; HTTP → HTTPS redirect for both domains
- HTTPS proxy: `/` and `/api/*` → `http://127.0.0.1:8080`
- In Nginx `location /api/`, use `proxy_pass http://127.0.0.1:8080;` (no trailing slash) to preserve the `/api` prefix.
- Nginx enforces HTTP Basic Auth on **all** routes
- Upload limit: `client_max_body_size 20000M`
- TLS terminated at Nginx via Let's Encrypt

## HTTP Basic Auth

| | Value |
|-|-------|
| User | `racef1` |
| Password | `100fuchupabien` |
| Credential file on host | `/etc/nginx/.htpasswd_rfactor2_engineer` |
| Source file in repo | `deploy/.htpasswd` (hashed) |

## TLS / Certbot

- Cert names: `telemetria.bot.nu`, `car-setup.com`
- Auto-renewal: `certbot.timer`

## Release and Deploy Procedure

```bash
# 1. Build Expo web
cd apps/expo_app && npx expo export --platform web

# 2. Build Go binary (embed Expo dist/ into binary)
cd services/backend_go
GOOS=linux GOARCH=amd64 go build -o ../../rfactor2-engineer ./cmd/server

# 3. Tag
git tag vX.Y.Z && git push --tags

# 4. Upload to host
scp rfactor2-engineer bitor@34.175.126.128:~/

# 5. On host: swap binary
ssh bitor@34.175.126.128 'pkill rfactor2-engineer; mv rfactor2-engineer /opt/rfactor2-engineer && /opt/rfactor2-engineer &'

# 6. Verify
curl -u racef1:100fuchupabien https://car-setup.com/api/models
```

## Operational Notes

- The Go binary must bind to loopback only (`127.0.0.1:8080`); Nginx is the public face.
- Host swap: `/swapfile` 2 GiB, `vm.swappiness=10`.
- `data/` on the remote host persists across deploys (do not wipe it).
- Pre-deploy QA steps: `docs/release_checklist.md`
