param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseTag,
    [string]$RemoteHost = "34.175.126.128",
    [string]$User = "bitor",
    [string]$RemoteDir = "/home/bitor/apps/rFactor2_engineer",
    [string]$Repo = "victoriruela/rFactor2_engineer",
    [switch]$UseGithubReleaseArtifact,
    [switch]$SkipDockerBuild
)

$ErrorActionPreference = "Stop"

$remote = "$User@$RemoteHost"
$distDir = Join-Path $PWD "dist"
$artifactName = "rfactor2_engineer-$ReleaseTag.tar.gz"
$localArtifactPath = Join-Path $distDir $artifactName
$remoteTar = "/home/$User/rfactor2_engineer_deploy.tar.gz"

function Assert-LastExit {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($Step). Exit code: $LASTEXITCODE"
    }
}

function Assert-CleanWorkingTree {
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read git status."
    }
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Dirty working tree detected. Aborting deploy by policy. Commit or stash changes first."
    }
}

function Get-GitHubToken {
    if ($env:GH_TOKEN) {
        return $env:GH_TOKEN
    }
    if ($env:GITHUB_TOKEN) {
        return $env:GITHUB_TOKEN
    }

    $credentialQuery = "protocol=https`nhost=github.com`n`n"
    $credentialResult = $credentialQuery | git credential fill
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($credentialResult)) {
        return $null
    }

    foreach ($line in ($credentialResult -split "`n")) {
        if ($line.StartsWith("password=")) {
            return $line.Substring("password=".Length)
        }
    }
    return $null
}

function Download-GitHubReleaseArtifact {
    param(
        [string]$Repository,
        [string]$Tag,
        [string]$ExpectedAssetName,
        [string]$OutFile
    )

    $token = Get-GitHubToken
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "No GitHub token available to download release artifact."
    }

    $headers = @{
        "Authorization" = "Bearer $token"
        "Accept" = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }

    $release = Invoke-RestMethod -Method Get -Headers $headers -Uri "https://api.github.com/repos/$Repository/releases/tags/$Tag"
    $asset = $release.assets | Where-Object { $_.name -eq $ExpectedAssetName } | Select-Object -First 1
    if (-not $asset) {
        throw "Asset '$ExpectedAssetName' not found in release '$Tag'."
    }

    $downloadHeaders = @{
        "Authorization" = "Bearer $token"
        "Accept" = "application/octet-stream"
        "X-GitHub-Api-Version" = "2022-11-28"
    }

    Invoke-WebRequest -Method Get -Headers $downloadHeaders -Uri "https://api.github.com/repos/$Repository/releases/assets/$($asset.id)" -OutFile $OutFile
}

function Wait-RemoteHttp200 {
    param(
        [string]$Label,
        [string]$Url,
        [string]$Auth = "",
        [int]$MaxAttempts = 60,
        [int]$SleepSeconds = 2
    )

    for ($i = 1; $i -le $MaxAttempts; $i++) {
        if ([string]::IsNullOrWhiteSpace($Auth)) {
            $code = ssh $script:remote "curl -sS -o /dev/null -w '%{http_code}' $Url 2>/dev/null"
        }
        else {
            $code = ssh $script:remote "curl -sS -u '$Auth' -o /dev/null -w '%{http_code}' $Url 2>/dev/null"
        }
        if ($LASTEXITCODE -eq 0 -and $code.Trim() -eq "200") {
            Write-Output "$Label:200"
            return
        }
        Start-Sleep -Seconds $SleepSeconds
    }

    throw "$Label health check timed out for $Url"
}

Assert-CleanWorkingTree

New-Item -ItemType Directory -Path $distDir -Force | Out-Null

if ($UseGithubReleaseArtifact) {
    Write-Output "==> Downloading deploy artifact from GitHub Release $ReleaseTag"
    Download-GitHubReleaseArtifact -Repository $Repo -Tag $ReleaseTag -ExpectedAssetName $artifactName -OutFile $localArtifactPath
}
else {
    Write-Output "==> Creating deploy artifact from git tag $ReleaseTag"
    git archive --format=tar.gz --output $localArtifactPath $ReleaseTag
    Assert-LastExit -Step "git archive tag"
}

