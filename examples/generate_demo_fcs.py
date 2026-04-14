"""
generate_demo_fcs.py
Creates a synthetic FCS 3.1 file for testing FlowGate.

Simulated populations:
  - Live/Dead marker (Aqua stain)
  - CD45 (pan-leukocyte)
  - CD3  (T cells)
  - CD19 (B cells)
  - CD56 (NK cells)
  - CD14 (monocytes)
"""

import numpy as np
import struct
import os
import sys


def write_minimal_fcs(filepath, data, channel_names):
    """Write float32 FCS 3.1 with minimal TEXT."""
    n_events, n_ch = data.shape
    delim = "|"

    text = {
        "$BEGINANALYSIS": "0", "$ENDANALYSIS": "0",
        "$BEGINDATA": "0", "$ENDDATA": "0",
        "$BYTEORD": "1,2,3,4", "$DATATYPE": "F",
        "$MODE": "L", "$NEXTDATA": "0",
        "$PAR": str(n_ch), "$TOT": str(n_events),
        "$CYT": "DemoFCS",
        "$DATE": "14-APR-2026",
    }
    for i, name in enumerate(channel_names, 1):
        text[f"$P{i}N"] = name
        text[f"$P{i}S"] = name
        text[f"$P{i}B"] = "32"
        text[f"$P{i}R"] = "262144"
        text[f"$P{i}E"] = "0,0"

    def encode(pairs):
        parts = []
        for k, v in pairs.items():
            parts.append(k)
            parts.append(v)
        return (delim + delim.join(parts) + delim).encode("latin-1")

    data_bytes = data.astype(np.float32).tobytes()
    HEADER = 58
    TEXT_START = HEADER

    text_bytes = encode(text)
    TEXT_END = TEXT_START + len(text_bytes) - 1
    DATA_START = TEXT_END + 1
    DATA_END = DATA_START + len(data_bytes) - 1

    text["$BEGINDATA"] = str(DATA_START)
    text["$ENDDATA"] = str(DATA_END)
    text_bytes = encode(text)
    TEXT_END = TEXT_START + len(text_bytes) - 1
    DATA_START = TEXT_END + 1
    DATA_END = DATA_START + len(data_bytes) - 1
    text["$BEGINDATA"] = str(DATA_START)
    text["$ENDDATA"] = str(DATA_END)
    text_bytes = encode(text)
    TEXT_END = TEXT_START + len(text_bytes) - 1
    DATA_START = TEXT_END + 1
    DATA_END = DATA_START + len(data_bytes) - 1

    hdr = "FCS3.1    "
    hdr += f"{TEXT_START:>8}{TEXT_END:>8}{DATA_START:>8}{DATA_END:>8}{'0':>8}{'0':>8}"
    hdr_b = hdr.encode("latin-1").ljust(58)

    with open(filepath, "wb") as f:
        f.write(hdr_b)
        f.write(text_bytes)
        f.write(data_bytes)


