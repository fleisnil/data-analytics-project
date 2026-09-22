param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{1,3}$')]
    [string]$GroupNumber
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$artifacts = Join-Path $projectRoot "artifacts"
$normalizedGroup = $GroupNumber.PadLeft(2, "0")
$archive = Join-Path $artifacts "materials_group_$normalizedGroup.zip"
$staging = Join-Path ([System.IO.Path]::GetTempPath()) "sptdelays_submission_$([guid]::NewGuid())"

New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
New-Item -ItemType Directory -Path $staging -Force | Out-Null

$items = @(
    ".env.example", "README.md", "docker-compose.yml", "pyproject.toml", "uv.lock",
    "config", "data", "docs", "notebooks", "presentation", "reports", "scripts", "sql", "src", "tests"
)

try {
    foreach ($item in $items) {
        $source = Join-Path $projectRoot $item
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $staging -Recurse -Force
        }
    }
    Get-ChildItem -LiteralPath $staging -Directory -Recurse -Force |
        Where-Object { $_.Name -in @(".venv", ".uv-cache", "__pycache__", ".pytest_cache", ".ipynb_checkpoints") } |
        Sort-Object FullName -Descending |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    if (Test-Path -LiteralPath $archive) {
        throw "Archive already exists. Review or rename it before building another package: $archive"
    }
    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $archive -CompressionLevel Optimal
    Write-Host "Created $archive"
}
finally {
    $resolvedStaging = [System.IO.Path]::GetFullPath($staging)
    $resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    if ($resolvedStaging.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedStaging)) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}
