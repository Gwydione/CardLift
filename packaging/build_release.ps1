<#
.SYNOPSIS
    Builds a CardLift RC1 release: PyInstaller bundle, bundled docs,
    internal + external SHA256 checksums, and a versioned ZIP, in one
    repeatable step.

.DESCRIPTION
    1. Regenerates packaging/version_info.txt from deckforge.__version__
       so the .exe's Windows file-properties metadata never drifts from
       the version string the GUI itself displays.
    2. Runs PyInstaller against deckforge_gui.spec for a clean one-folder
       build (dist/CardLift/).
    3. Copies release docs (QUICK_START.md, ALPHA_TESTING_GUIDE.md,
       docs/PRIVACY_PROMISES.md as PRIVACY.md, LICENSE,
       LICENSE_EXPLAINED.md, THIRD_PARTY_NOTICES.md) into dist/CardLift/
       alongside the .exe and _internal/.
    4. Writes dist/CardLift/SHA256SUMS.txt covering CardLift.exe and
       the copied docs (not _internal/, which is PyInstaller's own
       runtime payload and not independently verifiable content).
    5. Zips dist/CardLift/ into a versioned archive
       (dist/CardLift-<version>-windows-x64.zip).
    6. Writes a sibling .sha256 checksum file for that archive so testers
       can verify the download before running it -- there is no code
       signing yet, so this is the only integrity check available.

.NOTES
    Run from the repository root, or anywhere -- paths are resolved
    relative to this script's location. Requires the project virtualenv
    (.venv) to already have pyinstaller installed.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$PyInstaller = Join-Path $RepoRoot '.venv\Scripts\pyinstaller.exe'
$SpecFile = Join-Path $RepoRoot 'deckforge_gui.spec'
$DistDir = Join-Path $RepoRoot 'dist'
$BundleDir = Join-Path $DistDir 'CardLift'

foreach ($tool in @($Python, $PyInstaller)) {
    if (-not (Test-Path $tool)) {
        throw "Required tool not found: $tool (has the project venv been created?)"
    }
}

Write-Host "== Step 1/6: Generating executable version metadata ==" -ForegroundColor Cyan
& $Python (Join-Path $PSScriptRoot 'generate_version_info.py')
if ($LASTEXITCODE -ne 0) { throw 'generate_version_info.py failed' }

$Version = (& $Python -c "import sys; sys.path.insert(0, 'src'); from deckforge import __version__; print(__version__)").Trim()
if (-not $Version) { throw 'Could not determine deckforge.__version__' }
Write-Host "Version: $Version"

Write-Host "`n== Step 2/6: Running PyInstaller ==" -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & $PyInstaller --noconfirm --clean $SpecFile
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
}
finally {
    Pop-Location
}

$ExePath = Join-Path $BundleDir 'CardLift.exe'
if (-not (Test-Path $ExePath)) {
    throw "Expected build output not found: $ExePath"
}

Write-Host "`n== Step 3/6: Copying release docs ==" -ForegroundColor Cyan
$DocsToCopy = @(
    @{ Source = Join-Path $RepoRoot 'QUICK_START.md'; DestName = 'QUICK_START.md' },
    @{ Source = Join-Path $RepoRoot 'ALPHA_TESTING_GUIDE.md'; DestName = 'ALPHA_TESTING_GUIDE.md' },
    @{ Source = Join-Path $RepoRoot 'docs\PRIVACY_PROMISES.md'; DestName = 'PRIVACY.md' },
    @{ Source = Join-Path $RepoRoot 'LICENSE'; DestName = 'LICENSE' },
    @{ Source = Join-Path $RepoRoot 'LICENSE_EXPLAINED.md'; DestName = 'LICENSE_EXPLAINED.md' },
    @{ Source = Join-Path $RepoRoot 'THIRD_PARTY_NOTICES.md'; DestName = 'THIRD_PARTY_NOTICES.md' }
)
foreach ($doc in $DocsToCopy) {
    if (-not (Test-Path $doc.Source)) {
        throw "Required release doc not found: $($doc.Source)"
    }
    Copy-Item -Path $doc.Source -Destination (Join-Path $BundleDir $doc.DestName) -Force
    Write-Host "Copied $($doc.DestName)"
}

Write-Host "`n== Step 4/6: Generating internal SHA256SUMS.txt ==" -ForegroundColor Cyan
$SumsPath = Join-Path $BundleDir 'SHA256SUMS.txt'
$SumsFiles = @('CardLift.exe') + ($DocsToCopy | ForEach-Object { $_.DestName })
$SumsLines = foreach ($name in $SumsFiles) {
    $hash = (Get-FileHash -Path (Join-Path $BundleDir $name) -Algorithm SHA256).Hash.ToLower()
    "$hash  $name"
}
[System.IO.File]::WriteAllText($SumsPath, (($SumsLines -join "`n") + "`n"), [System.Text.Encoding]::ASCII)
Write-Host "Wrote $SumsPath"

Write-Host "`n== Step 5/6: Assembling release ZIP ==" -ForegroundColor Cyan
$ZipName = "CardLift-$Version-windows-x64.zip"
$ZipPath = Join-Path $DistDir $ZipName
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path $BundleDir -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Wrote $ZipPath"

Write-Host "`n== Step 6/6: Generating external checksum ==" -ForegroundColor Cyan
$Hash = Get-FileHash -Path $ZipPath -Algorithm SHA256
$ChecksumPath = "$ZipPath.sha256"
$ChecksumLine = "$($Hash.Hash.ToLower())  $ZipName"
[System.IO.File]::WriteAllText($ChecksumPath, "$ChecksumLine`n", [System.Text.Encoding]::ASCII)
Write-Host "Wrote $ChecksumPath"

Write-Host "`nDone." -ForegroundColor Green
Write-Host "  Bundle:   $BundleDir"
Write-Host "  Archive:  $ZipPath"
Write-Host "  Checksum: $ChecksumPath ($($Hash.Hash.ToLower()))"