def generate_demo(out_path="demo_PBMC.fcs", n_total=30000, seed=42):
    rng = np.random.default_rng(seed)

    channels = ["FSC-A", "SSC-A", "Live_Dead_Aqua",
                "CD45", "CD3", "CD19", "CD56", "CD14", "HLA-DR"]
    n_ch = len(channels)

    # Proportions
    pop_fracs = {
        "debris":    0.05,
        "dead":      0.10,
        "T_cells":   0.35,  # CD45+ CD3+
        "B_cells":   0.15,  # CD45+ CD19+
        "NK_cells":  0.10,  # CD45+ CD56+
        "Monocytes": 0.15,  # CD45+ CD14+
        "other":     0.10,
    }
    counts = {k: int(v * n_total) for k, v in pop_fracs.items()}
    counts["T_cells"] += n_total - sum(counts.values())  # pad rounding

    def gauss(mu, sd, n, lo=0, hi=262144):
        return np.clip(rng.normal(mu, sd, n), lo, hi)

    rows = []

    # Debris — small, low signal
    n = counts["debris"]
    fsc = gauss(8000, 3000, n)
    ssc = gauss(4000, 2000, n)
    ld  = gauss(60000, 20000, n)   # high live/dead (dead)
    cd45 = gauss(500, 300, n)
    cd3  = gauss(300, 200, n)
    cd19 = gauss(300, 200, n)
    cd56 = gauss(300, 200, n)
    cd14 = gauss(300, 200, n)
    hlad = gauss(500, 300, n)
    rows.append(np.column_stack([fsc, ssc, ld, cd45, cd3, cd19, cd56, cd14, hlad]))

    # Dead cells
    n = counts["dead"]
    fsc = gauss(30000, 12000, n)
    ssc = gauss(20000, 8000, n)
    ld  = gauss(80000, 15000, n)
    cd45 = gauss(20000, 8000, n)
    cd3  = gauss(500, 300, n)
    cd19 = gauss(500, 300, n)
    cd56 = gauss(500, 300, n)
    cd14 = gauss(500, 300, n)
    hlad = gauss(3000, 1500, n)
    rows.append(np.column_stack([fsc, ssc, ld, cd45, cd3, cd19, cd56, cd14, hlad]))

    # T cells — CD45+ CD3+
    n = counts["T_cells"]
    fsc = gauss(55000, 8000, n)
    ssc = gauss(25000, 6000, n)
    ld  = gauss(1000, 500, n)
    cd45 = gauss(55000, 10000, n)
    cd3  = gauss(60000, 10000, n)
    cd19 = gauss(500, 300, n)
    cd56 = gauss(800, 400, n)
    cd14 = gauss(500, 300, n)
    hlad = gauss(2000, 1000, n)
    rows.append(np.column_stack([fsc, ssc, ld, cd45, cd3, cd19, cd56, cd14, hlad]))

    # B cells — CD45+ CD19+
    n = counts["B_cells"]
    fsc = gauss(45000, 7000, n)
    ssc = gauss(22000, 5000, n)
    ld  = gauss(1200, 600, n)
    cd45 = gauss(50000, 10000, n)
    cd3  = gauss(600, 300, n)
    cd19 = gauss(65000, 10000, n)
    cd56 = gauss(600, 300, n)
    cd14 = gauss(500, 300, n)
    hlad = gauss(55000, 12000, n)
    rows.append(np.column_stack([fsc, ssc, ld, cd45, cd3, cd19, cd56, cd14, hlad]))

    # NK cells — CD45+ CD56+
    n = counts["NK_cells"]
    fsc = gauss(50000, 7000, n)
    ssc = gauss(24000, 5000, n)
    ld  = gauss(1000, 500, n)
    cd45 = gauss(52000, 10000, n)
    cd3  = gauss(700, 350, n)
    cd19 = gauss(600, 300, n)
    cd56 = gauss(62000, 12000, n)
    cd14 = gauss(500, 300, n)
    hlad = gauss(3000, 1200, n)
    rows.append(np.column_stack([fsc, ssc, ld, cd45, cd3, cd19, cd56, cd14, hlad]))

    # Monocytes — CD45+ CD14+
    n = counts["Monocytes"]
    fsc = gauss(70000, 10000, n)
    ssc = gauss(50000, 12000, n)
    ld  = gauss(1500, 700, n)
    cd45 = gauss(48000, 10000, n)
    cd3  = gauss(500, 300, n)
    cd19 = gauss(500, 300, n)
    cd56 = gauss(600, 300, n)
    cd14 = gauss(65000, 12000, n)
    hlad = gauss(50000, 10000, n)
    rows.append(np.column_stack([fsc, ssc, ld, cd45, cd3, cd19, cd56, cd14, hlad]))

    # Other lymphocytes
    n = counts["other"]
    fsc = gauss(48000, 8000, n)
    ssc = gauss(22000, 6000, n)
    ld  = gauss(1500, 800, n)
    cd45 = gauss(45000, 10000, n)
    cd3  = gauss(800, 400, n)
    cd19 = gauss(700, 400, n)
    cd56 = gauss(700, 400, n)
    cd14 = gauss(600, 300, n)
    hlad = gauss(4000, 2000, n)
    rows.append(np.column_stack([fsc, ssc, ld, cd45, cd3, cd19, cd56, cd14, hlad]))

    data = np.vstack(rows)
    data = np.clip(data, 0, 262143)
    write_minimal_fcs(out_path, data, channels)
    print(f"Demo FCS written: {out_path}  ({len(data):,} events, {n_ch} channels)")
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "demo_PBMC.fcs"
    generate_demo(out)
