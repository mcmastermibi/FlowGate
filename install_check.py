#!/usr/bin/env python3
"""
install_check.py — Verify FlowGate dependencies are correctly installed.
Run this before launching the GUI for the first time.
"""
import sys
import subprocess

REQUIRED = {
    "flowio":     "1.3",
    "numpy":      "1.22",
    "matplotlib": "3.7",
    "scipy":      "1.9",
}

OPTIONAL = {
    "tkinter": "bundled with Python (install python3-tk on Linux if missing)",
}

def check():
    print("FlowGate — Dependency Check")
    print("=" * 40)
    all_ok = True

    for pkg, min_ver in REQUIRED.items():
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "?")
            print(f"  ✓  {pkg:<15} {ver}")
        except ImportError:
            print(f"  ✗  {pkg:<15} NOT FOUND — install with: pip install {pkg}>={min_ver}")
            all_ok = False

    print()
    # tkinter special check
    try:
        import tkinter
        print(f"  ✓  tkinter         {tkinter.TkVersion}")
    except ImportError:
        print(f"  ✗  tkinter         NOT FOUND")
        print(f"       Ubuntu/Debian: sudo apt install python3-tk")
        print(f"       Conda:         conda install tk")
        all_ok = False

    print()
    if all_ok:
        print("All dependencies satisfied. You can launch FlowGate with:")
        print("  python run_flowgate.py")
        print("  # or after pip install -e .")
        print("  flowgate")
    else:
        print("Install missing packages, then re-run this check.")
        sys.exit(1)

if __name__ == "__main__":
    check()
