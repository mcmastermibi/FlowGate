#!/usr/bin/env python3
"""
run_flowgate.py — Direct launcher for FlowGate (no installation required)
Usage: python run_flowgate.py [optional_fcs_file.fcs]
"""
import sys
import os

# Allow running from the repo root without installing
sys.path.insert(0, os.path.dirname(__file__))

from flowgate.app import FlowGateApp
import tkinter as tk


def main():
    root = tk.Tk()
    app = FlowGateApp(root)

    # Optional: pre-load FCS from command line
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(200, lambda: app._load_fcs_path(sys.argv[1]))

    root.mainloop()


if __name__ == "__main__":
    main()
