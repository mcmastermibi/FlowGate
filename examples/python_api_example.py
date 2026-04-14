#!/usr/bin/env python3
"""
python_api_example.py
Demonstrates programmatic use of FlowGate without the GUI.

Useful for:
  - Building gates from code (e.g. from known channel cutoffs)
  - Integrating gated populations into a downstream pipeline
  - Verifying exported FCS files
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from flowgate import read_fcs, write_fcs, apply_transform
from flowgate.gates import Gate, GateHierarchy


def main():
    # ── 1. Read FCS ────────────────────────────────────────────────
    fcs_path = Path(__file__).parent / "demo_PBMC.fcs"
    if not fcs_path.exists():
        print("Generating demo FCS first…")
        from generate_demo_fcs import generate_demo
        generate_demo(str(fcs_path))

    print(f"\n── Reading FCS ──")
    fcs = read_fcs(str(fcs_path))
    print(f"  File     : {fcs['filename']}")
    print(f"  Events   : {len(fcs['data']):,}")
    print(f"  Channels : {fcs['channels']}")

    # ── 2. Apply arcsinh transform (cofactor 150 for conventional flow) ──
    display = apply_transform(fcs["data"], transform="asinh", cofactor=150)
    channels = fcs["channels"]

    # ── 3. Build a gate hierarchy programmatically ──────────────────
    print(f"\n── Building gate hierarchy ──")
    h = GateHierarchy()

    # Helper: get channel index
    def ch(name):
        return channels.index(name)

    # Gate 1: Live cells — FSC-A vs Live_Dead_Aqua (low Aqua = live)
    # In arcsinh(150) space, live cells cluster below ~3.0 on Aqua axis
    g_live = Gate(
        name="Live",
        x_channel="FSC-A",
        y_channel="Live_Dead_Aqua",
        parent_id=None,
        gate_type="rectangle",
        rect_bounds=(4.0, -1.0, 8.0, 3.0),   # (x0, y0, x1, y1) in display space
    )
    h.add_gate(g_live)

    # Gate 2: CD45+ — within Live, gate on CD45 high
    g_cd45 = Gate(
        name="CD45+",
        x_channel="FSC-A",
        y_channel="CD45",
        parent_id=g_live.id,
        gate_type="rectangle",
        rect_bounds=(4.0, 5.0, 8.0, 9.0),
    )
    h.add_gate(g_cd45)

    # Gate 3: T cells (CD3+) — within CD45+, gate on CD3 high
    g_tcell = Gate(
        name="T_cells_CD3pos",
        x_channel="CD45",
        y_channel="CD3",
        parent_id=g_cd45.id,
        gate_type="rectangle",
        rect_bounds=(5.0, 5.0, 9.0, 9.0),
    )
    h.add_gate(g_tcell)

    # Gate 4: B cells (CD19+) — within CD45+, gate on CD19 high
    g_bcell = Gate(
        name="B_cells_CD19pos",
        x_channel="CD45",
        y_channel="CD19",
        parent_id=g_cd45.id,
        gate_type="rectangle",
        rect_bounds=(5.0, 5.0, 9.0, 9.0),
    )
    h.add_gate(g_bcell)

    # Gate 5: Monocytes (CD14+) — within CD45+
    g_mono = Gate(
        name="Monocytes_CD14pos",
        x_channel="CD45",
        y_channel="CD14",
        parent_id=g_cd45.id,
        gate_type="rectangle",
        rect_bounds=(5.0, 5.0, 9.0, 9.0),
    )
    h.add_gate(g_mono)

    # ── 4. Print gate statistics ────────────────────────────────────
    print(f"\n── Gate Statistics ──")
    n_total = len(display)
    print(f"  {'Gate':<25} {'N':>7}  {'% Parent':>9}  {'% Total':>8}")
    print(f"  {'-'*55}")
    print(f"  {'All Events':<25} {n_total:>7,}  {'100.0%':>9}  {'100.0%':>8}")

    for gate in h.gates:
        stats = h.get_gate_stats(gate.id, display, channels)
        indent = "  " if gate.parent_id is None else "    └─ "
        print(
            f"  {indent}{gate.name:<21} {stats['count']:>7,}  "
            f"{stats['pct_parent']:>8.1f}%  {stats['pct_total']:>7.1f}%"
        )

    # ── 5. Export gated populations ─────────────────────────────────
    print(f"\n── Exporting gated FCS files ──")
    out_dir = Path(__file__).parent / "exported_gates"
    out_dir.mkdir(exist_ok=True)

    for gate in h.gates:
        idxs = h.get_event_indices(gate.id, display, channels)
        raw_gated = fcs["data"][idxs]
        out_path = out_dir / f"{gate.name}.fcs"
        write_fcs(str(out_path), raw_gated, channels, fcs["metadata"])
        print(f"  Exported {gate.name}: {len(idxs):,} events → {out_path.name}")

    # ── 6. Save gate hierarchy ──────────────────────────────────────
    gates_json = out_dir / "gates.json"
    h.save(str(gates_json))
    print(f"\n  Gate hierarchy saved → {gates_json}")

    # ── 7. Round-trip verification ──────────────────────────────────
    print(f"\n── Round-trip verification ──")
    h2 = GateHierarchy()
    h2.load(str(gates_json))
    assert len(h2.gates) == len(h.gates), "Gate count mismatch after reload!"
    for g1, g2 in zip(h.gates, h2.gates):
        i1 = h.get_event_indices(g1.id, display, channels)
        i2 = h2.get_event_indices(g2.id, display, channels)
        assert len(i1) == len(i2), f"Event count mismatch for gate '{g1.name}'"
    print("  All gates reload correctly ✓")

    # ── 8. Read exported FCS and confirm usable ─────────────────────
    print(f"\n── Verifying exported FCS files ──")
    for gate in h.gates:
        fcs_out = read_fcs(str(out_dir / f"{gate.name}.fcs"))
        expected = h.get_event_indices(gate.id, display, channels)
        assert len(fcs_out["data"]) == len(expected), \
            f"Exported event count mismatch for {gate.name}"
        assert fcs_out["channels"] == channels, "Channel mismatch in exported FCS"
    print("  All exported FCS files verified ✓")

    print(f"\n✓ FlowGate API example complete. Exports in: {out_dir}\n")


if __name__ == "__main__":
    main()
