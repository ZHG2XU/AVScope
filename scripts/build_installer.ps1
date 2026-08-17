$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script = Join-Path $root "packaging\AVScope.nsi"
$makensis = if ($env:AVSCOPE_MAKENSIS) {
    $env:AVSCOPE_MAKENSIS
} else {
    (Get-Command makensis.exe -ErrorAction SilentlyContinue).Source
}

if (-not $makensis -or -not (Test-Path -LiteralPath $makensis)) {
    throw "makensis.exe not found. Set AVSCOPE_MAKENSIS to the NSIS compiler path."
}

& "$root\scripts\generate_installer_assets.ps1"
if (-not $?) {
    throw "Installer asset generation failed"
}

& $makensis /WX /INPUTCHARSET UTF8 $script
if ($LASTEXITCODE -ne 0) {
    throw "NSIS installer build failed"
}

Write-Output "$root\dist\AVScope-Setup.exe"
