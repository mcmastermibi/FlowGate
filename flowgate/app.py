"""
app.py — FlowGate main GUI application
Uses tkinter + matplotlib for interactive gating
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.widgets import PolygonSelector, RectangleSelector
from matplotlib.patches import Polygon as MplPolygon, FancyArrowPatch
from matplotlib.lines import Line2D

from .fcs_io import read_fcs, write_fcs, apply_transform
from .gates import Gate, GateHierarchy

# ── Colour palette ──────────────────────────────────────────────
GATE_COLORS = [
    "#0077CC", "#E63946", "#2A9D5C", "#E07B00",
    "#7B2FBE", "#D4820A", "#0096A0", "#C1121F",
]

THEMES = {
    "dark": dict(
        BG_DARK="#0F1117", BG_PANEL="#1A1D26", BG_PLOT="#12151F",
        FG_TEXT="#E8EAF0", ACC_BLUE="#00C8FF", ACC_GREEN="#51E57B",
        ACC_RED="#FF6B6B", SEP_COLOR="#2A2D3A",
        PLOT_GRID="#2A2D3A", PLOT_DOT="#4DAACC", LABEL_MUTED="#666980",
    ),
    "light": dict(
        BG_DARK="#F0F2F5", BG_PANEL="#FFFFFF", BG_PLOT="#FFFFFF",
        FG_TEXT="#1A1D26", ACC_BLUE="#0077CC", ACC_GREEN="#2A9D5C",
        ACC_RED="#E63946", SEP_COLOR="#D0D3DC",
        PLOT_GRID="#E8E8E8", PLOT_DOT="#0077CC", LABEL_MUTED="#888A9A",
    ),
}

# Module-level colour variables — mutated by set_theme()
BG_DARK   = THEMES["dark"]["BG_DARK"]
BG_PANEL  = THEMES["dark"]["BG_PANEL"]
BG_PLOT   = THEMES["dark"]["BG_PLOT"]
FG_TEXT   = THEMES["dark"]["FG_TEXT"]
ACC_BLUE  = THEMES["dark"]["ACC_BLUE"]
ACC_GREEN = THEMES["dark"]["ACC_GREEN"]
ACC_RED   = THEMES["dark"]["ACC_RED"]
SEP_COLOR = THEMES["dark"]["SEP_COLOR"]




def _make_button(parent, text, command, bg, fg, font=("Helvetica", 9, "bold"),
                 relief=tk.FLAT, bd=0, padx=6, pady=4, width=16, cursor="hand2"):
    """
    macOS-safe coloured button.
    On macOS, tk.Button ignores bg/fg after ttk theme changes.
    Setting highlightbackground forces the colour to render.
    """
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
        font=font, relief=relief, bd=bd, padx=padx, pady=pady,
        width=width, cursor=cursor,
        highlightthickness=0, highlightbackground=bg,
    )
    return btn

class FlowGateApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FlowGate — Manual FCS Gating")
        self._theme_name = "dark"
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)

        # State
        self.fcs_data: dict | None = None           # current loaded FCS
        self.display_data: np.ndarray | None = None  # raw data copy
        self.hierarchy = GateHierarchy()
        self.current_gate_id: str | None = None     # selected gate in tree
        self.selected_parent_id: str | None = None  # parent for new gate

        # Folder / multi-file state
        self.folder_path: str | None = None
        self.fcs_files: list = []                   # list of full paths
        self.current_file_idx: int = 0
        # Per-file gate offsets: {filepath: {gate_id: (dx, dy)}}
        self.file_offsets: dict = {}
        # Per-file loaded data cache: {filepath: (fcs_data, display_data)}
        self._fcs_cache: dict = {}

        # Gate drag state
        self._drag_gate_id: str | None = None
        self._drag_start: tuple | None = None       # (x, y) in data coords
        self._drag_origin_offset: tuple = (0.0, 0.0)

        self.draw_mode: str = "none"   # "polygon" | "rectangle" | "none"
        self._poly_selector = None
        self._rect_selector = None
        self._in_progress_verts = []

        self.x_channel: str | None = None
        self.y_channel: str | None = None
        # Per-axis transform settings
        self.x_transform: str = "asinh"
        self.y_transform: str = "asinh"
        self.x_cofactor: float = 150.0
        self.y_cofactor: float = 150.0
        self.dot_alpha: float = 0.3
        self.dot_size: float = 1.0
        self.subsample: int = 50000

        self._color_cycle = 0
        self._gate_patches: dict = {}   # gate_id -> mpl artist

        # Saved transform state (persisted across theme rebuilds)
        self._saved_x_transform = "asinh"
        self._saved_y_transform = "asinh"
        self._saved_x_cofactor  = "150"
        self._saved_y_cofactor  = "150"

        self._build_ui()

    # ─────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Menu bar ──────────────────────────────────────────────
        menubar = tk.Menu(self.root, bg=BG_PANEL, fg=FG_TEXT,
                          activebackground=ACC_BLUE, activeforeground=BG_DARK)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False, bg=BG_PANEL, fg=FG_TEXT,
                            activebackground=ACC_BLUE, activeforeground=BG_DARK)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open FCS File…", command=self.open_fcs, accelerator="Ctrl+Shift+O")
        file_menu.add_command(label="Open FCS Folder…", command=self.open_folder, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save Gate Hierarchy…", command=self.save_gates)
        file_menu.add_command(label="Load Gate Hierarchy…", command=self.load_gates)
        file_menu.add_separator()
        file_menu.add_command(label="Export Current File — Selected Gate…", command=self.export_gated)
        file_menu.add_command(label="Export Current File — All Gates…", command=self.export_all_gates)
        file_menu.add_command(label="Export All Files — All Gates (Batch)…", command=self.export_batch)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.quit)

        view_menu = tk.Menu(menubar, tearoff=False, bg=BG_PANEL, fg=FG_TEXT,
                            activebackground=ACC_BLUE, activeforeground=BG_DARK)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Reset Zoom", command=self.reset_zoom)
        view_menu.add_command(label="Toggle Gate Labels", command=self.toggle_gate_labels)
        view_menu.add_separator()
        view_menu.add_command(label="Toggle Light / Dark Mode", command=self.toggle_theme)
        self._view_menu = view_menu

        self.root.bind("<Control-o>", lambda e: self.open_folder())
        self.root.bind("<Control-O>", lambda e: self.open_fcs())

        # ── Outer layout: left panel + plot area ──────────────────
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                               bg=SEP_COLOR, sashwidth=4, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True)
        self._paned = paned

        # ── Left panel ────────────────────────────────────────────
        left = tk.Frame(paned, bg=BG_PANEL, width=280)
        paned.add(left, minsize=220)
        self._left_frame = left

        self._build_left_panel(left)

        # ── Right: plot + bottom bar ───────────────────────────────
        right = tk.Frame(paned, bg=BG_DARK)
        paned.add(right, minsize=600)
        self._right_frame = right

        self._build_plot_area(right)
        self._build_bottom_bar(right)

    def _t(self):
        """Return current theme dict."""
        return THEMES[self._theme_name]

    def _lbl(self, parent, text, size=9, bold=False, color=None) -> tk.Label:
        t = self._t()
        fg = color if color is not None else t["FG_TEXT"]
        font = ("Helvetica", size, "bold" if bold else "normal")
        return tk.Label(parent, text=text, bg=t["BG_PANEL"], fg=fg, font=font)

    def _btn(self, parent, text, cmd, color=None, width=16) -> tk.Button:
        t = self._t()
        btn_bg = "#444455" if self._theme_name == "dark" else "#CCCCCC"
        bg = color if color is not None else btn_bg
        # Light text on dark/saturated buttons, dark text on light-grey buttons
        fg = "#333333"  # dark text on all neutral grey buttons
        return _make_button(parent, text=text, command=cmd,
                            bg=bg, fg=fg, width=width)

    def _build_left_panel(self, parent):
        th = self._t()   # current theme dict — read fresh each build
        bp    = th["BG_PANEL"]
        bd    = th["BG_DARK"]
        fg    = th["FG_TEXT"]
        ab    = th["ACC_BLUE"]
        ag    = th["ACC_GREEN"]
        sep   = th["SEP_COLOR"]
        muted = th["LABEL_MUTED"]
        entry_bg = th["BG_DARK"] if self._theme_name == "dark" else "#F0F2F5"

        def sep_line():
            tk.Frame(parent, bg=sep, height=1).pack(fill=tk.X, padx=10, pady=8)

        def frame(p=parent, **kw):
            return tk.Frame(p, bg=bp, **kw)

        def rb(parent_w, text, var, val, cmd):
            return tk.Radiobutton(parent_w, text=text, variable=var,
                                  value=val, bg=bp, fg=fg,
                                  selectcolor=entry_bg, activebackground=bp,
                                  font=("Helvetica", 8), command=cmd)

        def entry_w(parent_w, var, width=5):
            e = tk.Entry(parent_w, textvariable=var, width=width,
                         bg=entry_bg, fg=fg, insertbackground=fg,
                         font=("Helvetica", 8), relief=tk.FLAT,
                         highlightthickness=1,
                         highlightbackground=sep, highlightcolor=ab)
            return e

        # ── Folder / file browser ─────────────────────────────────
        sec = frame()
        sec.pack(fill=tk.X, padx=10, pady=(12, 4))
        tk.Label(sec, text="FOLDER", bg=bp, fg=muted,
                 font=("Helvetica", 8)).pack(anchor=tk.W)
        self.folder_label = tk.Label(sec, text="No folder loaded", bg=bp, fg=ab,
                                     font=("Helvetica", 9), wraplength=220, justify=tk.LEFT)
        self.folder_label.pack(anchor=tk.W)
        self._btn(sec, "Open FCS Folder…", self.open_folder, width=18).pack(anchor=tk.W, pady=(6, 0))

        # File list
        list_frame = tk.Frame(sec, bg=bp)
        list_frame.pack(fill=tk.X, pady=(6, 0))
        tk.Label(list_frame, text="FILES", bg=bp, fg=muted,
                 font=("Helvetica", 8)).pack(anchor=tk.W)

        lb_frame = tk.Frame(list_frame, bg=entry_bg)
        lb_frame.pack(fill=tk.X)
        self.file_listbox = tk.Listbox(
            lb_frame, height=6, bg=entry_bg, fg=fg,
            selectbackground=ab, selectforeground="#FFFFFF",
            font=("Helvetica", 8), relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground=sep,
            activestyle="none",
        )
        lb_scroll = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL,
                                   command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=lb_scroll.set)
        lb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.pack(fill=tk.X)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)

        # Nav buttons
        nav = tk.Frame(sec, bg=bp)
        nav.pack(fill=tk.X, pady=(4, 0))
        self._btn(nav, "◀ Prev", self.prev_file, width=7).pack(side=tk.LEFT, padx=(0, 4))
        self._btn(nav, "Next ▶", self.next_file, width=7).pack(side=tk.LEFT)
        self.file_label = tk.Label(nav, text="", bg=bp, fg=muted,
                                   font=("Helvetica", 8))
        self.file_label.pack(side=tk.RIGHT)

        sep_line()

        # ── Axes ───────────────────────────────────────────────────
        sec2 = frame()
        sec2.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(sec2, text="AXES", bg=bp, fg=muted,
                 font=("Helvetica", 8)).pack(anchor=tk.W)

        # X axis
        row_x = frame(sec2)
        row_x.pack(fill=tk.X, pady=2)
        tk.Label(row_x, text="X:", bg=bp, fg=fg, font=("Helvetica", 9)).pack(side=tk.LEFT)
        self.x_combo = ttk.Combobox(row_x, state="readonly", width=17, font=("Helvetica", 9))
        self.x_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.x_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_plot())

        row_xt = frame(sec2)
        row_xt.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row_xt, text="  ", bg=bp).pack(side=tk.LEFT)
        self.x_transform_var = tk.StringVar(value=self._saved_x_transform)
        for val in ("asinh", "linear"):
            rb(row_xt, val, self.x_transform_var, val, self.on_transform_change).pack(side=tk.LEFT, padx=1)
        tk.Label(row_xt, text="cf:", bg=bp, fg=muted, font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(6, 2))
        self.x_cofactor_var = tk.StringVar(value=self._saved_x_cofactor)
        ex = entry_w(row_xt, self.x_cofactor_var)
        ex.pack(side=tk.LEFT)
        ex.bind("<Return>", lambda e: self.on_transform_change())

        # Y axis
        row_y = frame(sec2)
        row_y.pack(fill=tk.X, pady=2)
        tk.Label(row_y, text="Y:", bg=bp, fg=fg, font=("Helvetica", 9)).pack(side=tk.LEFT)
        self.y_combo = ttk.Combobox(row_y, state="readonly", width=17, font=("Helvetica", 9))
        self.y_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.y_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_plot())

        row_yt = frame(sec2)
        row_yt.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row_yt, text="  ", bg=bp).pack(side=tk.LEFT)
        self.y_transform_var = tk.StringVar(value=self._saved_y_transform)
        for val in ("asinh", "linear"):
            rb(row_yt, val, self.y_transform_var, val, self.on_transform_change).pack(side=tk.LEFT, padx=1)
        tk.Label(row_yt, text="cf:", bg=bp, fg=muted, font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(6, 2))
        self.y_cofactor_var = tk.StringVar(value=self._saved_y_cofactor)
        ey = entry_w(row_yt, self.y_cofactor_var)
        ey.pack(side=tk.LEFT)
        ey.bind("<Return>", lambda e: self.on_transform_change())

        sep_line()

        # ── Gating tools ───────────────────────────────────────────
        sec3 = frame()
        sec3.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(sec3, text="GATING TOOLS", bg=bp, fg=muted,
                 font=("Helvetica", 8)).pack(anchor=tk.W, pady=(0, 6))

        self.parent_label = tk.Label(sec3, text="Parent: All Events",
                                     bg=bp, fg=ag, font=("Helvetica", 8))
        self.parent_label.pack(anchor=tk.W, pady=(0, 4))

        btn_row = frame(sec3)
        btn_row.pack(fill=tk.X)
        self.poly_btn = self._btn(btn_row, "✏ Polygon", self.start_polygon_gate, width=11)
        self.poly_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.rect_btn = self._btn(btn_row, "▭ Rectangle", self.start_rectangle_gate, width=11)
        self.rect_btn.pack(side=tk.LEFT)

        cancel_bg = "#CCCCCC" if self._theme_name == "light" else "#444455"
        cancel_fg = "#333333"  # always dark text — these buttons have light backgrounds
        _make_button(sec3, text="✕  Cancel Draw", command=self.cancel_draw,
                     bg=cancel_bg, fg=cancel_fg, width=16).pack(anchor=tk.W, pady=(4, 0))

        tk.Frame(sec3, bg=sep, height=1).pack(fill=tk.X, pady=(8, 4))
        tk.Label(sec3, text="PER-FILE ADJUSTMENT", bg=bp, fg=muted,
                 font=("Helvetica", 8)).pack(anchor=tk.W, pady=(0, 4))
        move_bg = "#444455" if self._theme_name == "dark" else "#CCCCCC"
        move_fg = "#333333"
        self.move_btn = _make_button(
            sec3, text="✥  Move Gate (this file)", command=self.start_move_gate,
            bg=move_bg, fg=move_fg, width=22)
        self.move_btn.pack(anchor=tk.W)
        self.move_label = tk.Label(sec3, text="Select a gate, then drag it",
                                   bg=bp, fg=muted, font=("Helvetica", 8),
                                   wraplength=220, justify=tk.LEFT)
        self.move_label.pack(anchor=tk.W, pady=(2, 0))
        self._btn(sec3, "↺  Reset Gate Position", self.reset_gate_offset,
                  color=cancel_bg, width=22).pack(anchor=tk.W, pady=(4, 0))
        # move_btn fg already set correctly above

        sep_line()

        # ── Gate hierarchy tree ────────────────────────────────────
        sec4 = tk.Frame(parent, bg=bp)
        sec4.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        tk.Label(sec4, text="GATE HIERARCHY", bg=bp, fg=muted,
                 font=("Helvetica", 8)).pack(anchor=tk.W)

        tree_bg = bd if self._theme_name == "dark" else "#F5F7FA"
        tree_frame = tk.Frame(sec4, bg=tree_bg)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Flow.Treeview",
                        background=tree_bg, foreground=fg,
                        fieldbackground=tree_bg, font=("Helvetica", 9),
                        rowheight=22)
        style.configure("Flow.Treeview.Heading",
                        background=bp, foreground=muted,
                        font=("Helvetica", 8, "bold"))
        sel_bg = "#1E3A5F" if self._theme_name == "dark" else "#CCE4FF"
        style.map("Flow.Treeview",
                  background=[("selected", sel_bg)],
                  foreground=[("selected", ab)])

        self.gate_tree = ttk.Treeview(tree_frame, style="Flow.Treeview",
                                       columns=("count", "pct"), show="tree headings",
                                       selectmode="browse")
        self.gate_tree.heading("#0", text="Gate")
        self.gate_tree.heading("count", text="N")
        self.gate_tree.heading("pct", text="% Parent")
        self.gate_tree.column("#0", width=130)
        self.gate_tree.column("count", width=60, anchor=tk.E)
        self.gate_tree.column("pct", width=70, anchor=tk.E)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.gate_tree.yview)
        self.gate_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.gate_tree.pack(fill=tk.BOTH, expand=True)

        self.gate_tree.bind("<<TreeviewSelect>>", self.on_gate_select)
        self.gate_tree.bind("<Double-1>", self.on_gate_double_click)
        self.gate_tree.bind("<Delete>", lambda e: self.delete_selected_gate())

        # Gate action buttons
        gbtn = tk.Frame(sec4, bg=bp)
        gbtn.pack(fill=tk.X, pady=(6, 0))
        self._btn(gbtn, "⊕ Gate In", self.gate_into_selected,
                  color=ag, width=9).pack(side=tk.LEFT, padx=(0, 4))
        rename_bg = "#CCCCCC" if self._theme_name == "light" else "#555566"
        rename_fg = "#333333"  # always dark text — these buttons have light backgrounds
        _make_button(gbtn, text="✎ Rename", command=self.rename_gate,
                     bg=rename_bg, fg=rename_fg, width=9).pack(side=tk.LEFT, padx=(0, 4))
        self._btn(gbtn, "✕ Delete", self.delete_selected_gate,
                  color=th["ACC_RED"], width=9).pack(side=tk.LEFT)

    def _build_plot_area(self, parent):
        plot_frame = tk.Frame(parent, bg=BG_PLOT)
        plot_frame.pack(fill=tk.BOTH, expand=True)

        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.fig.patch.set_facecolor(BG_PLOT)
        self.ax.set_facecolor(BG_PLOT)
        self.ax.tick_params(colors=FG_TEXT)
        for spine in self.ax.spines.values():
            spine.set_color(SEP_COLOR)
        self.ax.grid(True, color=SEP_COLOR, linewidth=0.4, alpha=0.6)

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar_frame = tk.Frame(plot_frame, bg=BG_PANEL)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.config(bg=BG_PANEL)
        self.toolbar.update()

        self._draw_placeholder()

    def _build_bottom_bar(self, parent):
        bar = tk.Frame(parent, bg=BG_PANEL, height=28)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        self._bottom_bar = bar

        th2 = self._t()
        self.status_var = tk.StringVar(value="Ready. Open an FCS file to begin.")
        tk.Label(bar, textvariable=self.status_var, bg=th2["BG_PANEL"], fg=th2["LABEL_MUTED"],
                 font=("Helvetica", 8), anchor=tk.W).pack(side=tk.LEFT, padx=10)

        self.event_count_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.event_count_var, bg=th2["BG_PANEL"], fg=th2["ACC_BLUE"],
                 font=("Helvetica", 8, "bold"), anchor=tk.E).pack(side=tk.RIGHT, padx=10)

    # ─────────────────────────────────────────────────────────────
    # File I/O
    # ─────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────
    # Folder / multi-file management
    # ─────────────────────────────────────────────────────────────

    def open_folder(self):
        """Open a folder of FCS files."""
        folder = filedialog.askdirectory(title="Open FCS Folder")
        if not folder:
            return
        fcs_files = sorted([
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith(".fcs")
        ])
        if not fcs_files:
            messagebox.showinfo("No FCS files", "No .fcs files found in that folder.")
            return
        self.folder_path = folder
        self.fcs_files = fcs_files
        self.current_file_idx = 0
        self._fcs_cache = {}
        self.file_offsets = {}
        self.hierarchy = GateHierarchy()
        self.current_gate_id = None
        self.selected_parent_id = None
        self._color_cycle = 0

        # Update file listbox
        self.file_listbox.delete(0, tk.END)
        for f in fcs_files:
            self.file_listbox.insert(tk.END, os.path.basename(f))
        self.file_listbox.selection_set(0)

        folder_name = os.path.basename(folder)
        self.folder_label.config(text=folder_name)
        self._load_file_by_idx(0)

    def _load_file_by_idx(self, idx: int):
        """Load the FCS file at index idx."""
        if not self.fcs_files or idx < 0 or idx >= len(self.fcs_files):
            return
        self.current_file_idx = idx
        path = self.fcs_files[idx]

        # Use cache if available
        if path in self._fcs_cache:
            self.fcs_data, self.display_data = self._fcs_cache[path]
        else:
            try:
                self.fcs_data = read_fcs(path)
                self.display_data = self.fcs_data["data"].copy().astype(float)
                self._fcs_cache[path] = (self.fcs_data, self.display_data)
            except Exception as exc:
                messagebox.showerror("Error loading FCS", str(exc))
                return

        # Ensure offset entry exists for this file
        if path not in self.file_offsets:
            self.file_offsets[path] = {}

        # Update channel combos
        chans = self.fcs_data["channels"]
        self.x_combo["values"] = chans
        self.y_combo["values"] = chans
        if self.x_channel and self.x_channel in chans:
            self.x_combo.set(self.x_channel)
        elif chans:
            self.x_combo.current(0)
            self.x_channel = chans[0]
        if self.y_channel and self.y_channel in chans:
            self.y_combo.set(self.y_channel)
        elif len(chans) > 1:
            self.y_combo.current(1)
            self.y_channel = chans[1]

        n = len(self.fcs_data["data"])
        fname = self.fcs_data["filename"]
        self.file_label.config(text=f"{idx+1}/{len(self.fcs_files)}")
        self.event_count_var.set(f"{n:,} events")
        self.status(f"{fname}  |  {n:,} events  |  {len(chans)} channels")

        # Highlight listbox
        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(idx)
        self.file_listbox.see(idx)

        self._refresh_gate_tree()
        self.refresh_plot()

    def on_file_select(self, event):
        sel = self.file_listbox.curselection()
        if sel:
            self._load_file_by_idx(sel[0])

    def prev_file(self):
        if self.fcs_files:
            self._load_file_by_idx(max(0, self.current_file_idx - 1))

    def next_file(self):
        if self.fcs_files:
            self._load_file_by_idx(min(len(self.fcs_files) - 1,
                                       self.current_file_idx + 1))

    def _current_offsets(self) -> dict:
        """Return the offset dict for the current file."""
        if not self.fcs_files:
            return {}
        path = self.fcs_files[self.current_file_idx]
        return self.file_offsets.get(path, {})

    # ─────────────────────────────────────────────────────────────
    # Gate drag / move (per-file)
    # ─────────────────────────────────────────────────────────────

    def start_move_gate(self):
        """Enable drag mode for the selected gate."""
        if not self.current_gate_id:
            messagebox.showinfo("Move Gate",
                "Select a gate in the hierarchy first, then click Move Gate.")
            return
        self._cancel_selectors()
        self.draw_mode = "move"
        gate = self.hierarchy.get_gate(self.current_gate_id)
        self.move_label.config(text=f"Drag '{gate.name}' to reposition for this file")
        self.status(f"Drag mode: click and drag '{gate.name}' on the plot.")
        # Connect drag events
        self._drag_cid_press   = self.canvas.mpl_connect("button_press_event",   self._on_drag_press)
        self._drag_cid_motion  = self.canvas.mpl_connect("motion_notify_event",  self._on_drag_motion)
        self._drag_cid_release = self.canvas.mpl_connect("button_release_event", self._on_drag_release)

    def _stop_drag(self):
        for attr in ("_drag_cid_press", "_drag_cid_motion", "_drag_cid_release"):
            cid = getattr(self, attr, None)
            if cid is not None:
                try:
                    self.canvas.mpl_disconnect(cid)
                except Exception:
                    pass
                setattr(self, attr, None)
        self._drag_gate_id = None
        self._drag_start = None
        self.draw_mode = "none"
        try:
            self.move_label.config(text="Select a gate, then drag it")
        except Exception:
            pass

    def _on_drag_press(self, event):
        if event.inaxes != self.ax or not self.current_gate_id:
            return
        self._drag_gate_id = self.current_gate_id
        self._drag_start = (event.xdata, event.ydata)
        path = self.fcs_files[self.current_file_idx] if self.fcs_files else None
        if path:
            ox, oy = self.file_offsets.get(path, {}).get(self._drag_gate_id, (0.0, 0.0))
            self._drag_origin_offset = (ox, oy)

    def _on_drag_motion(self, event):
        if event.inaxes != self.ax or not self._drag_gate_id or not self._drag_start:
            return
        dx = event.xdata - self._drag_start[0]
        dy = event.ydata - self._drag_start[1]
        ox, oy = self._drag_origin_offset
        path = self.fcs_files[self.current_file_idx] if self.fcs_files else None
        if path:
            if path not in self.file_offsets:
                self.file_offsets[path] = {}
            self.file_offsets[path][self._drag_gate_id] = (ox + dx, oy + dy)
        self.refresh_plot()

    def _on_drag_release(self, event):
        if self._drag_gate_id:
            path = self.fcs_files[self.current_file_idx] if self.fcs_files else None
            if path:
                off = self.file_offsets.get(path, {}).get(self._drag_gate_id, (0, 0))
                self.status(f"Gate moved — offset ({off[0]:.3f}, {off[1]:.3f}). "
                            "Click Move Gate again to continue adjusting.")
            self._refresh_gate_tree()
        self._stop_drag()

    def reset_gate_offset(self):
        """Reset the current gate's position for the current file."""
        if not self.current_gate_id or not self.fcs_files:
            return
        path = self.fcs_files[self.current_file_idx]
        if path in self.file_offsets and self.current_gate_id in self.file_offsets[path]:
            del self.file_offsets[path][self.current_gate_id]
        gate = self.hierarchy.get_gate(self.current_gate_id)
        self.status(f"Gate '{gate.name}' position reset for this file.")
        self._refresh_gate_tree()
        self.refresh_plot()

    # ─────────────────────────────────────────────────────────────
    # Batch export
    # ─────────────────────────────────────────────────────────────

    def export_batch(self):
        """Export all gates for all files in the folder."""
        if not self.fcs_files or not self.hierarchy.gates:
            messagebox.showinfo("Batch Export", "Open a folder and create gates first.")
            return
        out_dir = filedialog.askdirectory(title="Select batch export folder")
        if not out_dir:
            return
        os.makedirs(out_dir, exist_ok=True)
        total_exported = 0
        errors = []
        for file_path in self.fcs_files:
            stem = os.path.splitext(os.path.basename(file_path))[0]
            # Load data (use cache)
            if file_path in self._fcs_cache:
                fcs, raw = self._fcs_cache[file_path]
            else:
                try:
                    fcs = read_fcs(file_path)
                    raw = fcs["data"].copy().astype(float)
                    self._fcs_cache[file_path] = (fcs, raw)
                except Exception as e:
                    errors.append(f"{os.path.basename(file_path)}: {e}")
                    continue
            offsets = self.file_offsets.get(file_path, {})
            chans = fcs["channels"]
            # Build display matrix for this file
            disp = self._build_display_matrix(raw, chans)
            for gate in self.hierarchy.gates:
                idxs = self.hierarchy.get_event_indices(gate.id, disp, chans, offsets)
                raw_gated = fcs["data"][idxs]
                safe_name = gate.name.replace(" ", "_").replace("/", "-")
                out_name = f"{stem}_{safe_name}.fcs"
                out_path = os.path.join(out_dir, out_name)
                write_fcs(out_path, raw_gated, chans, fcs["metadata"])
                total_exported += 1
        msg = f"Batch export complete.\n{total_exported} files exported to:\n{out_dir}"
        if errors:
            msg += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors)
        messagebox.showinfo("Batch Export", msg)
        self.status(f"Batch export: {total_exported} files → {out_dir}")

    def _build_display_matrix(self, raw: np.ndarray, chans: list) -> np.ndarray:
        """Build display matrix applying gate-stored transforms to relevant channels."""
        mat = raw.copy()
        ch_settings = {}
        for gate in self.hierarchy.gates:
            if gate.x_channel:
                ch_settings[gate.x_channel] = (gate.x_transform, gate.x_cofactor)
            if gate.y_channel:
                ch_settings[gate.y_channel] = (gate.y_transform, gate.y_cofactor)
        for ch_name, (transform, cofactor) in ch_settings.items():
            if ch_name in chans:
                ci = chans.index(ch_name)
                mat[:, ci] = apply_transform(
                    mat[:, ci].reshape(-1, 1), transform=transform, cofactor=cofactor).ravel()
        return mat

    def _load_fcs_path(self, path: str):
        """Load an FCS file from a direct path (used by CLI launcher)."""
        try:
            self.status("Loading FCS…")
            self.fcs_data = read_fcs(path)
            self._compute_display_data()
            self.file_label.config(text=self.fcs_data["filename"])
            chans = self.fcs_data["channels"]
            self.x_combo["values"] = chans
            self.y_combo["values"] = chans
            self.x_combo.current(min(0, len(chans) - 1))
            self.y_combo.current(min(1, len(chans) - 1))
            self.hierarchy = GateHierarchy()
            self._refresh_gate_tree()
            n = len(self.fcs_data["data"])
            self.event_count_var.set(f"{n:,} events loaded")
            self.status(f"Loaded: {self.fcs_data['filename']}  |  {n:,} events  |  {len(chans)} channels")
            self.refresh_plot()
        except Exception as exc:
            messagebox.showerror("Error loading FCS", str(exc))

    def open_fcs(self):
        path = filedialog.askopenfilename(
            title="Open FCS File",
            filetypes=[("FCS files", "*.fcs"), ("All files", "*.*")],
        )
        if not path:
            return
        # Treat as a single-file folder so the file list and nav work consistently
        self.folder_path = os.path.dirname(path)
        self.fcs_files = [path]
        self.current_file_idx = 0
        self._fcs_cache = {}
        self.file_offsets = {}
        self.hierarchy = GateHierarchy()
        self.current_gate_id = None
        self.selected_parent_id = None
        self._color_cycle = 0

        self.file_listbox.delete(0, tk.END)
        self.file_listbox.insert(tk.END, os.path.basename(path))
        self.file_listbox.selection_set(0)
        self.folder_label.config(text=os.path.basename(self.folder_path))
        self._load_file_by_idx(0)

    def save_gates(self):
        if not self.hierarchy.gates:
            messagebox.showinfo("No gates", "No gates to save.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Gate files", "*.json")],
            title="Save Gate Hierarchy",
        )
        if path:
            self.hierarchy.save(path)
            self.status(f"Gates saved → {os.path.basename(path)}")

    def load_gates(self):
        path = filedialog.askopenfilename(
            filetypes=[("Gate files", "*.json")],
            title="Load Gate Hierarchy",
        )
        if path:
            self.hierarchy.load(path)
            self._refresh_gate_tree()
            self.refresh_plot()
            self.status(f"Gates loaded from {os.path.basename(path)}")

    def export_gated(self):
        if not self.fcs_data or not self.current_gate_id:
            messagebox.showinfo("Export", "Select a gate in the hierarchy first.")
            return
        gate = self.hierarchy.get_gate(self.current_gate_id)
        path = filedialog.asksaveasfilename(
            defaultextension=".fcs",
            initialfile=f"{gate.name.replace(' ', '_')}_gated.fcs",
            filetypes=[("FCS files", "*.fcs")],
            title="Export Gated Population",
        )
        if path:
            self._do_export(self.current_gate_id, path)

    def export_all_gates(self):
        if not self.fcs_data or not self.hierarchy.gates:
            messagebox.showinfo("Export", "No gates to export.")
            return
        folder = filedialog.askdirectory(title="Select export folder")
        if not folder:
            return
        basename = os.path.splitext(self.fcs_data["filename"])[0]
        for gate in self.hierarchy.gates:
            fname = f"{basename}_{gate.name.replace(' ', '_')}.fcs"
            self._do_export(gate.id, os.path.join(folder, fname))
        self.status(f"Exported {len(self.hierarchy.gates)} gate populations → {folder}")

    def _do_export(self, gate_id: str, path: str):
        gate = self.hierarchy.get_gate(gate_id)
        offsets = self._current_offsets()
        idxs = self.hierarchy.get_event_indices(
            gate_id, self._get_display_matrix(), self.fcs_data["channels"], offsets
        )
        raw_gated = self.fcs_data["data"][idxs]
        write_fcs(path, raw_gated, self.fcs_data["channels"], self.fcs_data["metadata"])
        n = len(idxs)
        self.status(f"Exported '{gate.name}'  ({n:,} events) → {os.path.basename(path)}")
        messagebox.showinfo("Export complete",
                            f"Gate '{gate.name}'\n{n:,} events exported to:\n{path}")

    # ─────────────────────────────────────────────────────────────
    # Transforms
    # ─────────────────────────────────────────────────────────────

    def _compute_display_data(self):
        """
        Build display_data: a copy of raw data with per-channel transforms applied.
        Each channel is transformed independently using the axis-specific settings
        that were active when gating occurred.  For gate computation we need a
        consistent display_data array — we use the CURRENT x/y transform settings
        applied to the currently selected x/y channels, and raw values for all others.
        """
        if self.fcs_data is None:
            return
        # Store raw; per-axis transform applied in get_display_xy()
        self.display_data = self.fcs_data["data"].copy().astype(float)

    def get_display_xy(self):
        """Return transformed x and y arrays for the currently selected channels."""
        if self.fcs_data is None or self.display_data is None:
            return None, None
        chans = self.fcs_data["channels"]
        x_name = self.x_combo.get()
        y_name = self.y_combo.get()
        if x_name not in chans or y_name not in chans:
            return None, None
        xi = chans.index(x_name)
        yi = chans.index(y_name)
        try:
            x_cf = float(self.x_cofactor_var.get())
        except ValueError:
            x_cf = 150.0
        try:
            y_cf = float(self.y_cofactor_var.get())
        except ValueError:
            y_cf = 150.0
        x_t = self.x_transform_var.get()
        y_t = self.y_transform_var.get()
        x_raw = self.display_data[:, xi]
        y_raw = self.display_data[:, yi]
        x_disp = apply_transform(x_raw.reshape(-1, 1), transform=x_t, cofactor=x_cf).ravel()
        y_disp = apply_transform(y_raw.reshape(-1, 1), transform=y_t, cofactor=y_cf).ravel()
        return x_disp, y_disp

    def _get_display_matrix(self):
        """Build display matrix for the current file using gate-stored transforms
        plus the current UI axis settings for any channels not already covered."""
        if self.fcs_data is None or self.display_data is None:
            return self.display_data
        chans = self.fcs_data["channels"]
        mat = self._build_display_matrix(self.display_data, chans)

        # Collect channels already transformed by _build_display_matrix
        already_transformed = set()
        for gate in self.hierarchy.gates:
            if gate.x_channel:
                already_transformed.add(gate.x_channel)
            if gate.y_channel:
                already_transformed.add(gate.y_channel)

        # Only apply current UI transform to channels NOT already handled above
        x_name = self.x_combo.get()
        y_name = self.y_combo.get()
        try:
            x_cf = float(self.x_cofactor_var.get())
        except ValueError:
            x_cf = 150.0
        try:
            y_cf = float(self.y_cofactor_var.get())
        except ValueError:
            y_cf = 150.0
        if x_name and x_name in chans and x_name not in already_transformed:
            ci = chans.index(x_name)
            mat[:, ci] = apply_transform(mat[:, ci].reshape(-1, 1),
                transform=self.x_transform_var.get(), cofactor=x_cf).ravel()
        if y_name and y_name in chans and y_name not in already_transformed:
            ci = chans.index(y_name)
            mat[:, ci] = apply_transform(mat[:, ci].reshape(-1, 1),
                transform=self.y_transform_var.get(), cofactor=y_cf).ravel()
        return mat

    def on_transform_change(self, *_):
        try:
            self._saved_x_transform = self.x_transform_var.get()
            self._saved_y_transform = self.y_transform_var.get()
            self._saved_x_cofactor  = self.x_cofactor_var.get()
            self._saved_y_cofactor  = self.y_cofactor_var.get()
        except Exception:
            pass
        self._compute_display_data()
        self.refresh_plot()

    # ─────────────────────────────────────────────────────────────
    # Plot
    # ─────────────────────────────────────────────────────────────

    def _draw_placeholder(self):
        t = THEMES[self._theme_name]
        self.fig.patch.set_facecolor(t["BG_PLOT"])
        self.ax.clear()
        self.ax.set_facecolor(t["BG_PLOT"])
        self.ax.text(0.5, 0.5, "Open an FCS file to begin",
                     ha="center", va="center", transform=self.ax.transAxes,
                     color=t["LABEL_MUTED"], fontsize=14, fontstyle="italic")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.canvas.draw_idle()

    def refresh_plot(self):
        if self.display_data is None:
            return

        chans = self.fcs_data["channels"]
        x_name = self.x_combo.get()
        y_name = self.y_combo.get()
        if x_name not in chans or y_name not in chans:
            return

        self.x_channel = x_name
        self.y_channel = y_name

        # Build the full display matrix for gate masking
        disp_mat = self._get_display_matrix()

        # Determine which events to show (current gate or all)
        offsets = self._current_offsets()
        if self.current_gate_id:
            mask = self.hierarchy.compute_mask(
                self.current_gate_id, disp_mat, chans, offsets)
        else:
            mask = np.ones(len(disp_mat), dtype=bool)

        # Get per-axis transformed coords for the scatter plot
        x_disp, y_disp = self.get_display_xy()
        xv = x_disp[mask]
        yv = y_disp[mask]
        n = len(xv)
        if n > self.subsample:
            idx = np.random.choice(n, self.subsample, replace=False)
            xv = xv[idx]
            yv = yv[idx]

        t = THEMES[self._theme_name]
        bg_plot  = t["BG_PLOT"]
        fg_text  = t["FG_TEXT"]
        sep      = t["SEP_COLOR"]
        plot_dot = t["PLOT_DOT"]
        grid_col = t["PLOT_GRID"]

        self.fig.patch.set_facecolor(bg_plot)
        self.ax.clear()
        self.ax.set_facecolor(bg_plot)
        self.ax.tick_params(colors=fg_text, labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color(sep)
        self.ax.grid(True, color=grid_col, linewidth=0.5, alpha=0.8)

        self.ax.scatter(
            xv, yv,
            s=self.dot_size, alpha=self.dot_alpha,
            c=plot_dot, rasterized=True, linewidths=0,
        )
        # Axis labels include transform info
        x_t = self.x_transform_var.get()
        y_t = self.y_transform_var.get()
        try:
            x_cf = float(self.x_cofactor_var.get())
        except ValueError:
            x_cf = 150.0
        try:
            y_cf = float(self.y_cofactor_var.get())
        except ValueError:
            y_cf = 150.0
        x_label = f"{x_name}  [{x_t}" + (f", cf={int(x_cf)}" if x_t == "asinh" else "") + "]"
        y_label = f"{y_name}  [{y_t}" + (f", cf={int(y_cf)}" if y_t == "asinh" else "") + "]"
        # labels set below with theme colour

        title = "All Events"
        if self.current_gate_id:
            g = self.hierarchy.get_gate(self.current_gate_id)
            title = f"Population: {g.name}"
        self.ax.set_title(title, color=t["ACC_BLUE"], fontsize=10, pad=6)
        self.ax.set_xlabel(x_label, color=fg_text, fontsize=9)
        self.ax.set_ylabel(y_label, color=fg_text, fontsize=9)

        # Draw gate overlays visible for current axes
        self._gate_patches = {}
        for gate in self.hierarchy.gates:
            if gate.x_channel == x_name and gate.y_channel == y_name:
                self._draw_gate_overlay(gate)

        self.canvas.draw_idle()

    def _draw_gate_overlay(self, gate: Gate):
        offsets = self._current_offsets()
        dx, dy = offsets.get(gate.id, (0.0, 0.0))
        plot_bg = THEMES[self._theme_name]["BG_PLOT"]
        # Show a nudge indicator if offset is non-zero
        has_offset = abs(dx) > 1e-9 or abs(dy) > 1e-9
        lw = 1.8 if (gate.id == self.current_gate_id) else 1.2
        alpha_fill = 0.20 if (gate.id == self.current_gate_id) else 0.12

        if gate.gate_type == "polygon" and len(gate.vertices) >= 3:
            shifted = gate.get_offset_vertices(dx, dy)
            verts = shifted + [shifted[0]]
            xs, ys = zip(*verts)
            patch = self.ax.fill(xs, ys, alpha=alpha_fill, color=gate.color)[0]
            line, = self.ax.plot(xs, ys, color=gate.color, lw=lw, alpha=0.9,
                                 linestyle="--" if has_offset else "-")
            cx = np.mean([v[0] for v in shifted])
            cy = np.mean([v[1] for v in shifted])
            label = gate.name + (" ⤢" if has_offset else "")
            self.ax.text(cx, cy, label, color=gate.color,
                         fontsize=7, ha="center", va="center",
                         bbox=dict(boxstyle="round,pad=0.2",
                                   fc=plot_bg, ec=gate.color, lw=0.6, alpha=0.9))
            self._gate_patches[gate.id] = (patch, line)

        elif gate.gate_type == "rectangle" and gate.rect_bounds:
            x0, y0, x1, y1 = gate.get_offset_rect(dx, dy)
            w, h = abs(x1 - x0), abs(y1 - y0)
            rect = mpatches.FancyBboxPatch(
                (min(x0, x1), min(y0, y1)), w, h,
                linewidth=lw, edgecolor=gate.color,
                facecolor=gate.color, alpha=alpha_fill,
                boxstyle="square,pad=0",
                linestyle="--" if has_offset else "-",
            )
            self.ax.add_patch(rect)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            label = gate.name + (" ⤢" if has_offset else "")
            self.ax.text(cx, cy, label, color=gate.color,
                         fontsize=7, ha="center", va="center",
                         bbox=dict(boxstyle="round,pad=0.2",
                                   fc=plot_bg, ec=gate.color, lw=0.6, alpha=0.9))
            self._gate_patches[gate.id] = rect

    # ─────────────────────────────────────────────────────────────
    # Gate drawing
    # ─────────────────────────────────────────────────────────────

    def _next_color(self) -> str:
        c = GATE_COLORS[self._color_cycle % len(GATE_COLORS)]
        self._color_cycle += 1
        return c

    def start_polygon_gate(self):
        if self.display_data is None:
            messagebox.showinfo("No data", "Open an FCS file first.")
            return
        self._cancel_selectors()
        self.draw_mode = "polygon"
        self.poly_btn.config(bg=ACC_GREEN)
        self.status("Polygon gate: click to add vertices. Press ENTER to close, ESC to cancel.")

        self._poly_selector = PolygonSelector(
            self.ax,
            onselect=self._on_polygon_complete,
            props=dict(color=self._peek_color(), lw=1.5, alpha=0.8),
        )
        self.canvas.draw_idle()

    def start_rectangle_gate(self):
        if self.display_data is None:
            messagebox.showinfo("No data", "Open an FCS file first.")
            return
        self._cancel_selectors()
        self.draw_mode = "rectangle"
        self.rect_btn.config(bg=ACC_GREEN)
        self.status("Rectangle gate: click and drag to draw. Release to complete.")

        self._rect_selector = RectangleSelector(
            self.ax,
            onselect=self._on_rectangle_complete,
            useblit=True,
            props=dict(facecolor=self._peek_color(), edgecolor=self._peek_color(),
                       alpha=0.2, fill=True),
            interactive=False,
        )
        self.canvas.draw_idle()

    def _peek_color(self) -> str:
        return GATE_COLORS[self._color_cycle % len(GATE_COLORS)]

    def cancel_draw(self):
        self._cancel_selectors()
        self.draw_mode = "none"
        self.status("Draw cancelled.")

    def _cancel_selectors(self):
        if self._poly_selector:
            try:
                self._poly_selector.disconnect_events()
            except Exception:
                pass
            self._poly_selector = None
        if self._rect_selector:
            try:
                self._rect_selector.set_active(False)
                self._rect_selector.disconnect_events()
            except Exception:
                pass
            self._rect_selector = None
        neutral = "#444455" if self._theme_name == "dark" else "#CCCCCC"
        self.poly_btn.config(bg=neutral)
        self.rect_btn.config(bg=neutral)

    def _on_polygon_complete(self, verts):
        self._cancel_selectors()
        self.draw_mode = "none"
        if len(verts) < 3:
            self.status("Polygon needs at least 3 points — cancelled.")
            return
        self._create_gate("polygon", vertices=list(verts))

    def _on_rectangle_complete(self, eclick, erelease):
        self._cancel_selectors()
        self.draw_mode = "none"
        x0, y0 = eclick.xdata, eclick.ydata
        x1, y1 = erelease.xdata, erelease.ydata
        if None in (x0, y0, x1, y1):
            self.status("Rectangle outside plot area — cancelled.")
            return
        self._create_gate("rectangle", rect_bounds=(x0, y0, x1, y1))

    def _create_gate(self, gate_type: str, **kwargs):
        name = simpledialog.askstring(
            "Gate Name",
            "Enter a name for this gate:",
            initialvalue=f"Gate {len(self.hierarchy.gates) + 1}",
            parent=self.root,
        )
        if not name:
            self.refresh_plot()
            return

        color = self._next_color()
        try:
            x_cf = float(self.x_cofactor_var.get())
        except ValueError:
            x_cf = 150.0
        try:
            y_cf = float(self.y_cofactor_var.get())
        except ValueError:
            y_cf = 150.0
        gate = Gate(
            name=name,
            x_channel=self.x_channel or "",
            y_channel=self.y_channel or "",
            parent_id=self.selected_parent_id,
            gate_type=gate_type,
            color=color,
            x_transform=self.x_transform_var.get(),
            y_transform=self.y_transform_var.get(),
            x_cofactor=x_cf,
            y_cofactor=y_cf,
            **kwargs,
        )
        self.hierarchy.add_gate(gate)
        self._refresh_gate_tree()
        self.refresh_plot()

        stats = self.hierarchy.get_gate_stats(
            gate.id, self._get_display_matrix(), self.fcs_data["channels"],
            self._current_offsets())
        self.status(
            f"Gate '{name}' created  |  {stats['count']:,} events  "
            f"({stats['pct_parent']:.1f}% of parent)"
        )

    # ─────────────────────────────────────────────────────────────
    # Gate tree
    # ─────────────────────────────────────────────────────────────

    def _refresh_gate_tree(self):
        self.gate_tree.delete(*self.gate_tree.get_children())
        if self.display_data is None:
            return

        def insert(parent_id, tree_parent):
            disp = self._get_display_matrix()
            offsets = self._current_offsets()
            for gate in self.hierarchy.get_children(parent_id):
                stats = self.hierarchy.get_gate_stats(
                    gate.id, disp, self.fcs_data["channels"], offsets)
                count_str = f"{stats['count']:,}"
                pct_str = f"{stats['pct_parent']:.1f}%"
                iid = self.gate_tree.insert(
                    tree_parent, tk.END,
                    iid=gate.id,
                    text=f"  {gate.name}",
                    values=(count_str, pct_str),
                    tags=(gate.id,),
                )
                self.gate_tree.tag_configure(gate.id, foreground=gate.color)
                insert(gate.id, iid)

        # Root node: all events
        n = len(self.display_data)
        self.gate_tree.insert("", tk.END, iid="__all__",
                              text="  All Events",
                              values=(f"{n:,}", "100%"),
                              tags=("root",))
        self.gate_tree.tag_configure("root", foreground=FG_TEXT)
        insert(None, "__all__")
        self.gate_tree.item("__all__", open=True)

    def on_gate_select(self, event):
        sel = self.gate_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "__all__":
            self.current_gate_id = None
            self.selected_parent_id = None
            self.parent_label.config(text="Parent: All Events")
        else:
            self.current_gate_id = iid
            # Don't change selected_parent_id here; only on "Gate In"
            g = self.hierarchy.get_gate(iid)
            if g:
                self.parent_label.config(text=f"Viewing: {g.name}")
        self.refresh_plot()

    def on_gate_double_click(self, event):
        """Double-click: set as parent for next gate."""
        sel = self.gate_tree.selection()
        if sel:
            self.gate_into_selected()

    def gate_into_selected(self):
        sel = self.gate_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "__all__":
            self.selected_parent_id = None
            self.current_gate_id = None
            self.parent_label.config(text="Parent: All Events")
        else:
            self.selected_parent_id = iid
            self.current_gate_id = iid
            g = self.hierarchy.get_gate(iid)
            if g:
                self.parent_label.config(text=f"Parent: {g.name}")
        self.refresh_plot()
        self.status("Draw the next gate — it will be a child of the selected gate.")

    def delete_selected_gate(self):
        if not self.current_gate_id:
            return
        g = self.hierarchy.get_gate(self.current_gate_id)
        if g and messagebox.askyesno("Delete Gate", f"Delete gate '{g.name}' and all children?"):
            self.hierarchy.remove_gate(self.current_gate_id)
            self.current_gate_id = None
            self.selected_parent_id = None
            self._refresh_gate_tree()
            self.refresh_plot()

    def rename_gate(self):
        if not self.current_gate_id:
            return
        g = self.hierarchy.get_gate(self.current_gate_id)
        if not g:
            return
        new_name = simpledialog.askstring(
            "Rename Gate", "New name:", initialvalue=g.name, parent=self.root)
        if new_name:
            g.name = new_name
            self._refresh_gate_tree()
            self.refresh_plot()

    # ─────────────────────────────────────────────────────────────
    # Misc
    # ─────────────────────────────────────────────────────────────

    def reset_zoom(self):
        self.ax.autoscale()
        self.canvas.draw_idle()

    def toggle_gate_labels(self):
        self.refresh_plot()

    def status(self, msg: str):
        self.status_var.set(msg)
        self.root.update_idletasks()


    def toggle_theme(self):
        """Switch between light and dark mode and repaint the entire UI."""
        import flowgate.app as _mod
        # Save current transform state before rebuilding panel
        try:
            self._saved_x_transform = self.x_transform_var.get()
            self._saved_y_transform = self.y_transform_var.get()
            self._saved_x_cofactor  = self.x_cofactor_var.get()
            self._saved_y_cofactor  = self.y_cofactor_var.get()
        except Exception:
            pass
        self._theme_name = "dark" if self._theme_name == "light" else "light"
        t = THEMES[self._theme_name]

        # Update module-level colour variables so helper methods pick them up
        _mod.BG_DARK   = t["BG_DARK"]
        _mod.BG_PANEL  = t["BG_PANEL"]
        _mod.BG_PLOT   = t["BG_PLOT"]
        _mod.FG_TEXT   = t["FG_TEXT"]
        _mod.ACC_BLUE  = t["ACC_BLUE"]
        _mod.ACC_GREEN = t["ACC_GREEN"]
        _mod.ACC_RED   = t["ACC_RED"]
        _mod.SEP_COLOR = t["SEP_COLOR"]

        # Also update the names used locally in this instance
        global BG_DARK, BG_PANEL, BG_PLOT, FG_TEXT, ACC_BLUE, ACC_GREEN, ACC_RED, SEP_COLOR
        BG_DARK   = t["BG_DARK"]
        BG_PANEL  = t["BG_PANEL"]
        BG_PLOT   = t["BG_PLOT"]
        FG_TEXT   = t["FG_TEXT"]
        ACC_BLUE  = t["ACC_BLUE"]
        ACC_GREEN = t["ACC_GREEN"]
        ACC_RED   = t["ACC_RED"]
        SEP_COLOR = t["SEP_COLOR"]

        self._apply_theme()

    def _apply_theme(self):
        """Rebuild the left panel and replot using current theme colours."""
        t = THEMES[self._theme_name]

        # Update root and outer frames
        self.root.configure(bg=t["BG_DARK"])
        self._paned.configure(bg=t["SEP_COLOR"])
        self._left_frame.configure(bg=t["BG_PANEL"])
        self._right_frame.configure(bg=t["BG_DARK"])

        # Destroy and rebuild the left panel contents with new colours
        for child in self._left_frame.winfo_children():
            child.destroy()
        self._build_left_panel(self._left_frame)

        # Restore state into the rebuilt widgets
        if self.fcs_data:
            chans = self.fcs_data["channels"]
            self.x_combo["values"] = chans
            self.y_combo["values"] = chans
            if self.x_channel and self.x_channel in chans:
                self.x_combo.set(self.x_channel)
            if self.y_channel and self.y_channel in chans:
                self.y_combo.set(self.y_channel)
            self.x_transform_var.set(self._saved_x_transform)
            self.y_transform_var.set(self._saved_y_transform)
            self.x_cofactor_var.set(self._saved_x_cofactor)
            self.y_cofactor_var.set(self._saved_y_cofactor)
            self.file_label.config(text=self.fcs_data["filename"])
            n = len(self.fcs_data["data"])
            self.event_count_var.set(f"{n:,} events loaded")
            self._refresh_gate_tree()

        # Rebuild status bar colours
        self._bottom_bar.configure(bg=t["BG_PANEL"])
        for child in self._bottom_bar.winfo_children():
            try:
                child.configure(bg=t["BG_PANEL"])
                fg = child.cget("fg")
                if fg in (THEMES["dark"]["ACC_BLUE"], THEMES["light"]["ACC_BLUE"]):
                    child.configure(fg=t["ACC_BLUE"])
                else:
                    child.configure(fg=t["LABEL_MUTED"])
            except Exception:
                pass

        # ttk Treeview style
        style = ttk.Style()
        tree_bg = t["BG_DARK"] if self._theme_name == "dark" else "#F5F7FA"
        style.configure("Flow.Treeview",
                        background=tree_bg, foreground=t["FG_TEXT"],
                        fieldbackground=tree_bg)
        style.configure("Flow.Treeview.Heading",
                        background=t["BG_PANEL"], foreground=t["LABEL_MUTED"])

        # Toolbar
        try:
            self.toolbar.config(bg=t["BG_PANEL"])
            for child in self.toolbar.winfo_children():
                try:
                    child.configure(bg=t["BG_PANEL"])
                except Exception:
                    pass
        except Exception:
            pass

        # Replot
        self.refresh_plot()


def main():
    root = tk.Tk()
    app = FlowGateApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
