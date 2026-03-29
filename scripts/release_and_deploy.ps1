param(
    [ValidateSet("patch", "minor", "major")]
    [string]$VersionBump = "patch",
    [string[]]$SourceBranches = @(),
    [string]$Repo = "victoriruela/rFactor2_engineer",
    [string]$RemoteHost = "34.175.126.128",
    [string]$User = "bitor",
    [string]$RemoteDir = "/home/bitor/apps/rFactor2_engineer",
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"

function Assert-LastExit {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($Step). Exit code: $LASTEXITCODE"
    }
}

function Assert-CleanWorkingTree {
    $status = git status --porcelain
    Assert-LastExit -Step "git status"
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Dirty working tree detected. Aborting release flow by policy."
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

function Split-Version {
    param([string]$Version)
    $parts = $Version.Split('.')
    return [int[]]@([int]$parts[0], [int]$parts[1], [int]$parts[2])
}

function Get-LatestStableTag {
    # Filter out RC/pre-release tags; only consider clean vX.Y.Z tags
    $latest = git tag --list "v[0-9]*.[0-9]*.[0-9]*" --sort=-version:refname |
              Where-Object { $_ -notmatch '-' } |
              Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($latest)) {
        return "v0.0.0"
    }
    return $latest.Trim()
}

function Get-NextVersion {
    param(
        [string]$CurrentTag,
        [string]$BumpType
    )

    $current = $CurrentTag.TrimStart('v')
    $parts = Split-Version -Version $current
    $major = $parts[0]
    $minor = $parts[1]
    $patch = $parts[2]

    switch ($BumpType) {
        "major" { $major += 1; $minor = 0; $patch = 0 }
        "minor" { $minor += 1; $patch = 0 }
        default { $patch += 1 }
    }

    return "v$major.$minor.$patch"
}

function Get-NextRcTag {
    param([string]$ReleaseTag)

    $pattern = "^$([regex]::Escape($ReleaseTag))-rc\.(\d+)$"
    $rcTags = git tag | Where-Object { $_ -match $pattern }
    if (-not $rcTags) {
        return "$ReleaseTag-rc.1"
    }

    $max = 0
    foreach ($t in $rcTags) {
        $n = [int]([regex]::Match($t, $pattern).Groups[1].Value)
        if ($n -gt $max) {
            $max = $n
        }
    }
    return "$ReleaseTag-rc.$($max + 1)"
}

function Invoke-GithubApi {
    param(
        [string]$Method,
        [string]$Uri,
        [string]$Token,
        [object]$Body = $null
    )

    $headers = @{
        "Authorization" = "Bearer $Token"
        "Accept" = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }

    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
    }

    $jsonBody = $Body | ConvertTo-Json -Depth 8 -Compress
    return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -Body $jsonBody -ContentType "application/json"
}

function Publish-ReleaseWithAsset {
    param(
        [string]$Repository,
        [string]$Tag,
        [string]$Token,
        [string]$AssetPath,
        [string]$Name,
        [string]$BodyText
    )

    $release = $null
    try {
        $release = Invoke-GithubApi -Method "GET" -Uri "https://api.github.com/repos/$Repository/releases/tags/$Tag" -Token $Token
    }
    catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 404) {
            throw
        }
    }

    if (-not $release) {
        $payload = @{
            tag_name = $Tag
            name = $Tag
            target_commitish = "main"
            body = $BodyText
            draft = $false
            prerelease = $false
            generate_release_notes = $true
        }
        $release = Invoke-GithubApi -Method "POST" -Uri "https://api.github.com/repos/$Repository/releases" -Token $Token -Body $payload
    }

    $assetName = [System.IO.Path]::GetFileName($AssetPath)
    $existing = $release.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
    if ($existing) {
        Invoke-GithubApi -Method "DELETE" -Uri "https://api.github.com/repos/$Repository/releases/assets/$($existing.id)" -Token $Token | Out-Null
    }

    $uploadHeaders = @{
        "Authorization" = "Bearer $Token"
        "Accept" = "application/vnd.github+json"
        "Content-Type" = "application/gzip"
    }

    $uploadUri = "https://uploads.github.com/repos/$Repository/releases/$($release.id)/assets?name=$assetName"
    Invoke-RestMethod -Method "POST" -Uri $uploadUri -Headers $uploadHeaders -InFile $AssetPath
}

