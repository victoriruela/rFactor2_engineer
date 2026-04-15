# deploy.ps1 - Compila Go para Linux/amd64, sube al remoto y verifica E2E.
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\deploy.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -- Constantes --
$RemoteUser    = "bitor"
$RemoteHost    = "34.175.126.128"
$SshTarget     = "$RemoteUser@$RemoteHost"
$RemoteNewBin  = "/home/bitor/rfactor2-engineer-new"
$RemoteInstall = "/opt/rfactor2_engineer/rfactor2-engineer"
$Service       = "rfactor2-engineer"
$PublicURL     = "https://car-setup.com"
$HealthURL     = "$PublicURL/api/health"

$Root     = Split-Path $PSScriptRoot -Parent
$GoDir   = Join-Path $Root "services\backend_go"
$BinName = "rfactor2-engineer-linux-amd64"
$BinPath = Join-Path $GoDir $BinName
$StaticIndexPath = Join-Path $GoDir "cmd\server\static\index.html"

# -- Helpers --
function Step($msg) { Write-Host "" ; Write-Host "==> $msg" -ForegroundColor Cyan }
function OK($msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Die($msg)  { Write-Host "    FAIL: $msg" -ForegroundColor Red ; exit 1 }

function Get-EntryHashFromHtml($html) {
    if ($html -match 'entry-([a-f0-9]+)\.js') {
        return $Matches[1]
    }
    return $null
}

function Ssh-Run($cmd) {
    $out = & ssh $SshTarget $cmd 2>&1
    return ($out | Out-String).Trim()
}

# -- 1. Limpiar GOOS/GOARCH residuales --
Step "Limpiando variables GOOS/GOARCH residuales"
Remove-Item Env:GOOS   -ErrorAction SilentlyContinue
Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
& go env -u GOOS   2>$null
& go env -u GOARCH 2>$null
$nativeOS = (& go env GOOS).Trim()
if ($nativeOS -ne "windows") {
    Write-Warning "go env GOOS devuelve '$nativeOS' (inesperado). Forzando limpieza."
    $env:GOOS = ""; $env:GOARCH = ""
}
OK "GOOS/GOARCH limpios. GOOS del entorno = $(& go env GOOS)"

# -- 2. Compilar linux/amd64 --
Step "Compilando para linux/amd64"
# Guardarrail estricto: regenerar siempre el bundle web antes del build Go.
$ExpoDir = Join-Path $Root "apps\expo_app"
$ExpoDistDir = Join-Path $ExpoDir "dist"
$StaticEmbedDir = Join-Path $GoDir "cmd\server\static"

Push-Location $ExpoDir
& npx expo export --platform web
$expoBuildExit = $LASTEXITCODE
Pop-Location
if ($expoBuildExit -ne 0) { Die "expo export fallo con exit $expoBuildExit" }
if (-not (Test-Path $ExpoDistDir)) { Die "No se encontro Expo dist en $ExpoDistDir" }

# Copiar Expo dist al directorio static embebido antes de compilar.
Remove-Item "$StaticEmbedDir\*" -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item "$ExpoDistDir\*" $StaticEmbedDir -Recurse -Force
OK "Expo dist copiado a static embed"

$distIndexPath = Join-Path $ExpoDistDir "index.html"
if (-not (Test-Path $distIndexPath)) { Die "No se encontro index.html en Expo dist" }
$distIndexHtml = Get-Content -Path $distIndexPath -Raw
$expectedEntryHash = Get-EntryHashFromHtml $distIndexHtml
if (-not $expectedEntryHash) { Die "No se encontro entry-*.js en index.html de Expo dist" }
# Guardarrail: normalizar script de entrada web como modulo para permitir import.meta
if (Test-Path $StaticIndexPath) {
    $indexHtmlLocal = Get-Content -Path $StaticIndexPath -Raw
    $normalizedHtml = $indexHtmlLocal -replace '<script\s+src="(/_expo/static/js/web/entry-[a-f0-9]+\.js)"\s+defer></script>', '<script type="module" src="$1" defer></script>'
    if ($normalizedHtml -ne $indexHtmlLocal) {
        Set-Content -Path $StaticIndexPath -Value $normalizedHtml -NoNewline
        OK "index.html local normalizado a script type=module"
    }
}

# Guardarrail: validar que static embebido apunta al mismo hash que Expo dist.
$staticIndexHtml = Get-Content -Path $StaticIndexPath -Raw
$embeddedEntryHash = Get-EntryHashFromHtml $staticIndexHtml
if (-not $embeddedEntryHash) { Die "No se encontro entry-*.js en static/index.html embebido" }
if ($embeddedEntryHash -ne $expectedEntryHash) {
    Die "Hash de bundle desalineado: dist=$expectedEntryHash static=$embeddedEntryHash"
}
OK "Hash bundle sincronizado: $expectedEntryHash"

Set-Location $GoDir
$env:GOOS   = "linux"
$env:GOARCH = "amd64"
$buildTs = Get-Date -Format 'yyyyMMddHHmmss'
& go build -ldflags "-X main.buildVersion=$buildTs" -o $BinName ./cmd/server
$buildExit = $LASTEXITCODE
Remove-Item Env:GOOS   -ErrorAction SilentlyContinue
Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
if ($buildExit -ne 0) { Die "go build fallo con exit $buildExit" }
$info = Get-Item $BinPath
OK "Binario: $($info.Name)  $([math]::Round($info.Length/1MB, 1)) MB  $($info.LastWriteTime)"

# Guardarrail ELF
$magic = [System.IO.File]::ReadAllBytes($BinPath)[0..3]
$isElf = ($magic[0] -eq 0x7F -and $magic[1] -eq 0x45 -and $magic[2] -eq 0x4C -and $magic[3] -eq 0x46)
if (-not $isElf) { Die "El binario NO es ELF Linux. Bytes: $magic. Build uso OS incorrecto." }
OK "ELF magic correcto (binario Linux amd64 valido)"

# -- 3. Subir por SCP --
Step "Subiendo binario via SCP"
& scp $BinPath "${SshTarget}:${RemoteNewBin}"
if ($LASTEXITCODE -ne 0) { Die "SCP fallo" }
OK "Subida completa"

# -- 4. Reemplazar y reiniciar --
Step "Reemplazando binario y reiniciando servicio"
$swapCmd = "sudo systemctl stop $Service ; sudo cp $RemoteNewBin $RemoteInstall ; sudo chmod +x $RemoteInstall ; sudo systemctl start $Service ; sleep 3 ; sudo systemctl is-active $Service"
$active = Ssh-Run $swapCmd
if ($active -ne "active") { Die "Servicio no esta active tras el restart (estado: $active)" }
OK "Servicio: $active"

# -- 5. Health loopback (desde el servidor) --
Step "Health check en loopback (127.0.0.1:8080)"
$loopCode = Ssh-Run "curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1:8080/api/health"
if ($loopCode -ne "200") { Die "Health loopback = $loopCode (esperado 200)" }
OK "http://127.0.0.1:8080/api/health -> $loopCode"

# -- 6. Verificacion publica E2E --
Step "Verificacion publica end-to-end"
foreach ($path in @("/", "/api/health")) {
    $url  = "$PublicURL$path"
    $code = Ssh-Run "curl -s -o /dev/null -w '%{http_code}' -m 15 $url"
    if ($code -ne "200") { Die "$url -> $code (esperado 200)" }
    OK "$url -> $code"
}

# -- 7. Verificar bundle JS --
Step "Verificando que el bundle JS esta accesible"
$indexContent = (& curl.exe -s -m 15 "$PublicURL/") | Out-String
$publicEntryHash = Get-EntryHashFromHtml $indexContent
if (-not $publicEntryHash) {
    Die "No se encontro entry-*.js en index.html servido"
}
if ($publicEntryHash -ne $expectedEntryHash) {
    Die "Hash publico desactualizado: esperado=$expectedEntryHash publico=$publicEntryHash"
}
$bundleUrl = "$PublicURL/_expo/static/js/web/entry-$publicEntryHash.js"
$bundleCode = (& curl.exe -s -o NUL -w "%{http_code}" -m 15 "$bundleUrl") | Out-String
$bundleCode = $bundleCode.Trim()
if ($bundleCode -ne "200") { Die "Bundle entry-$publicEntryHash.js -> $bundleCode (esperado 200)" }
OK "Bundle entry-$publicEntryHash.js -> $bundleCode"

# Guardarrail: la entrada web debe cargarse como modulo para permitir import.meta
if ($indexContent -notmatch '<script[^>]*type="module"[^>]*entry-[a-f0-9]+\.js') {
    Die "index.html no sirve el bundle entry-*.js como script type=module"
}
OK "index.html carga entry-*.js con type=module"

# -- 8. Logs recientes --
Step "Ultimos logs del servicio"
Ssh-Run "sudo journalctl -u $Service --no-pager -n 10"

Write-Host ""
Write-Host "Deploy completado y validado E2E." -ForegroundColor Green
Write-Host "URL: $PublicURL" -ForegroundColor Green
