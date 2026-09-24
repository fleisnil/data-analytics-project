param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{1,3}$')]
    [string]$GroupNumber,
    [switch]$ValidateOnly,
    [ValidateRange(1, 10000)]
    [int]$MaxOptionalRawFileMB = 100
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$artifacts = Join-Path $projectRoot "artifacts"
$normalizedGroup = $GroupNumber.PadLeft(2, "0")
$archive = Join-Path $artifacts "materials_group_$normalizedGroup.zip"

# Explicit source allowlist: never package the project recursively.
$items = @(
    ".env.example", ".gitignore", "README.md", "docker-compose.yml", "pyproject.toml", "uv.lock",
    ".github", ".vscode", "config", "data", "database", "docs", "notebooks",
    "presentation", "reports", "scripts", "sql", "src", "tests"
)
$required = @(
    "README.md", "pyproject.toml", "uv.lock", "config/study.json", "src/sptdelays/cli.py",
    "data/processed/model_data.csv", "sql/sqlite_analysis.sql", "database/sptdelays.sqlite"
)
foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relative) -PathType Leaf)) {
        throw "Required submission file is missing: $relative. Run the pipeline first."
    }
}
if (-not (Get-ChildItem -LiteralPath (Join-Path $projectRoot "notebooks") -Filter "*.ipynb" -File)) {
    throw "At least one Jupyter notebook is required."
}

$files = [System.Collections.Generic.List[object]]::new()
$excluded = [System.Collections.Generic.List[object]]::new()
foreach ($item in $items) {
    $source = Join-Path $projectRoot $item
    if (-not (Test-Path -LiteralPath $source)) { continue }
    $candidates = if (Test-Path -LiteralPath $source -PathType Container) {
        Get-ChildItem -LiteralPath $source -File -Recurse -Force
    } else {
        Get-Item -LiteralPath $source -Force
    }
    foreach ($file in $candidates) {
        $relative = $file.FullName.Substring($projectRoot.Length + 1).Replace('\', '/')
        $reason = $null
        if ($relative -match '(^|/)(\.git|\.venv|\.uv-cache|\.pytest_cache|\.ruff_cache|__pycache__|\.ipynb_checkpoints|\.codex[^/]*|[^/]*\.egg-info)(/|$)') {
            $reason = "Development cache or environment"
        } elseif (($file.Name -like ".env*" -and $file.Name -ne ".env.example") -or
                  $file.Extension -in @(".pem", ".key", ".pfx", ".p12", ".pyc", ".pyo") -or
                  $file.Name -match '(?i)(^credentials.*\.json$|^id_(rsa|ed25519)$|\.sqlite-(wal|shm|journal)$|\.duckdb\.wal$)') {
            $reason = "Secret, credential file or transient database file"
        } elseif ($relative -like "data/raw/*" -and
                  $file.Length -gt ($MaxOptionalRawFileMB * 1MB) -and
                  $file.Name -notlike "*_selected_stations.csv") {
            $reason = "Large optional raw original; retain the original locally and source provenance in docs"
        } elseif ($file.Extension -in @(".mp4", ".zip")) {
            $reason = "Video and archive files are separate Moodle submissions"
        }
        if ($reason) {
            $excluded.Add([pscustomobject]@{ path = $relative; reason = $reason; bytes = $file.Length })
        } else {
            $files.Add([pscustomobject]@{ source = $file.FullName; path = $relative; bytes = $file.Length })
        }
    }
}
$totalBytes = ($files | Measure-Object -Property bytes -Sum).Sum
Write-Host ("Validated {0} files ({1:N1} MiB), excluded {2} files." -f $files.Count, ($totalBytes / 1MB), $excluded.Count)
Write-Host "Includes source, locked dependencies, notebooks, collected/processed data, SQLite and available reports."
Write-Host "This checks package contents, not lecturer approval, data sufficiency or final presentation quality."
if ($ValidateOnly) {
    $excluded | Select-Object path, reason | Format-Table -AutoSize
    Write-Host "Validation only: no archive or staging files were created."
    return
}
if (Test-Path -LiteralPath $archive) {
    throw "Archive already exists. Review or rename it before building another package: $archive"
}

$staging = Join-Path ([System.IO.Path]::GetTempPath()) "sptdelays_submission_$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
New-Item -ItemType Directory -Path $staging -Force | Out-Null
$manifestFiles = [System.Collections.Generic.List[object]]::new()
try {
    foreach ($file in $files) {
        $destination = Join-Path $staging $file.path
        $parent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $file.source -Destination $destination
        $manifestFiles.Add([pscustomobject]@{
            path = $file.path
            bytes = (Get-Item -LiteralPath $destination).Length
            sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        })
    }
    $manifest = [ordered]@{
        group_number = $normalizedGroup
        created_utc = [DateTime]::UtcNow.ToString("o")
        file_count = $files.Count
        files = @($manifestFiles.ToArray())
        excluded = @($excluded.ToArray())
        note = "File hashes identify the submitted version. Review docs/checklists and supply video and presentation PDF separately."
    }
    $manifest | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath (Join-Path $staging "submission_manifest.json") -Encoding UTF8
    # ZipFile includes dotfiles such as .env.example, which Compress-Archive can omit.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $staging, $archive, [System.IO.Compression.CompressionLevel]::Optimal, $false
    )
    Write-Host "Created $archive"
    Write-Host "The archive contains submission_manifest.json with SHA-256 hashes and exclusions."
}
finally {
    $resolvedStaging = [System.IO.Path]::GetFullPath($staging)
    $resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\', '/')
    $tempPrefix = $resolvedTemp + [System.IO.Path]::DirectorySeparatorChar
    if ($resolvedStaging.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedStaging) -like "sptdelays_submission_*" -and
        (Test-Path -LiteralPath $resolvedStaging)) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}
