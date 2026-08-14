$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$source = "$root\build\qt6\bin\AVScope.exe"
$output = "$root\dist\AVScopeQt"
$deploy = if ($env:AVSCOPE_WINDEPLOYQT) { $env:AVSCOPE_WINDEPLOYQT } else { "" }
if (-not $deploy -and $env:AVSCOPE_QT_ROOT) { $deploy = Join-Path $env:AVSCOPE_QT_ROOT "bin\windeployqt.exe" }
if (-not $deploy) { $deploy = (Get-Command windeployqt.exe -ErrorAction SilentlyContinue).Source }
if (-not $deploy) { throw "windeployqt.exe not found. Set AVSCOPE_WINDEPLOYQT." }
<##
if (-not $deploy) { throw "未找到 windeployqt.exe。请设置 `$env:AVSCOPE_WINDEPLOYQT。" }

##>
if (-not (Test-Path -LiteralPath $source)) {
    & "$root\scripts\build_qt.ps1"
}

New-Item -ItemType Directory -Force -Path $output | Out-Null
Copy-Item -LiteralPath $source -Destination "$output\AVScope.exe" -Force
& $deploy --release --no-translations --no-opengl-sw "$output\AVScope.exe"
if ($LASTEXITCODE -ne 0) { throw "Qt deployment failed" }

$mingwBin = if ($env:AVSCOPE_MINGW) { $env:AVSCOPE_MINGW } else { Split-Path (Get-Command g++.exe -ErrorAction SilentlyContinue).Source -ErrorAction SilentlyContinue }
foreach ($dll in @("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")) {
    $sourceDll = if ($mingwBin) { Join-Path $mingwBin $dll } else { "" }
    if ($sourceDll -and (Test-Path $sourceDll)) { Copy-Item -LiteralPath $sourceDll -Destination $output -Force }
}

& "$root\scripts\build_qt_engine.ps1"
if ($LASTEXITCODE -ne 0) { throw "Qt analysis engine deployment failed" }

Write-Output "$output\AVScope.exe"
