$ErrorActionPreference = "Stop"
$root = "G:\AVScope"
$dist = "G:\AVScope\dist"
$sourceZip = "G:\AVScope\dist\AVScope-portable-source.zip"
$appZip = "G:\AVScope\dist\AVScope-portable-win-x64.zip"

New-Item -ItemType Directory -Force -Path $dist | Out-Null
if (Test-Path $sourceZip) {
    Remove-Item -Path $sourceZip -Force
}
if (Test-Path $appZip) {
    Remove-Item -Path $appZip -Force
}

$items = @(
    "G:\AVScope\avscope",
    "G:\AVScope\packaging",
    "G:\AVScope\plugins",
    "G:\AVScope\samples",
    "G:\AVScope\scripts",
    "G:\AVScope\tests",
    "G:\AVScope\data",
    "G:\AVScope\docs",
    "G:\AVScope\INSTALLATIONS.md",
    "G:\AVScope\README.md",
    "G:\AVScope\run_avscope.py"
)

Compress-Archive -Path $items -DestinationPath $sourceZip -CompressionLevel Optimal
Compress-Archive -Path "G:\AVScope\dist\AVScope" -DestinationPath $appZip -CompressionLevel Optimal
Write-Host $sourceZip
Write-Host $appZip
