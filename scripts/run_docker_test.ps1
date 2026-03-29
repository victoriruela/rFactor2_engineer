param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs,

    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"

if (-not $CommandArgs -or $CommandArgs.Count -eq 0) {
    $CommandArgs = @("pytest", "tests/", "--ignore=tests/integration", "-v")
}

$composeProject = "rfactor2_engineer"
$temporaryProjectRegex = '^t\d+-'
$composeService = "test"
$exitCode = 1

function Remove-TestArtifacts {
    param(
        [string]$Project,
        [string]$Service,
        [string]$TemporaryProjectRegex
    )

    $ids = docker ps -aq --filter "label=com.docker.compose.service=$Service" --filter "status=exited"
    if (-not $ids) {
        return
    }

    $toRemove = @()
    foreach ($id in $ids) {
        $containerProject = docker inspect --format "{{ index .Config.Labels \"com.docker.compose.project\" }}" $id
        if ($containerProject -eq $Project -or $containerProject -match $TemporaryProjectRegex) {
            $toRemove += $id
        }
    }

    if ($toRemove) {
        docker rm $toRemove | Out-Null
    }
}

try {
    docker compose --profile test run --rm test @CommandArgs
    $exitCode = $LASTEXITCODE
}
finally {
    if (-not $KeepArtifacts) {
        Remove-TestArtifacts -Project $composeProject -Service $composeService -TemporaryProjectRegex $temporaryProjectRegex
    }
}

exit $exitCode
