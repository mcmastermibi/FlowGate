# FlowGate — User Guide

**Open-source manual FCS gating for Python pipelines**
*A self-contained alternative to FlowJo, FCS Express, and OMIQ*

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Launching FlowGate](#3-launching-flowgate)
4. [Interface Layout](#4-interface-layout)
5. [Opening an FCS File](#5-opening-an-fcs-file)
6. [Setting Up the Plot](#6-setting-up-the-plot)
7. [Typical Gating Workflow — Live / CD45+ / CD3+](#7-typical-gating-workflow--live--cd45--cd3)
8. [Gate Types](#8-gate-types)
9. [Gate Hierarchy Panel](#9-gate-hierarchy-panel)
10. [Saving and Loading Gates](#10-saving-and-loading-gates)
11. [Exporting Gated Populations](#11-exporting-gated-populations)
12. [Batch Pipeline Integration](#12-batch-pipeline-integration)
13. [Python API](#13-python-api)
14. [Keyboard Shortcuts](#14-keyboard-shortcuts)
15. [Troubleshooting](#15-troubleshooting)
16. [Roadmap](#16-roadmap)

---

## 1. Overview

FlowGate is a desktop GUI application for manually gating FCS files. It is designed to replace commercial gating tools in research workflows where the downstream analysis is already Python-based.

**Key design principles:**

- Gates are drawn interactively on scatter plots and stored as portable JSON
- All gated populations are exported as standard FCS 3.1 files containing the **original raw (untransformed) values** — suitable for direct import into any downstream pipeline
- The transform (arcsinh, log, linear) is applied only for *display*; it does not alter exported data
- Sequential (hierarchical) gating is fully supported: each gate is applied within its parent population

**Supported FCS versions:** 2.0, 3.0, 3.1

---

## 2. Installation

### Recommended: Dedicated conda environment

```bash
conda create -n flowgate python=3.11 -y
conda activate flowgate
conda install -c conda-forge tk -y    # ensures tkinter is present on all platforms
pip install flowio numpy matplotlib scipy
```

> **Why a separate environment?**
> FlowGate's dependency on `flowio` pins numpy at a version that may conflict with
> other pipelines (e.g. ark-analysis). Keeping it isolated avoids these conflicts.

### Verify installation

```bash
python install_check.py
```

Expected output:
```
FlowGate — Dependency Check
========================================
  ✓  flowio           1.4.0
  ✓  numpy            1.26.4
  ✓  matplotlib       3.9.0
  ✓  scipy            1.13.0

  ✓  tkinter          8.6
```

### Install as a package (optional)

```bash
pip install -e .
```

This makes the `flowgate` command available system-wide in the active environment.

---

## 3. Launching FlowGate

```bash
# Option A — direct launcher (no install required)
python run_flowgate.py

# Option B — pre-load a specific FCS file
python run_flowgate.py path/to/my_file.fcs

# Option C — after pip install -e .
flowgate

# Option D — as a module
python -m flowgate.app
```

---

## 4. Interface Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  File   View                                           [menu bar]│
├────────────────┬────────────────────────────────────────────────┤
│ FILE           │                                                 │
│ [filename]     │                                                 │
│ [Open FCS]     │                                                 │
│────────────────│              SCATTER PLOT                       │
│ AXES           │                                                 │
│  X: [combo]   │         (events plotted here)                   │
│  Y: [combo]   │                                                 │
│  Transform ○  │                                                 │
│  Cofactor     │                                                 │
│────────────────│                                                 │
│ GATING TOOLS  │                                                 │
│ Parent: ...   ├────────────────────────────────────────────────┤
│ [✏ Polygon]   │  [matplotlib navigation toolbar]               │
│ [▭ Rectangle] │                                                 │
│ [✕ Cancel]    ├────────────────────────────────────────────────┤
│────────────────│  status bar                    N events loaded  │
│ GATE HIERARCHY│                                                 │
│  ▼ All Events │                                                 │
│    ▼ Live     │                                                 │
│      ▼ CD45+  │                                                 │
│        CD3+   │                                                 │
│────────────────│                                                 │
│ [⊕ Gate In]  │                                                 │
│ [✎ Rename]   │                                                 │
│ [✕ Delete]   │                                                 │
└────────────────┴────────────────────────────────────────────────┘
```

| Panel | Purpose |
|---|---|
| **Left panel** | File info, axis selection, transform controls, gating tools, gate hierarchy tree |
| **Scatter plot** | Interactive plot — draw gates here |
| **Navigation toolbar** | Pan, zoom, reset view (standard matplotlib toolbar) |
| **Status bar** | Live feedback on actions and gate statistics |

---

## 5. Opening an FCS File

- Menu: **File → Open FCS…** or press `Ctrl+O`
- Supported: `.fcs` files (FCS 2.0, 3.0, 3.1)
- After loading, the channel list populates the X and Y dropdowns automatically
- The status bar shows total event count and number of channels

### Demo file

A pre-generated synthetic PBMC file is included for testing:

```bash
# If not already present, generate it:
python examples/generate_demo_fcs.py examples/demo_PBMC.fcs
```

Channels: `FSC-A`, `SSC-A`, `Live_Dead_Aqua`, `CD45`, `CD3`, `CD19`, `CD56`, `CD14`, `HLA-DR`
Populations: ~30,000 events with realistic T cell, B cell, NK cell, monocyte, dead cell, and debris populations.

---

## 6. Setting Up the Plot

### Axes

Select channels from the **X** and **Y** dropdown menus in the left panel. The plot updates immediately.

### Transform

| Transform | When to use |
|---|---|
| `asinh` | Default — suitable for most flow cytometry and CyTOF/MIBI data |
| `log` | Older instruments or when data is strictly positive |
| `linear` | Scatter parameters (FSC, SSC) or when inspecting raw values |

**Cofactor** controls the linear range of the arcsinh transform:
- `150` — typical for conventional flow cytometry antibody channels
- `5` — typical for MIBI / CyTOF mass channels
- `50–500` — adjust based on your instrument and staining intensity

> The transform affects **display only**. Exported FCS files always contain original raw values.

### Display density

FlowGate subsamples up to **50,000 events** for rendering speed. All events are used for gate computation and export — subsampling only affects what is drawn on screen.

---

## 7. Typical Gating Workflow — Live / CD45+ / CD3+

This is the canonical sequential gating strategy for isolating T cells from a PBMC or bone marrow sample.

### Gate hierarchy being built

```
All Events
  └── Live          (FSC-A vs Live_Dead_Aqua  — low viability dye)
        └── CD45+   (FSC-A vs CD45            — CD45 high)
              └── CD3+  (CD45 vs CD3          — CD3 high)
```

---

### Step 1 — Open your FCS file

`File → Open FCS…` or `Ctrl+O`

---

### Step 2 — Gate Live cells

**Goal:** Exclude dead cells and debris using a viability dye (e.g. Live/Dead Aqua, 7-AAD, DAPI).

1. Set **X** = `FSC-A`, **Y** = `Live_Dead_Aqua`
2. Set **Transform** = `asinh`, **Cofactor** = `150`
3. Click **✏ Polygon** in the Gating Tools panel
4. Click around the live cell cluster (low viability dye, mid-to-high FSC):
   - Place vertices by clicking on the plot
   - Press `Enter` to close the polygon
5. When prompted, name the gate: **`Live`**
6. The gate appears as a coloured overlay; the hierarchy tree updates showing event count and % of parent

> **Tip:** Dead cells have high viability dye signal. Live cells cluster at low Y values.
> Debris appears at low FSC-A and can be excluded by keeping your gate above the debris cluster.

---

### Step 3 — Gate into the Live population

Before drawing the next gate, you must tell FlowGate that subsequent gates should be children of `Live`.

1. Click **`Live`** in the Gate Hierarchy panel to select it
2. Click **⊕ Gate In** (or double-click the gate in the tree)
3. The **Parent** label at the top of the Gating Tools panel will update to: `Parent: Live`

> The plot now displays only the events within the `Live` gate. This makes the next gate
> easier to draw on a cleaner population.

---

### Step 4 — Gate CD45+ cells

**Goal:** Select leukocytes (CD45+) from within the live gate, excluding remaining debris and red blood cells (CD45−).

1. Change **X** = `FSC-A`, **Y** = `CD45`
2. Click **✏ Polygon**
3. Draw a gate around the CD45-high cloud (upper portion of the plot)
4. Press `Enter` to close; name the gate: **`CD45+`**

> **Tip:** There is often a clear separation between CD45-negative cells/debris (bottom)
> and CD45-positive leukocytes (top). The gate boundary sits in the gap between these two populations.

---

### Step 5 — Gate into the CD45+ population

1. Click **`CD45+`** in the hierarchy tree
2. Click **⊕ Gate In**
3. Parent label updates to: `Parent: CD45+`

---

### Step 6 — Gate CD3+ T cells

**Goal:** Identify T cells (CD3+) within the CD45+ leukocyte gate.

1. Change **X** = `CD45`, **Y** = `CD3`
2. Click **✏ Polygon**
3. Draw a gate around the CD3-high population (right side / upper right)
4. Press `Enter`; name the gate: **`CD3+`**

The hierarchy tree now shows:

```
All Events    30,000   100%
  └── Live    18,000    60%
        └── CD45+   17,900   99.4%
              └── CD3+    8,500    47.5%
```

---

### Step 7 — Save the gate hierarchy

`File → Save Gate Hierarchy…`

Save as `my_gates.json`. This file can be reloaded onto any FCS file with matching channel names.

---

### Step 8 — Export gated populations

**Export a single gate:**
`File → Export Gated Population…`
(requires a gate to be selected in the tree)

**Export all gates at once:**
`File → Export All Gates…`
Select a destination folder. Each gate exports as:
`<original_filename>_<GateName>.fcs`

Exported files contain **raw (untransformed)** event data and are standard FCS 3.1 — compatible with flowio, fcsparser, FlowCytometryTools, and any other FCS reader.

---

### Complete workflow summary

| Step | X Axis | Y Axis | Action |
|---|---|---|---|
| 1 | `FSC-A` | `Live_Dead_Aqua` | Polygon gate → name `Live` |
| 2 | — | — | Select `Live` → **⊕ Gate In** |
| 3 | `FSC-A` | `CD45` | Polygon gate → name `CD45+` |
| 4 | — | — | Select `CD45+` → **⊕ Gate In** |
| 5 | `CD45` | `CD3` | Polygon gate → name `CD3+` |
| 6 | — | — | **File → Export All Gates** |

---

## 8. Gate Types

### Polygon gate (`✏ Polygon`)

- Click to place each vertex on the plot
- Press **`Enter`** to close the polygon and commit the gate
- Press **`Escape`** to cancel
- Best for: irregular population shapes, tight clusters, populations adjacent to debris

### Rectangle gate (`▭ Rectangle`)

- Click and drag to draw a rectangle
- Release the mouse button to commit
- Best for: clearly separated populations, quick rough gating, FSC/SSC scatter gating

> Both gate types operate in **display (transformed) space**. The boundary coordinates
> are stored in display space in the JSON, so gates are tied to the transform and cofactor
> they were drawn with. If you change the cofactor significantly, re-draw your gates.

---

## 9. Gate Hierarchy Panel

The tree on the left panel shows every gate and its relationship to parent gates.

| Column | Description |
|---|---|
| Gate name | Indented to show parent–child relationships |
| N | Number of events passing this gate (within its parent) |
| % Parent | Percentage of the parent population captured by this gate |

### Actions

| Action | Method |
|---|---|
| View a gate's population | Single-click the gate in the tree |
| Set as parent for next gate | Click **⊕ Gate In** or double-click |
| Rename a gate | Select → click **✎ Rename** |
| Delete a gate (and all children) | Select → click **✕ Delete** or press `Delete` |
| Return to All Events | Click `All Events` → **⊕ Gate In** |

---

## 10. Saving and Loading Gates

### Save

`File → Save Gate Hierarchy…`

Saves all gates as a `.json` file. The file stores gate shapes, channel assignments, parent relationships, names, and colours.

### Load

`File → Load Gate Hierarchy…`

Loads a `.json` gate file onto the currently open FCS. Gates will display and compute statistics immediately if the channel names match. Mismatched channel names will cause gates to be skipped silently (check the status bar).

### Portability

A gate JSON file can be applied to:
- Multiple FCS files from the same panel/instrument (via the GUI or batch script)
- Different samples in a cohort (all must have matching channel names)

---

## 11. Exporting Gated Populations

### Single gate export

1. Select a gate in the hierarchy tree
2. `File → Export Gated Population…`
3. Choose filename and location
4. A summary dialog confirms event count

### Batch export (all gates)

`File → Export All Gates…`

Prompts for a folder. Exports one FCS file per gate:
```
output_folder/
  my_sample_Live.fcs
  my_sample_CD45+.fcs
  my_sample_CD3+.fcs
```

### Exported FCS format

| Property | Value |
|---|---|
| FCS version | 3.1 |
| Data type | float32, little-endian |
| Values | Original raw instrument values (not transformed) |
| Channels | Same as source file |
| Metadata | Key fields preserved (`$CYT`, `$DATE`, `$SRC`, etc.) |

---

## 12. Batch Pipeline Integration

Once gates are saved from the GUI, apply them programmatically to an entire cohort using the included batch script:

```bash
conda activate flowgate

python examples/batch_gate.py \
  --gates my_gates.json \
  --input  ./raw_fcs_cohort/ \
  --output ./gated_output/ \
  --gate-names "Live" "CD45+" "CD3+"
```

**Options:**

| Flag | Description | Default |
|---|---|---|
| `--gates` | Path to `.json` gate file | required |
| `--input` | Folder of source FCS files | required |
| `--output` | Destination folder | required |
| `--gate-names` | Gate names to export (space-separated) | all gates |
| `--transform` | `asinh`, `log`, or `linear` | `asinh` |
| `--cofactor` | Cofactor for asinh | `150` |
| `--no-stats` | Skip `gate_stats.csv` output | off |

**Output:**

```
gated_output/
  sample01_Live.fcs
  sample01_CD45+.fcs
  sample01_CD3+.fcs
  sample02_Live.fcs
  ...
  gate_stats.csv        ← event counts and % for every file × gate combination
```

---

## 13. Python API

For programmatic use without the GUI — useful for automated pipelines or building gates from known cutoffs:

```python
from flowgate import read_fcs, write_fcs, apply_transform
from flowgate.gates import Gate, GateHierarchy

# ── Read ──────────────────────────────────────────────────────────
fcs = read_fcs("sample.fcs")
display = apply_transform(fcs["data"], transform="asinh", cofactor=150)
channels = fcs["channels"]

# ── Build hierarchy ───────────────────────────────────────────────
h = GateHierarchy()

g_live = Gate(
    name="Live",
    x_channel="FSC-A",
    y_channel="Live_Dead_Aqua",
    gate_type="rectangle",
    rect_bounds=(4.0, -1.0, 8.0, 3.0),   # (x0, y0, x1, y1) in display space
)
h.add_gate(g_live)

g_cd45 = Gate(
    name="CD45+",
    x_channel="FSC-A",
    y_channel="CD45",
    parent_id=g_live.id,
    gate_type="rectangle",
    rect_bounds=(4.0, 5.0, 8.0, 9.0),
)
h.add_gate(g_cd45)

g_cd3 = Gate(
    name="CD3+",
    x_channel="CD45",
    y_channel="CD3",
    parent_id=g_cd45.id,
    gate_type="rectangle",
    rect_bounds=(5.0, 5.0, 9.0, 9.0),
)
h.add_gate(g_cd3)

# ── Statistics ────────────────────────────────────────────────────
for gate in h.gates:
    s = h.get_gate_stats(gate.id, display, channels)
    print(f"{gate.name}: {s['count']:,} events ({s['pct_parent']:.1f}% of parent)")

# ── Export ────────────────────────────────────────────────────────
idxs = h.get_event_indices(g_cd3.id, display, channels)
write_fcs("CD3pos.fcs", fcs["data"][idxs], channels, fcs["metadata"])

# ── Save / load gates ─────────────────────────────────────────────
h.save("my_gates.json")

h2 = GateHierarchy()
h2.load("my_gates.json")
```

See `examples/python_api_example.py` for a fully annotated runnable example.

---

## 14. Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+O` | Open FCS file |
| `Enter` | Close and commit polygon gate |
| `Escape` | Cancel in-progress polygon gate |
| `Delete` | Delete selected gate (and all children) |

**Matplotlib navigation toolbar shortcuts** (standard):

| Key | Action |
|---|---|
| `f` | Toggle fullscreen |
| `h` / `r` | Reset zoom to home view |
| `p` | Pan mode |
| `o` | Zoom mode |
| `s` | Save plot as image |

---

## 15. Troubleshooting

### GUI does not open / tkinter error

```
ModuleNotFoundError: No module named '_tkinter'
```

**Linux:**
```bash
sudo apt install python3-tk
# or in conda:
conda install -c conda-forge tk
```

**Windows/macOS:** Re-install Python from python.org (includes tkinter) or use:
```bash
conda install -c conda-forge tk
```

---

### "Channel not found" when loading gates

Gates are matched to channels by **exact name**. If your FCS file uses `CD3` but the gate was drawn on a file with `CD3-FITC`, the gate will not apply.

**Fix:** Rename channels in your FCS export pipeline, or re-draw gates on a representative file from the new cohort.

---

### Plot is empty or shows no events after gating

This usually means the gate was drawn in the wrong region for the current data. Common causes:
- Cofactor mismatch (gate drawn with cofactor 150, reloaded on a MIBI file needing cofactor 5)
- Channel dynamic range is very different between samples

**Fix:** Use **✎ Rename** and **✕ Delete** to adjust gates, or redraw with the correct transform settings.

---

### FCS export contains 0 events

The gate bounds do not overlap the data in display space. Check:
1. Transform and cofactor settings match what was used when the gate was drawn
2. The correct parent gate is set (zero parent events → zero child events)

---

### Very large FCS files are slow to display

FlowGate subsamples to 50,000 events for rendering. If you need to adjust this, change `self.subsample` in `app.py`:

```python
self.subsample: int = 50000   # increase or decrease as needed
```

Gate computation and export always use all events regardless of this setting.

---

## 16. Roadmap

- [ ] Ellipse gate type
- [ ] 1D histogram threshold gate (for single-channel cutoffs)
- [ ] Density/KDE colour overlay on scatter plots
- [ ] Gate statistics export to CSV directly from GUI
- [ ] FCS channel renaming / keyword editor
- [ ] Batch gate application via GUI (folder drag-and-drop)
- [ ] Gate template library (save/share panel-specific gate sets)

---

## License

MIT License — free for academic and commercial use.

---

*FlowGate is not affiliated with FlowJo LLC, De Novo Software, or OMIQ Inc.*
