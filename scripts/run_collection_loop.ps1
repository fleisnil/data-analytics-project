param(
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 20,
    [ValidateRange(1, 10000)]
    [int]$Iterations = 6
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$localCli = Join-Path $projectRoot ".venv/Scripts/sptdelays.exe"
if (-not (Test-Path -LiteralPath $localCli -PathType Leaf)) {
    throw "Project environment not found: $localCli. Run uv sync --extra dev first."
}
Push-Location -LiteralPath $projectRoot
try {
    for ($i = 1; $i -le $Iterations; $i++) {
        Write-Host "Collection $i of $Iterations"
        & $localCli collect-live
        if ($LASTEXITCODE -ne 0) {
            throw "Collection $i failed with exit code $LASTEXITCODE. Check sptdelays status and the saved raw response."
        }
        if ($i -lt $Iterations) {
            Start-Sleep -Seconds ($IntervalMinutes * 60)
        }
    }
} finally {
    Pop-Location
}
