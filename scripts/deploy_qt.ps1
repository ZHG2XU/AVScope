$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$source = "$root\build\qt6\bin\AVScope.exe"
$output = "$root\dist\AVScopeQt"
$deploy = "E:\QT\6.9.0\mingw_64\bin\windeployqt.exe"

if (-not (Test-Path -LiteralPath $source)) {
    & "$root\scripts\build_qt.ps1"
}

New-Item -ItemType Directory -Force -Path $output | Out-Null
Copy-Item -LiteralPath $source -Destination "$output\AVScope.exe" -Force
& $deploy --release --no-translations --no-opengl-sw "$output\AVScope.exe"
if ($LASTEXITCODE -ne 0) { throw "Qt deployment failed" }

Copy-Item -LiteralPath "E:\QT\Tools\mingw1310_64\bin\libgcc_s_seh-1.dll" -Destination $output -Force
Copy-Item -LiteralPath "E:\QT\Tools\mingw1310_64\bin\libstdc++-6.dll" -Destination $output -Force
Copy-Item -LiteralPath "E:\QT\Tools\mingw1310_64\bin\libwinpthread-1.dll" -Destination $output -Force

& "$root\scripts\build_qt_engine.ps1"
if ($LASTEXITCODE -ne 0) { throw "Qt analysis engine deployment failed" }

Write-Output "$output\AVScope.exe"
