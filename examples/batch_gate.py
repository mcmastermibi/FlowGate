#!/usr/bin/env python3
"""
batch_gate.py — Apply a saved FlowGate hierarchy to a folder of FCS files.

Usage:
    python batch_gate.py --gates my_gates.json --input ./fcs_folder --output ./gated_output

This is the downstream Python pipeline entry point. Load gates you defined
interactively in the FlowGate GUI and apply them to an entire cohort.
"""

import argparse
import os
import sys
import json
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flowgate import read_fcs, write_fcs, apply_transform
from flowgate.gates import GateHierarchy


def batch_gate(
    gates_json: str,
    input_dir: str,
    output_dir: str,
    gate_names: list[str] | None = None,
    transform: str = "asinh",
    cofactor: float = 150.0,
    export_stats: bool = True,
):
    """
    Apply a gate hierarchy to every FCS file in input_dir.

    Parameters
    ----------
    gates_json   : Path to .json gate file saved from FlowGate GUI
    input_dir    : Folder containing source FCS files
    output_dir   : Destination folder for gated FCS exports
    gate_names   : List of gate names to export (None = all gates)
    transform    : Transform for gating computation ("asinh", "log", "linear")
    cofactor     : Cofactor for asinh transform
    export_stats : If True, write a summary CSV with event counts
    """
    os.makedirs(output_dir, exist_ok=True)

    # Load gate hierarchy
    h = GateHierarchy()
    h.load(gates_json)
    print(f"Loaded {len(h.gates)} gates from {gates_json}")

    # Filter to requested gates
    gates_to_export = h.gates
    if gate_names:
        gates_to_export = [g for g in h.gates if g.name in gate_names]
        found = [g.name for g in gates_to_export]
        missing = [n for n in gate_names if n not in found]
        if missing:
            print(f"  WARNING: gates not found in hierarchy: {missing}")

    # Find FCS files
    fcs_files = sorted(Path(input_dir).glob("*.fcs"))
    if not fcs_files:
        print(f"No .fcs files found in {input_dir}")
        return

    print(f"Processing {len(fcs_files)} FCS files → {output_dir}")
    print("-" * 60)

    stats_rows = []

    for fcs_path in fcs_files:
        stem = fcs_path.stem
        print(f"\n  {fcs_path.name}")

        try:
            fcs = read_fcs(str(fcs_path))
            display = apply_transform(fcs["data"], transform=transform, cofactor=cofactor)
            channels = fcs["channels"]
            n_total = len(fcs["data"])
        except Exception as e:
            print(f"    ERROR reading file: {e}")
            continue

        for gate in gates_to_export:
            # Check all required channels exist
            missing_ch = [
                ch for ch in [gate.x_channel, gate.y_channel]
                if ch and ch not in channels
            ]
            if missing_ch:
                print(f"    SKIP gate '{gate.name}': channels {missing_ch} not in file")
                continue

            try:
                idxs = h.get_event_indices(gate.id, display, channels)
                raw_gated = fcs["data"][idxs]
                n_gated = len(idxs)

                # Build output path: <stem>_<GateName>.fcs
                safe_name = gate.name.replace(" ", "_").replace("/", "-")
                out_name = f"{stem}_{safe_name}.fcs"
                out_path = os.path.join(output_dir, out_name)

                write_fcs(out_path, raw_gated, channels, fcs["metadata"])

                pct = n_gated / n_total * 100 if n_total > 0 else 0
                print(f"    → {gate.name}: {n_gated:,} / {n_total:,} events ({pct:.1f}%)  [{out_name}]")

                stats_rows.append({
                    "file": fcs_path.name,
                    "gate": gate.name,
                    "n_total": n_total,
                    "n_gated": n_gated,
                    "pct_total": round(pct, 2),
                    "output_file": out_name,
                })

            except Exception as e:
                print(f"    ERROR gating '{gate.name}': {e}")

    # Write stats CSV
    if export_stats and stats_rows:
        stats_path = os.path.join(output_dir, "gate_stats.csv")
        import csv
        fieldnames = ["file", "gate", "n_total", "n_gated", "pct_total", "output_file"]
        with open(stats_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(stats_rows)
        print(f"\nStats written → {stats_path}")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(
        description="Batch-apply FlowGate hierarchy to a folder of FCS files"
    )
    parser.add_argument("--gates", required=True, help="Path to .json gate file")
    parser.add_argument("--input", required=True, help="Folder of source FCS files")
    parser.add_argument("--output", required=True, help="Destination folder for exports")
    parser.add_argument(
        "--gate-names", nargs="*", default=None,
        help="Gate names to export (default: all gates)"
    )
    parser.add_argument(
        "--transform", default="asinh", choices=["asinh", "log", "linear"],
        help="Transform used for gating (default: asinh)"
    )
    parser.add_argument(
        "--cofactor", type=float, default=150.0,
        help="Cofactor for asinh transform (default: 150)"
    )
    parser.add_argument(
        "--no-stats", action="store_true",
        help="Skip writing gate_stats.csv"
    )
    args = parser.parse_args()

    batch_gate(
        gates_json=args.gates,
        input_dir=args.input,
        output_dir=args.output,
        gate_names=args.gate_names,
        transform=args.transform,
        cofactor=args.cofactor,
        export_stats=not args.no_stats,
    )


if __name__ == "__main__":
    main()
