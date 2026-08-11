$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$python = "E:\DevelopmentEnvironment\python\python.exe"
$setup = "G:\AVScope\dist\AVScope-Setup.exe"
$appExe = "G:\AVScope\dist\AVScope\AVScope.exe"
$ffprobe = "G:\AVScope\dist\AVScope\_internal\ffprobe.exe"
$portableZip = "G:\AVScope\dist\AVScope-portable-win-x64.zip"
$sourceZip = "G:\AVScope\dist\AVScope-portable-source.zip"
$installDir = "G:\AVScopeInstalled\ValidationSmoke-$([DateTime]::Now.ToString('yyyyMMddHHmmss'))"

$env:PYTHONPATH = $root
$env:TEMP = "G:\AVScope\tmp"
$env:TMP = "G:\AVScope\tmp"

Write-Host "== AVScope release validation =="
Write-Host "Root: $root"

Write-Host "== Unit tests =="
& $python -m unittest discover -s "$root\tests" -v

Write-Host "== Required artifacts =="
$artifacts = @($appExe, $ffprobe, $setup, $portableZip, $sourceZip)
foreach ($artifact in $artifacts) {
    if (-not (Test-Path $artifact)) {
        throw "Missing artifact: $artifact"
    }
    $item = Get-Item $artifact
    if ($item.Length -le 0) {
        throw "Empty artifact: $artifact"
    }
    Write-Host "$($item.FullName) $($item.Length) bytes"
}

Write-Host "== Mojibake scan =="
$bad = @(
    [string][char]0x951B,
    [string][char]0x93B5,
    [string][char]0x93C3,
    [string][char]0x9357,
    [string][char]0x7487,
    [string][char]0x6FEF,
    [string][char]0x9225,
    [string][char]0x9239,
    [string][char]0xFFFD
)
$sourceFiles = Get-ChildItem -Path "$root\avscope" -Recurse -Filter "*.py" -File | ForEach-Object { $_.FullName }
foreach ($file in $sourceFiles) {
    $text = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8)
    foreach ($fragment in $bad) {
        if ($text.Contains($fragment)) {
            throw "Mojibake fragment '$fragment' found in $file"
        }
    }
}
Write-Host "Mojibake scan OK"

Write-Host "== Path constraint scan =="
$scanTargets = @("$root\avscope", "$root\packaging", "$root\scripts")
$scanFiles = Get-ChildItem -Path $scanTargets -Recurse -File |
    Where-Object { $_.FullName -ne "$root\scripts\validate_release.ps1" }
$matches = Select-String -Path $scanFiles.FullName -Pattern "C:\\|PROGRAMFILES|DESKTOP|SMPROGRAMS" -ErrorAction SilentlyContinue
if ($matches) {
    $matches | ForEach-Object { Write-Host $_.Path ":" $_.LineNumber ":" $_.Line }
    throw "Path constraint scan found forbidden target references"
}
Write-Host "Path constraint scan OK"

Write-Host "== Dist executable smoke =="
$process = Start-Process -FilePath $appExe -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
if ($process.HasExited) {
    throw "AVScope.exe exited early with code $($process.ExitCode)"
}
Stop-Process -Id $process.Id -Force
Write-Host "Dist executable smoke OK"

Write-Host "== Installer smoke =="
Start-Process -FilePath $setup -ArgumentList @("/S", "/D=$installDir") -Wait -WindowStyle Hidden
if (-not (Test-Path "$installDir\AVScope.exe")) {
    throw "Installed AVScope.exe not found"
}
if (-not (Test-Path "$installDir\_internal\ffprobe.exe")) {
    throw "Installed ffprobe.exe not found"
}
$installedProcess = Start-Process -FilePath "$installDir\AVScope.exe" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
if ($installedProcess.HasExited) {
    throw "Installed AVScope.exe exited early with code $($installedProcess.ExitCode)"
}
Stop-Process -Id $installedProcess.Id -Force
Start-Process -FilePath "$installDir\Uninstall.exe" -ArgumentList "/S" -Wait -WindowStyle Hidden
if (Test-Path "$installDir\AVScope.exe") {
    throw "Uninstall did not remove AVScope.exe"
}
Write-Host "Installer smoke OK"

Write-Host "== Validation complete =="
