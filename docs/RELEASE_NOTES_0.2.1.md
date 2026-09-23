# AVScope v0.2.1

这是一个兼容性与可移植性更新，重点补充 AVI 2.0/OpenDML 识别，并改善不同开发环境下的构建与发布流程。

## 本次更新

- 新增 AVI 2.0/OpenDML 识别，可根据 OpenDML 头、索引或 `AVIX` 分段判断 AVI 版本。
- 保持对传统 AVI 1.0 文件的兼容，并在分析摘要中显示检测到的 AVI 版本。
- 移除构建和发布校验中的固定盘符依赖，降低换盘符或换机器构建时的配置成本。
- 更新项目简介，让项目定位和主要用途更直观。

## 下载说明

- `AVScope-Setup.exe`：Windows 10/11 64 位安装版，适合大多数用户。
- `AVScope-portable-win-x64.zip`：Windows 10/11 64 位绿色版，解压后运行 `AVScope.exe`。
- `AVScope-portable-source.zip`：项目源码、测试、脚本与文档归档。
- `AVScope-release-manifest.json`：发布文件大小与 SHA256 校验清单。
- `AVScope-validation-report.md`：本次发布的自动化验证结果。

## 升级说明

可直接覆盖旧绿色版目录，或运行新版安装程序覆盖安装。为避免遗留文件影响，建议先关闭正在运行的 AVScope。

## 系统要求

- Windows 10 或 Windows 11，64 位。
- 安装版默认安装到 `%ProgramFiles%\AVScope`，需要管理员权限。
- 当前可执行文件未进行商业代码签名；首次运行时 Windows 可能显示安全提示。可使用发布清单中的 SHA256 核对下载文件。

## 完整变更

**Full Changelog**: https://github.com/ZHG2XU/AVScope/compare/v0.2.0...v0.2.1
