from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    candidates = [
        root / "build" / "qt6" / "bin" / "AVScope.exe",
        root / "dist" / "AVScopeQt" / "AVScope.exe",
    ]
    for executable in candidates:
        if executable.exists() and not getattr(sys, "frozen", False):
            environment = os.environ.copy()
            environment.setdefault("AVSCOPE_ROOT", str(root))
            environment.setdefault("AVSCOPE_PYTHON", sys.executable)
            environment.setdefault("TEMP", str(root / "tmp"))
            environment.setdefault("TMP", str(root / "tmp"))
            subprocess.Popen([str(executable), *sys.argv[1:]], env=environment)
            return

    # Compatibility fallback for an undeployed source tree and the legacy package.
    from avscope.app import main as legacy_main

    legacy_main()


if __name__ == "__main__":
    main()
