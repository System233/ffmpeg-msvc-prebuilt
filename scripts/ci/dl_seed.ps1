#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Download vcpkg seed dependencies for FFmpeg MSVC prebuilt builds.

.DESCRIPTION
    Reads the ffmpeg-deps feature list from ``ports/ffmpeg-deps/vcpkg.json``
    and runs ``vcpkg install`` with ``--only-downloads`` for every triplet in
    the ``TRIPLETS`` environment variable.

    Environment variables expected:

        VCPKG_ROOT           Path to the vcpkg installation directory.
        TRIPLETS             Space-separated list of vcpkg triplets.
        VCPKG_INSTALL_OPTIONS Additional options passed to ``vcpkg install``
                             (space-separated).

    Extracted from ``.github/workflows/build-release.yml`` (ll. 257-272).

.EXAMPLE
    $env:VCPKG_ROOT = "C:\vcpkg"
    $env:TRIPLETS = "x64-windows x64-windows-static"
    $env:VCPKG_INSTALL_OPTIONS = "--clean-after-build"
    .\scripts\ci\dl_seed.ps1
#>

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Path resolution — everything is relative to this script's directory.
# ---------------------------------------------------------------------------
$scriptDir = $PSScriptRoot                              # e.g. scripts/ci
$repoRoot  = Resolve-Path "$scriptDir\..\.."            # repo root
$vcpkgJson = Join-Path $repoRoot "ports\ffmpeg-deps\vcpkg.json"

# ---------------------------------------------------------------------------
# Read environment variables
# ---------------------------------------------------------------------------
$tripletsStr = $env:TRIPLETS
if (-not $tripletsStr) {
    throw "TRIPLETS environment variable is not set."
}
$triplets = $tripletsStr.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)

$vcpkgRoot = $env:VCPKG_ROOT
if (-not $vcpkgRoot) {
    throw "VCPKG_ROOT environment variable is not set."
}
$vcpkgExe = Join-Path $vcpkgRoot "vcpkg.exe"
if (-not (Test-Path $vcpkgExe)) {
    throw "vcpkg.exe not found at: $vcpkgExe"
}

$installOptionsStr = $env:VCPKG_INSTALL_OPTIONS
$installOptions = if ($installOptionsStr) {
    $installOptionsStr.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
} else {
    @()
}

# ---------------------------------------------------------------------------
# Extract features from vcpkg.json
# ---------------------------------------------------------------------------
$json = Get-Content $vcpkgJson -Raw | ConvertFrom-Json
if (-not $json.features) {
    Write-Host "No features found in ffmpeg-deps — nothing to submit"
    exit 0
}
$features = $json.features.PSObject.Properties.Name

$allFeatures = $features -join ','

# ---------------------------------------------------------------------------
# Download for each triplet
# ---------------------------------------------------------------------------
foreach ($triplet in $triplets) {
    Write-Output "Downloading ffmpeg-deps[$allFeatures] for $triplet ..."

    $vcpkgArgs = @(
        "install",
        "ffmpeg-deps[$allFeatures]",
        "--triplet=$triplet",
        "--recurse",
        "--only-downloads"
    ) + $installOptions

    & $vcpkgExe @vcpkgArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download ffmpeg-deps[$allFeatures] for $triplet"
    }
}

Write-Output "All seed downloads completed successfully."
