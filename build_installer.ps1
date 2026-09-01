$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$version = (Get-Content -Raw -Path "$PSScriptRoot\VERSION.txt").Trim()
if ([string]::IsNullOrWhiteSpace($version)) { throw 'VERSION.txt jest pusty.' }
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "VERSION.txt musi mieć format X.Y.Z. Otrzymano: $version" }

New-Item -ItemType Directory -Force -Path "$PSScriptRoot\installer-output" | Out-Null
"#define MyAppVersion `"$version`"" | Set-Content -Encoding ASCII "$PSScriptRoot\installer\version.iss.inc"

& "$PSScriptRoot\build_exe.bat"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller nie zakończył się powodzeniem.' }

$isccCandidates = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $isccCandidates) {
    throw "Nie znaleziono ISCC.exe. Zainstaluj Inno Setup 6 i uruchom skrypt ponownie."
}

$iscc = $isccCandidates[0]
Write-Host "Using Inno Setup: $iscc"
& $iscc "$PSScriptRoot\installer\MizuLauncher.iss"
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup nie zakończył się powodzeniem.' }

Write-Host ""
Write-Host "GOTOWE"
Write-Host "Instalator: $PSScriptRoot\installer-output\MizuLauncher-Setup-$version.exe"