Write-Output "==> Uploading deploy artifact to $remote"
scp $localArtifactPath "$remote`:$remoteTar"
Assert-LastExit -Step "scp artifact"

Write-Output "==> Extracting artifact on remote host (preserving data/ directory)"
# Strategy: clean app-code files (bitor-owned) with plain rm; use sudo ONLY as a
# fallback for any Docker-owned files that may exist outside data/.
# data/ is intentionally preserved so in-flight user session uploads survive redeploys.
ssh $remote "mkdir -p '$RemoteDir'; find '$RemoteDir' -mindepth 1 -maxdepth 1 -not -name data | xargs -r rm -rf 2>/dev/null || true; sudo -n find '$RemoteDir' -mindepth 1 -maxdepth 1 -not -name data -exec rm -rf '{}' + 2>/dev/null || true; tar -xzf '$remoteTar' -C '$RemoteDir'"
Assert-LastExit -Step "remote extract"

Write-Output "==> Uploading deployment config files"
ssh $remote "mkdir -p '$RemoteDir/deploy'"
Assert-LastExit -Step "remote deploy dir"
scp deploy/docker-compose.gcp.yml "$remote`:$RemoteDir/deploy/docker-compose.gcp.yml"
Assert-LastExit -Step "scp docker-compose.gcp.yml"
scp deploy/nginx-rfactor2_engineer.conf "$remote`:$RemoteDir/deploy/nginx-rfactor2_engineer.conf"
Assert-LastExit -Step "scp nginx config"
scp deploy/.htpasswd "$remote`:$RemoteDir/deploy/.htpasswd"
Assert-LastExit -Step "scp htpasswd"

Write-Output "==> Cleaning legacy compose stacks (if any)"
ssh $remote "bash -lc 'cd $RemoteDir; sudo -n docker compose -f docker-compose.yml -f deploy/docker-compose.gcp.yml down || true; sudo -n docker compose -p deploy -f deploy/docker-compose.gcp.yml down || true'"
Assert-LastExit -Step "legacy compose cleanup"

$composeArgs = "up -d"
if (-not $SkipDockerBuild) {
    $composeArgs += " --build"
}

Write-Output "==> Starting Docker services on remote host"
ssh $remote "cd '$RemoteDir' && sudo -n docker compose -p rfactor2_engineer -f deploy/docker-compose.gcp.yml $composeArgs"
Assert-LastExit -Step "compose up"

Write-Output "==> Installing/refreshing Nginx reverse proxy config"
ssh $remote "sudo -n cp '$RemoteDir/deploy/nginx-rfactor2_engineer.conf' /etc/nginx/sites-available/rfactor2_engineer; sudo -n cp '$RemoteDir/deploy/.htpasswd' /etc/nginx/.htpasswd_rfactor2_engineer; sudo -n chmod 640 /etc/nginx/.htpasswd_rfactor2_engineer; sudo -n chown root:www-data /etc/nginx/.htpasswd_rfactor2_engineer; sudo -n ln -sf /etc/nginx/sites-available/rfactor2_engineer /etc/nginx/sites-enabled/rfactor2_engineer; sudo -n /usr/sbin/nginx -t; sudo -n systemctl reload nginx"
Assert-LastExit -Step "nginx setup"

Write-Output "==> Health checks"
Wait-RemoteHttp200 -Label "frontend_local" -Url "http://127.0.0.1:18501/"
Wait-RemoteHttp200 -Label "backend_local" -Url "http://127.0.0.1:18000/models"
Wait-RemoteHttp200 -Label "nginx_public" -Url "https://telemetria.bot.nu/" -Auth "racef1:100fuchupabien"
Wait-RemoteHttp200 -Label "nginx_api" -Url "https://telemetria.bot.nu/api/models" -Auth "racef1:100fuchupabien"
Wait-RemoteHttp200 -Label "nginx_public_car_setup" -Url "https://car-setup.com/" -Auth "racef1:100fuchupabien"
Wait-RemoteHttp200 -Label "nginx_api_car_setup" -Url "https://car-setup.com/api/models" -Auth "racef1:100fuchupabien"

Write-Output "Deployment completed successfully for $ReleaseTag."
