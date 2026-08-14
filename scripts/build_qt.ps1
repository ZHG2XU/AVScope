$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$qtRoot = if ($env:AVSCOPE_QT_ROOT) { $env:AVSCOPE_QT_ROOT } else { "" }
if (-not $qtRoot) {
    $qtRoot = (Get-ChildItem "C:\Qt","E:\Qt","D:\Qt" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue } |
        Where-Object { Test-Path (Join-Path $_.FullName "bin\qmake.exe") } |
        Select-Object -First 1 -ExpandProperty FullName)
}
$cmake = if ($env:AVSCOPE_CMAKE) { $env:AVSCOPE_CMAKE } else { (Get-Command cmake -ErrorAction SilentlyContinue).Source }
$ninja = if ($env:AVSCOPE_NINJA) { $env:AVSCOPE_NINJA } else { (Get-Command ninja -ErrorAction SilentlyContinue).Source }
$mingw = if ($env:AVSCOPE_MINGW) { $env:AVSCOPE_MINGW } else { "" }
if (-not $qtRoot) { throw "Qt not found. Set AVSCOPE_QT_ROOT to the Qt MinGW directory." }
if (-not $cmake) { throw "CMake not found. Set AVSCOPE_CMAKE or install CMake." }
if (-not $ninja) { throw "Ninja not found. Set AVSCOPE_NINJA or install Ninja." }
<##
if (-not $qtRoot) { throw "未找到 Qt。请安装 Qt 6.x MinGW，或设置 `$env:AVSCOPE_QT_ROOT 为 Qt 的 mingw_64 目录。" }
if (-not $cmake) { throw "未找到 CMake。请安装 CMake 或设置 `$env:AVSCOPE_CMAKE。" }
if (-not $ninja) { throw "未找到 Ninja。请安装 Ninja 或设置 `$env:AVSCOPE_NINJA。" }
##>
$build = "$root\build\qt6"

$env:PATH = "$(if($mingw){$mingw+';'})$($ninja | Split-Path);$qtRoot\bin;$env:PATH"
$tmpRoot = Join-Path $root "tmp"
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null
$env:TEMP = "$root\tmp"
$env:TMP = "$root\tmp"

& $cmake -S "$root\qt" -B $build -G Ninja -DCMAKE_PREFIX_PATH=$qtRoot -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw "Qt CMake configure failed" }

& $cmake --build $build --parallel
if ($LASTEXITCODE -ne 0) { throw "Qt build failed" }

Write-Output "$build\bin\AVScope.exe"
