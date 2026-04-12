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
- Authentication handled by application-level JWT (no Nginx Basic Auth)
- Upload limit: `client_max_body_size 20000M`
- TLS terminated at Nginx via Let's Encrypt

> Nota: la ejecución actual utiliza un único binario Go y no requiere Docker para la aplicación.

## Authentication

Authentication is handled at the application level via JWT. The legacy Nginx HTTP Basic Auth (`racef1`/`100fuchupabien`) has been removed. See `SPEC_AUTH.md` for the full auth specification.

Admin user: `Mulder_admin` (seeded on startup).

Relevant env vars: `RF2_JWT_SECRET`, `RF2_SMTP_HOST/PORT/USER/PASS/FROM`.

## TLS / Certbot

- Cert names: `telemetria.bot.nu`, `car-setup.com`
- Auto-renewal: `certbot.timer`

## Release and Deploy Procedure

### Fastest path — script automático (recomendado)

```powershell
# Compila, sube y verifica todo end-to-end con un solo comando:
.\scripts\deploy.ps1
```

El script (`scripts/deploy.ps1`) ejecuta en orden:
1. Limpia `GOOS`/`GOARCH` residuales.
2. Compila `linux/amd64` y valida el magic ELF (falla si el binario no es Linux).
3. Sube vía SCP a `/home/bitor/rfactor2-engineer-new`.
4. Para el servicio, reemplaza el binario, lo arranca y verifica `systemctl is-active`.
5. Health check en loopback (`http://127.0.0.1:8080/api/health` → 200).
6. Verificación pública E2E: `/` y `/api/health` deben dar 200.
7. Verifica que el bundle JS del `index.html` también devuelve 200.
8. Muestra los últimos logs del servicio.

Si cualquier paso falla el script para inmediatamente con el error concreto.

### Pasos manuales equivalentes (referencia)

```powershell
# 1. Build Expo web (solo si el frontend cambió)
cd apps/expo_app ; npx expo export --platform web
#    → copiar bundle + index.html a services/backend_go/cmd/server/static/

# 2. Build Go binary para Linux desde PowerShell
cd services/backend_go
$env:GOOS='linux' ; $env:GOARCH='amd64'
go build -o rfactor2-engineer-linux-amd64 ./cmd/server
Remove-Item Env:GOOS ; Remove-Item Env:GOARCH   # ← SIEMPRE limpiar después

# 3. Verificar magic ELF antes de subir
[System.IO.File]::ReadAllBytes(".\rfactor2-engineer-linux-amd64")[0..3]
# Debe mostrar: 127 69 76 70  (= 0x7F E L F)

# 4. Subir y reiniciar
scp .\rfactor2-engineer-linux-amd64 bitor@34.175.126.128:/home/bitor/rfactor2-engineer-new
ssh bitor@34.175.126.128 "sudo systemctl stop rfactor2-engineer && sudo cp /home/bitor/rfactor2-engineer-new /opt/rfactor2_engineer/rfactor2-engineer && sudo chmod +x /opt/rfactor2_engineer/rfactor2-engineer && sudo systemctl start rfactor2-engineer && sleep 2 && sudo systemctl is-active rfactor2-engineer"

# 5. Verificar end-to-end desde el servidor (no desde local)
ssh bitor@34.175.126.128 'curl -s -o /dev/null -w "%{http_code}" -m 10 http://127.0.0.1:8080/api/health'
ssh bitor@34.175.126.128 'curl -s -o /dev/null -w "%{http_code}" -m 15 https://car-setup.com/api/health'
```

## Operational Notes

- The Go binary must bind to loopback only (`127.0.0.1:8080`); Nginx is the public face.
- Host swap: `/swapfile` 2 GiB, `vm.swappiness=10`.
- `data/` on the remote host persists across deploys (do not wipe it).
- Pre-deploy QA steps: `docs/release_checklist.md`

## Guardarraíles de Deploy — Errores comunes y cómo evitarlos

| Error | Causa | Prevención |
|-------|-------|------------|
| Binario Windows en servidor Linux | `$env:GOOS` quedó sin limpiar de una compilación anterior | Usar `scripts/deploy.ps1` que valida el ELF magic antes de subir |
| Servicio caído mucho tiempo | Se sube el binario pero no se verifica que el servicio esté `active` | El script valida `systemctl is-active` y falla explícitamente si no |
| Bundle JS no accesible (404) | El index.html referencia un hash de bundle que no está embebido en el binario | El script verifica que el bundle del index.html devuelve 200 tras el deploy |
| Chrome muestra `chrome-error://chromewebdata/` | Estado residual del browser de cuando el servicio estaba caído | No es un bug de código; el usuario debe abrir en incógnito o hacer Ctrl+Shift+R |
| Verificación de salud falsa positiva | Se verifica solo loopback (`127.0.0.1`) en lugar de la URL pública real | El script verifica SIEMPRE la URL pública desde el propio servidor |
| `go env GOOS` reporta `linux` en host Windows | Env var `$env:GOOS` persistente en la sesión PowerShell de algún build anterior | El script hace `Remove-Item Env:GOOS/GOARCH` + `go env -u GOOS/GOARCH` al inicio |
