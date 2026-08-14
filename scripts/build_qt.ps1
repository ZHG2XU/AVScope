param(
    [switch]$SkipDeploy
)

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
$qtInstallRoot = if ($qtRoot) { Split-Path (Split-Path $qtRoot -Parent) -Parent } else { "" }
if (-not $cmake -and $qtInstallRoot) {
    $cmakeCandidate = Join-Path $qtInstallRoot "Tools\CMake\bin\cmake.exe"
    if (Test-Path -LiteralPath $cmakeCandidate) { $cmake = $cmakeCandidate }
}
if (-not $ninja -and $qtInstallRoot) {
    $ninjaCandidate = Join-Path $qtInstallRoot "Tools\Ninja\ninja.exe"
    if (Test-Path -LiteralPath $ninjaCandidate) { $ninja = $ninjaCandidate }
}
if (-not $mingw) {
    $mingwCommand = Get-Command g++.exe -ErrorAction SilentlyContinue
    if ($mingwCommand) {
        $mingw = Split-Path $mingwCommand.Source
    }
}
if (-not $mingw -and $qtRoot) {
    $mingw = Get-ChildItem (Join-Path $qtInstallRoot "Tools") -Directory -Filter "mingw*_64" -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "bin\g++.exe") } |
        Sort-Object Name -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if ($mingw) {
        $mingw = Join-Path $mingw "bin"
    }
}
if (-not $qtRoot) { throw "Qt not found. Set AVSCOPE_QT_ROOT to the Qt MinGW directory." }
if (-not $cmake) { throw "CMake not found. Set AVSCOPE_CMAKE or install CMake." }
if (-not $ninja) { throw "Ninja not found. Set AVSCOPE_NINJA or install Ninja." }
if (-not $mingw) { throw "MinGW not found. Set AVSCOPE_MINGW to the compiler bin directory." }
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

$executable = "$build\bin\AVScope.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Qt build completed but AVScope.exe was not found: $executable"
}

if (-not $SkipDeploy) {
    $deploy = if ($env:AVSCOPE_WINDEPLOYQT) { $env:AVSCOPE_WINDEPLOYQT } else { Join-Path $qtRoot "bin\windeployqt.exe" }
    if (-not (Test-Path -LiteralPath $deploy)) {
        $deployCommand = Get-Command windeployqt.exe -ErrorAction SilentlyContinue
        $deploy = if ($deployCommand) { $deployCommand.Source } else { "" }
    }
    if (-not $deploy) {
        throw "windeployqt.exe not found. Set AVSCOPE_WINDEPLOYQT or use -SkipDeploy."
    }

    & $deploy --release --no-translations --no-opengl-sw --compiler-runtime --dir (Split-Path $executable) $executable
    if ($LASTEXITCODE -ne 0) { throw "Qt runtime deployment failed" }

    $requiredRuntimeFiles = @(
        "$build\bin\Qt6Core.dll",
        "$build\bin\Qt6Gui.dll",
        "$build\bin\Qt6Widgets.dll",
        "$build\bin\Qt6Multimedia.dll",
        "$build\bin\libgcc_s_seh-1.dll",
        "$build\bin\libstdc++-6.dll",
        "$build\bin\libwinpthread-1.dll",
        "$build\bin\platforms\qwindows.dll"
    )
    $missingRuntimeFiles = $requiredRuntimeFiles | Where-Object { -not (Test-Path -LiteralPath $_) }
    if ($missingRuntimeFiles) {
        throw "Qt runtime deployment is incomplete. Missing: $($missingRuntimeFiles -join ', ')"
    }
}

Write-Output "AVScope build completed:"
Write-Output "  Executable: $executable"
Write-Output "  Runtime directory: $(Split-Path $executable)"
if ($SkipDeploy) {
    Write-Output "  Qt deployment: skipped (-SkipDeploy)"
} else {
    Write-Output "  Qt deployment: complete"
}
