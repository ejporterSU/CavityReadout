"""Launcher for the Cleverscope readout app.

Fixes the two environment quirks the vendor driver needs, then opens the window:
  - puts the "Cscope control driver" folder on sys.path so the flat vendor
    imports (CleverscopeInterface, cscope_class, T_*) resolve, and
  - sets the working directory to the repo root so the DLL's relative path
    ("Cscope control driver\\Cscope control driver 64.dll") resolves.

Usage:
    python run_scope.py            # real hardware (needs the DLL + scope)
    python run_scope.py --simulate # synthetic noisy sine waves, no hardware
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DRIVER_DIR = os.path.join(REPO_ROOT, "Cscope control driver")

sys.path.insert(0, DRIVER_DIR)
os.chdir(REPO_ROOT)

from gui import main  # noqa: E402  (import after sys.path fix)

if __name__ == "__main__":
    simulate = "--simulate" in sys.argv or "-s" in sys.argv
    main(simulate=simulate)