Assert-CleanWorkingTree

Write-Output "==> Fetching origin"
git fetch origin --tags
Assert-LastExit -Step "git fetch"

$latestStableTag = Get-LatestStableTag
$releaseTag = Get-NextVersion -CurrentTag $latestStableTag -BumpType $VersionBump
$rcTag = Get-NextRcTag -ReleaseTag $releaseTag

$existingReleaseTag = git tag --list $releaseTag
if (-not [string]::IsNullOrWhiteSpace($existingReleaseTag)) {
    throw "Release tag '$releaseTag' already exists. Bump version or remove the conflicting tag."
}

$currentBranch = git branch --show-current
Assert-LastExit -Step "git branch --show-current"
if ($SourceBranches.Count -eq 0 -and $currentBranch -ne "main" -and $currentBranch -ne "develop") {
    $SourceBranches = @($currentBranch)
}

Write-Output "==> Updating develop"
git checkout develop
Assert-LastExit -Step "git checkout develop"
git pull --ff-only origin develop
Assert-LastExit -Step "git pull develop"

foreach ($branch in $SourceBranches) {
    Write-Output "==> Merging source branch $branch into develop"
    git merge --no-ff $branch -m "chore(release): integrate $branch into develop"
    Assert-LastExit -Step "merge $branch into develop"
}

Write-Output "==> Running canonical docker tests on develop"
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/run_docker_test.ps1
Assert-LastExit -Step "docker tests on develop"

Write-Output "==> Creating RC tag $rcTag"
git tag $rcTag
Assert-LastExit -Step "git tag rc"
git push origin develop
Assert-LastExit -Step "push develop"
git push origin $rcTag
Assert-LastExit -Step "push rc tag"

Write-Output "==> Updating main"
git checkout main
Assert-LastExit -Step "git checkout main"
git pull --ff-only origin main
Assert-LastExit -Step "git pull main"

Write-Output "==> Merging develop into main"
git merge --no-ff develop -m "release: merge develop into main for $releaseTag"
Assert-LastExit -Step "merge develop into main"

Write-Output "==> Running canonical docker tests on main"
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/run_docker_test.ps1
Assert-LastExit -Step "docker tests on main"

Write-Output "==> Creating release tag $releaseTag"
git tag $releaseTag
Assert-LastExit -Step "git tag release"
git push origin main
Assert-LastExit -Step "push main"
git push origin $releaseTag
Assert-LastExit -Step "push release tag"

$distDir = Join-Path $PWD "dist"
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
$artifactPath = Join-Path $distDir "rfactor2_engineer-$releaseTag.tar.gz"

Write-Output "==> Creating immutable artifact $artifactPath"
git archive --format=tar.gz --output $artifactPath $releaseTag
Assert-LastExit -Step "git archive release artifact"

$token = Get-GitHubToken
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "GitHub token not available. Cannot publish release artifact."
}

Write-Output "==> Publishing GitHub release artifact"
Publish-ReleaseWithAsset -Repository $Repo -Tag $releaseTag -Token $token -AssetPath $artifactPath -Name $releaseTag -BodyText "Automated release for $releaseTag"

if (-not $SkipDeploy) {
    Write-Output "==> Deploying from GitHub release artifact"
    powershell -ExecutionPolicy Bypass -NoProfile -File scripts/deploy_gcp.ps1 -ReleaseTag $releaseTag -Repo $Repo -UseGithubReleaseArtifact
    Assert-LastExit -Step "deploy from release artifact"
}

Write-Output "Release flow completed: RC=$rcTag, Release=$releaseTag"
