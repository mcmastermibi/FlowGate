"""
fcs_io.py — FCS file reading and writing for FlowGate
Supports FCS 2.0, 3.0, 3.1 via flowio
"""

import struct
import numpy as np
import flowio
import os


def read_fcs(filepath: str) -> dict:
    """
    Read an FCS file and return a dict with:
      - data: np.ndarray (events x channels)
      - channels: list of channel names
      - metadata: dict of FCS header metadata
    """
    fcs = flowio.FlowData(filepath)

    n_events = fcs.event_count
    n_channels = fcs.channel_count
    raw = np.reshape(fcs.events, (n_events, n_channels))

    # Build channel labels: prefer pns (short name) over pnn (full name)
    # flowio uses integer keys and lowercase field names
    channels = []
    for i in range(1, n_channels + 1):
        ch_info = fcs.channels.get(i, {})
        short = str(ch_info.get("pns", "")).strip()
        long_ = str(ch_info.get("pnn", f"Ch{i}")).strip()
        channels.append(short if short else long_)

    return {
        "data": raw,
        "channels": channels,
        "metadata": fcs.text,
        "filepath": filepath,
        "filename": os.path.basename(filepath),
    }


def write_fcs(filepath: str, data: np.ndarray, channels: list, metadata: dict):
    """
    Write a numpy array back to an FCS 3.1 file.
    Uses a minimal header derived from the original metadata.
    """
    n_events, n_channels = data.shape

    # Build TEXT segment
    text_pairs = {
        "$BEGINANALYSIS": "0",
        "$ENDANALYSIS": "0",
        "$BEGINDATA": "",       # filled after
        "$ENDDATA": "",         # filled after
        "$BYTEORD": "1,2,3,4",  # little-endian
        "$DATATYPE": "F",       # float32
        "$MODE": "L",
        "$NEXTDATA": "0",
        "$PAR": str(n_channels),
        "$TOT": str(n_events),
    }

    # Copy some original metadata if available
    for key in ["$CYT", "$DATE", "$CELLS", "$EXP", "$PROJ", "$SRC"]:
        if key in metadata:
            text_pairs[key] = metadata[key]

    # Per-channel metadata
    for i, ch in enumerate(channels, start=1):
        pn_key = f"$P{i}N"
        ps_key = f"$P{i}S"
        pb_key = f"$P{i}B"
        pr_key = f"$P{i}R"
        pe_key = f"$P{i}E"
        text_pairs[pn_key] = ch
        text_pairs[ps_key] = ch
        text_pairs[pb_key] = "32"
        text_pairs[pr_key] = str(int(data[:, i - 1].max()) + 1) if data.shape[0] > 0 else "262144"
        text_pairs[pe_key] = "0,0"

    # Encode text segment (delimiter = "|")
    delim = "|"

    def build_text(pairs):
        parts = []
        for k, v in pairs.items():
            parts.append(k)
            parts.append(v)
        return delim + delim.join(parts) + delim

    # DATA segment: float32 little-endian
    data_bytes = data.astype(np.float32).tobytes(order="C")

    # FCS header is 58 bytes (offsets padded to 8 chars each)
    HEADER_SIZE = 58
    TEXT_START = HEADER_SIZE

    # Placeholder pass to compute offsets
    placeholder_text = build_text(text_pairs)
    TEXT_END = TEXT_START + len(placeholder_text.encode("latin-1")) - 1

    DATA_START = TEXT_END + 1
    DATA_END = DATA_START + len(data_bytes) - 1

    # Now fill in $BEGINDATA / $ENDDATA
    text_pairs["$BEGINDATA"] = str(DATA_START)
    text_pairs["$ENDDATA"] = str(DATA_END)
    final_text = build_text(text_pairs)
    text_bytes = final_text.encode("latin-1")

    # Recompute with real sizes
    TEXT_END = TEXT_START + len(text_bytes) - 1
    DATA_START = TEXT_END + 1
    DATA_END = DATA_START + len(data_bytes) - 1
    text_pairs["$BEGINDATA"] = str(DATA_START)
    text_pairs["$ENDDATA"] = str(DATA_END)
    final_text = build_text(text_pairs)
    text_bytes = final_text.encode("latin-1")
    TEXT_END = TEXT_START + len(text_bytes) - 1
    DATA_START = TEXT_END + 1
    DATA_END = DATA_START + len(data_bytes) - 1

    # Write header
    header = "FCS3.1"
    header += " " * 4  # spaces
    header += f"{TEXT_START:>8}"
    header += f"{TEXT_END:>8}"
    header += f"{DATA_START:>8}"
    header += f"{DATA_END:>8}"
    header += f"{'0':>8}"  # ANALYSIS start
    header += f"{'0':>8}"  # ANALYSIS end
    header_bytes = header.encode("latin-1")
    # Pad header to exactly 58 bytes
    header_bytes = header_bytes.ljust(58)

    with open(filepath, "wb") as f:
        f.write(header_bytes)
        f.write(text_bytes)
        f.write(data_bytes)


def apply_transform(data: np.ndarray, transform: str = "asinh", cofactor: float = 150) -> np.ndarray:
    """Apply common cytometry transforms for display."""
    if transform == "asinh":
        return np.arcsinh(data / cofactor)
    elif transform == "log":
        return np.log1p(np.clip(data, 0, None))
    elif transform == "biex":
        # simplified biexponential approximation
        return np.arcsinh(data / cofactor)
    else:
        return data
