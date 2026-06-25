#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Submit vcpkg dependency graph for FFmpeg MSVC prebuilt.
.DESCRIPTION
    Runs ``vcpkg install --dry-run`` for every triplet so vcpkg
    auto-submits the dependency tree to GitHub's Dependency Graph API.
    Unlike ``dl_seed.ps1``, this script does NOT download any sources.
    #>
$ErrorActionPreference = "Stop"

$vcpkgRoot = $env:VCPKG_ROOT
if (-not $vcpkgRoot) {
    throw "VCPKG_ROOT environment variable is not set."
}
$vcpkgExe = Join-Path $vcpkgRoot "vcpkg.exe"
if (-not (Test-Path $vcpkgExe)) {
    throw "vcpkg.exe not found at: $vcpkgExe"
}

$tripletsStr = $env:TRIPLETS
if (-not $tripletsStr) {
    throw "TRIPLETS environment variable is not set."
}
$triplets = $tripletsStr.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)

$installOptionsStr = $env:VCPKG_INSTALL_OPTIONS
$installOptions = if ($installOptionsStr) {
    $installOptionsStr.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
} else {
    @()
}

# Read features from vcpkg.json
$scriptDir = $PSScriptRoot
$repoRoot  = Resolve-Path "$scriptDir\..\.."
$vcpkgJson = Join-Path $repoRoot "ports\ffmpeg-deps\vcpkg.json"
$json = Get-Content $vcpkgJson -Raw | ConvertFrom-Json

$features = if ($json.features) {
    $json.features.PSObject.Properties.Name
} else {
    Write-Host "No features found in ffmpeg-deps — nothing to submit"
    exit 0
}

foreach ($triplet in $triplets) {
    $featureArgs = $features | ForEach-Object { "--x-feature=$_" }
    Write-Output "Submitting dependency graph for $triplet..."

    & $vcpkgExe install @featureArgs `
        --triplet=$triplet `
        --dry-run `
        @installOptions

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to submit dependency graph for $triplet"
    }
}

Write-Output "All dependency graphs submitted successfully."
