param(
    [int]$IntervalMinutes = 20,
    [int]$Iterations = 6
)

$ErrorActionPreference = "Stop"
for ($i = 1; $i -le $Iterations; $i++) {
    Write-Host "Collection $i of $Iterations"
    uv run sptdelays collect-live
    if ($i -lt $Iterations) {
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
}

