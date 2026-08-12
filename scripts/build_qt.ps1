$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$qtRoot = "E:\QT\6.9.0\mingw_64"
$cmake = "E:\QT\Tools\CMake_64\bin\cmake.exe"
$ninja = "E:\QT\Tools\Ninja"
$mingw = "E:\QT\Tools\mingw1310_64\bin"
$build = "$root\build\qt6"

$env:PATH = "$mingw;$ninja;$qtRoot\bin;$env:PATH"
$env:TEMP = "$root\tmp"
$env:TMP = "$root\tmp"

& $cmake -S "$root\qt" -B $build -G Ninja -DCMAKE_PREFIX_PATH=$qtRoot -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw "Qt CMake configure failed" }

& $cmake --build $build --parallel
if ($LASTEXITCODE -ne 0) { throw "Qt build failed" }

Write-Output "$build\bin\AVScope.exe"
