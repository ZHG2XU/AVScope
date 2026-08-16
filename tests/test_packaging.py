from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallerContractTests(unittest.TestCase):
    def test_installer_uses_modern_branded_pages(self) -> None:
        script = (ROOT / "packaging" / "AVScope.nsi").read_text(encoding="utf-8")

        self.assertIn('!include "MUI2.nsh"', script)
        self.assertIn("MUI_WELCOMEFINISHPAGE_BITMAP", script)
        self.assertIn("MUI_HEADERIMAGE_BITMAP", script)
        self.assertIn('MUI_FONT "Microsoft YaHei UI"', script)
        self.assertIn("Page custom OptionsPageCreate OptionsPageLeave", script)
        self.assertIn("MUI_FINISHPAGE_RUN", script)
        self.assertIn("ManifestDPIAware false", script)

    def test_installer_defaults_to_64_bit_program_files(self) -> None:
        script = (ROOT / "packaging" / "AVScope.nsi").read_text(encoding="utf-8")

        self.assertIn('InstallDir "$PROGRAMFILES64\\AVScope"', script)
        self.assertIn("RequestExecutionLevel admin", script)
        self.assertIn("SetShellVarContext all", script)

    def test_installer_assets_exist(self) -> None:
        assets = ROOT / "packaging" / "assets"

        for name in ("installer-welcome.bmp", "installer-header.bmp"):
            path = assets / name
            self.assertTrue(path.is_file(), f"missing installer asset: {path}")
            self.assertGreater(path.stat().st_size, 0)

    def test_installer_build_wrapper_uses_utf8(self) -> None:
        script = (ROOT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")

        self.assertIn("/WX /INPUTCHARSET UTF8", script)
        self.assertIn("generate_installer_assets.ps1", script)

    def test_public_versions_are_consistent(self) -> None:
        python_init = (ROOT / "avscope" / "__init__.py").read_text(encoding="utf-8")
        cmake = (ROOT / "qt" / "CMakeLists.txt").read_text(encoding="utf-8")
        installer = (ROOT / "packaging" / "AVScope.nsi").read_text(encoding="utf-8")

        python_version = re.search(r'__version__ = "([^"]+)"', python_init)
        qt_version = re.search(r"project\(AVScopeQt VERSION ([^ ]+)", cmake)
        installer_version = re.search(r'!define APP_VERSION "([^"]+)"', installer)
        self.assertIsNotNone(python_version)
        self.assertIsNotNone(qt_version)
        self.assertIsNotNone(installer_version)
        self.assertEqual(
            python_version.group(1),
            qt_version.group(1),
        )
        self.assertEqual(
            python_version.group(1),
            installer_version.group(1),
        )

    def test_validation_supports_elevated_installer_skip(self) -> None:
        script = (ROOT / "scripts" / "validate_release.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$SkipInstallerSmoke", script)
        self.assertIn("--installer-smoke $installerSmokeStatus", script)


if __name__ == "__main__":
    unittest.main()
