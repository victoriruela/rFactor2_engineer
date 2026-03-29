param(
    [switch]$RemoveTemporaryTestImages,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$mainProject = "rfactor2_engineer"
$temporaryProjectRegex = '^t\d+-'
$serviceLabel = "test"

function Should-CleanProject {
    param([string]$Project)

    if ($Project -eq $mainProject) {
        return $true
    }
    return $Project -match $temporaryProjectRegex
}

function Get-ExitedTestContainerIds {
    $ids = docker ps -aq --filter "label=com.docker.compose.service=$serviceLabel" --filter "status=exited"
    if (-not $ids) {
        return @()
    }

    $selected = @()
    foreach ($id in $ids) {
        $project = docker inspect --format "{{ index .Config.Labels \"com.docker.compose.project\" }}" $id
        if (Should-CleanProject -Project $project) {
            $selected += $id
        }
    }
    return $selected
}

function Remove-ExitedTestContainers {
    $toRemove = Get-ExitedTestContainerIds
    if (-not $toRemove -or $toRemove.Count -eq 0) {
        Write-Output "No exited test containers found for main/temporary projects."
        return
    }

    if ($DryRun) {
        Write-Output "Dry run: would remove exited test containers: $($toRemove -join ', ')"
        return
    }

    docker rm $toRemove | Out-Null
    Write-Output "Removed exited test containers: $($toRemove.Count)"
}

function Remove-TemporaryTestImages {
    $lines = docker image ls --format "{{.Repository}} {{.ID}}"
    if (-not $lines) {
        Write-Output "No Docker images found."
        return
    }

    $imageIds = @()
    foreach ($line in $lines) {
        $parts = $line -split ' ', 2
        if ($parts.Count -lt 2) {
            continue
        }
        $repository = $parts[0]
        $imageId = $parts[1]
        if ($repository -match '^t\d+-.*-test$') {
            $imageIds += $imageId
        }
    }

    if (-not $imageIds -or $imageIds.Count -eq 0) {
        Write-Output "No temporary benchmark test images found."
        return
    }

    $uniqueIds = $imageIds | Select-Object -Unique
    if ($DryRun) {
        Write-Output "Dry run: would remove temporary test images: $($uniqueIds -join ', ')"
        return
    }

    docker image rm $uniqueIds | Out-Null
    Write-Output "Removed temporary benchmark test images: $($uniqueIds.Count)"
}

Remove-ExitedTestContainers

if ($RemoveTemporaryTestImages) {
    Remove-TemporaryTestImages
}
