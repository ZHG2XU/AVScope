$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dist = Join-Path $root "dist"
$sourceZip = Join-Path $dist "AVScope-portable-source.zip"
$appZip = Join-Path $dist "AVScope-portable-win-x64.zip"

New-Item -ItemType Directory -Force -Path $dist | Out-Null
if (Test-Path $sourceZip) {
    Remove-Item -Path $sourceZip -Force
}
if (Test-Path $appZip) {
    Remove-Item -Path $appZip -Force
}

$items = @(
    (Join-Path $root "avscope"),
    (Join-Path $root "qt"),
    (Join-Path $root "packaging"),
    (Join-Path $root "plugins"),
    (Join-Path $root "samples"),
    (Join-Path $root "scripts"),
    (Join-Path $root "tests"),
    (Join-Path $root "data"),
    (Join-Path $root "docs"),
    (Join-Path $root "INSTALLATIONS.md"),
    (Join-Path $root "README.md"),
    (Join-Path $root "CHANGELOG.md"),
    (Join-Path $root "THIRD_PARTY_NOTICES.md"),
    (Join-Path $root "avscope_engine.py"),
    (Join-Path $root "run_avscope.py")
)

Compress-Archive -Path $items -DestinationPath $sourceZip -CompressionLevel Optimal
Compress-Archive -Path (Join-Path $dist "AVScopeQt") -DestinationPath $appZip -CompressionLevel Optimal
PowerShell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "make_sample_reports.ps1")
PowerShell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "make_release_manifest.ps1")
Write-Host $sourceZip
Write-Host $appZip
