# FlowGate 🔬

**Open-source manual FCS gating — a Python alternative to FlowJo / FCS Express / OMIQ**

FlowGate is a standalone desktop application for manually gating flow cytometry (and MIBI/CyTOF) FCS files. Gates are saved as portable JSON, and gated populations are exported as standard FCS 3.1 files ready for downstream Python pipelines.

---

## Features

| Feature | Details |
|---|---|
| **FCS support** | FCS 2.0, 3.0, 3.1 via `flowio` |
| **Gate types** | Polygon, Rectangle |
| **Gate hierarchy** | Unlimited sequential gating (e.g. Live → CD45+ → CD3+) |
| **Transforms** | arcsinh (cofactor adjustable), log, linear |
| **Export** | Per-gate FCS 3.1 export (original raw values, not transformed) |
| **Gate persistence** | Save/load gate hierarchy as JSON |
| **Subsample display** | Fast rendering of large files (≤50k events shown) |

---

## Installation

```bash
# 1. Clone or download
git clone https://github.com/yourlab/flowgate.git
cd flowgate

# 2. Install (editable recommended for development)
pip install -e .

# Or install directly:
pip install flowio numpy matplotlib scipy
```

### Requirements
- Python ≥ 3.9
- `flowio` ≥ 1.3
- `numpy`, `matplotlib`, `scipy`
- `tkinter` (bundled with most Python installs; on Linux: `sudo apt install python3-tk`)

---

## Quick Start

```bash
# Launch GUI
flowgate

# Or from Python
python -m flowgate.app
```

### Generating a demo FCS file

```bash
cd examples
python generate_demo_fcs.py demo_PBMC.fcs
```

This creates a 30,000-event synthetic PBMC file with channels:
`FSC-A`, `SSC-A`, `Live_Dead_Aqua`, `CD45`, `CD3`, `CD19`, `CD56`, `CD14`, `HLA-DR`

---

## Typical Gating Workflow

### Example: Live / CD45+ / CD3+ sequential gating

```
All Events
  └── Live (FSC-A vs Live_Dead_Aqua — polygon on low aqua)
        └── CD45+ (FSC-A vs CD45 — polygon on high CD45)
              └── CD3+ (CD45 vs CD3 — polygon on high CD3)
```

**Step-by-step in the GUI:**

1. **Open FCS** → `File > Open FCS…` or `Ctrl+O`
2. **Set axes** → Select X and Y channels from the dropdowns
3. **Set transform** → `asinh` with cofactor `150` is good for most instruments
4. **Draw gate** → Click `✏ Polygon` or `▭ Rectangle`, draw on the plot
   - Polygon: click to place vertices → press `Enter` to close
   - Rectangle: click and drag
5. **Name the gate** → A dialog will prompt for a name (e.g. `Live`)
6. **Gate into population** → Select `Live` in the hierarchy tree → click `⊕ Gate In`
7. **Change axes** → Set X/Y to the next markers (e.g. `FSC-A` vs `CD45`)
8. **Draw next gate** → Repeat; it will be nested under `Live`
9. **Export** → `File > Export Gated Population…` or `File > Export All Gates…`

---

## Gate Hierarchy Panel

| Action | How |
|---|---|
| Select a gate | Single-click in the tree |
| Set as parent for next gate | Click `⊕ Gate In` or double-click |
| Rename gate | Select → click `✎ Rename` |
| Delete gate (+ children) | Select → click `✕ Delete` or press `Delete` key |
| Save all gates | `File > Save Gate Hierarchy…` → saves as `.json` |
| Load gates | `File > Load Gate Hierarchy…` → restores gates onto current data |

The tree shows **event count** and **% of parent** for each gate, updating live.

---

## Python API (programmatic use)

```python
from flowgate import read_fcs, write_fcs, apply_transform
from flowgate.gates import Gate, GateHierarchy

# Read
fcs = read_fcs("my_file.fcs")
display = apply_transform(fcs["data"], transform="asinh", cofactor=150)

# Load a saved hierarchy
h = GateHierarchy()
h.load("my_gates.json")

# Get event indices for a gate by name
gate = next(g for g in h.gates if g.name == "CD3+")
idxs = h.get_event_indices(gate.id, display, fcs["channels"])

# Export raw (untransformed) events
raw_gated = fcs["data"][idxs]
write_fcs("CD3pos_export.fcs", raw_gated, fcs["channels"], fcs["metadata"])

print(f"{len(idxs):,} events in CD3+ gate")
```

---

## File Formats

### Exported FCS
- **Format**: FCS 3.1, float32, little-endian
- **Values**: Original raw instrument values (not transformed)
- **Metadata**: Key fields from source FCS are preserved

### Gate JSON
```json
[
  {
    "id": "a1b2c3d4",
    "name": "Live",
    "x_channel": "FSC-A",
    "y_channel": "Live_Dead_Aqua",
    "parent_id": null,
    "gate_type": "polygon",
    "vertices": [[x1, y1], [x2, y2], ...],
    "color": "#00C8FF"
  },
  {
    "id": "e5f6g7h8",
    "name": "CD45+",
    "parent_id": "a1b2c3d4",
    "gate_type": "polygon",
    ...
  }
]
```

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+O` | Open FCS file |
| `Enter` | Close polygon gate |
| `Escape` | Cancel current polygon |
| `Delete` | Delete selected gate |

---

## Roadmap

- [ ] Ellipse gate type
- [ ] 1D histogram threshold gate
- [ ] Color-coded density plots (KDE)
- [ ] Batch apply gates to a folder of FCS files
- [ ] Gate statistics export to CSV
- [ ] FCS keyword editor

---

## License

MIT License — free for academic and commercial use.
