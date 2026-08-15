[CmdletBinding()]
param(
    [switch]$FrontendOnly,
    [switch]$BackendOnly
)

$ErrorActionPreference = 'Stop'

if ($FrontendOnly -and $BackendOnly) {
    throw 'Choose either -FrontendOnly or -BackendOnly, not both.'
}

$projectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-CheckedCommand {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Command $($Arguments -join ' ')"
    }
}

if (-not $BackendOnly) {
    $frontendPath = Join-Path $projectRoot 'frontend'
    if (-not (Test-Path (Join-Path $frontendPath 'node_modules'))) {
        throw 'Frontend dependencies are missing. Run npm ci in the frontend directory first.'
    }

    Write-Host 'Checking frontend types and production build...'
    Push-Location $frontendPath
    try {
        Invoke-CheckedCommand 'npm.cmd' @('run', 'lint')
        Invoke-CheckedCommand 'npm.cmd' @('run', 'build')
    }
    finally {
        Pop-Location
    }
}

if (-not $FrontendOnly) {
    $backendPath = Join-Path $projectRoot 'Agents_backend'
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $python = if (Test-Path $venvPython) {
        $venvPython
    }
    else {
        (Get-Command python -ErrorAction Stop).Source
    }

    Write-Host 'Running backend tests...'
    Push-Location $backendPath
    try {
        Invoke-CheckedCommand $python @('-m', 'pytest', 'tests')
    }
    finally {
        Pop-Location
    }
}

Write-Host 'Verification completed successfully.'
