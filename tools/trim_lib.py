"""Trim a Liberty (.lib) + LEF cell library down to a whitelist of cell families.

Library ablation (see ic-design-automation/references/ablation-and-pin-density.md):
  full        : everything
  basic       : 2-input gates only (and/or/nand/nor/xor/xnor/inv/buf families)
  full-lite   : basic + the composite cells an engineer would actually ship
  full-minus-X: full with one family removed (ablation)

Only `cell (...) { ... }` blocks are dropped from the .lib; library-level
`library() / operating_conditions / wire_load / lu_table_template / unit` stay
untouched.  Only `MACRO ... END <name>` blocks are dropped from the .lef; SITE /
LAYER / VIA sections stay untouched (deleting them breaks placement).

Usage
  python tools/trim_lib.py --lib  <in.lib>  --lef <in.lef> --preset basic --outdir DIR
  python tools/trim_lib.py --lib ... --lef ... --keep "and2%,or2%,inv%"  --outdir DIR
"""
import argparse
import json
import os
import re
import sys

PREFIX = "sky130_fd_sc_hd__"

# families are matched against the cell name with the library prefix stripped,
# so "and2_1" and "and2b_2" both start with "and2".
PRESETS = {
    "full": None,  # no trimming
    "basic": ["and2", "or2", "nand2", "nor2", "xor2", "xnor2", "inv", "buf"],
    "full-lite": ["and2", "or2", "nand2", "nor2", "xor2", "xnor2", "inv", "buf",
                  "maj3", "fa", "ha", "mux2"],
    "full-minus-a": None,  # full minus the a21oi family, see DROP_PRESETS
}

DROP_PRESETS = {
    "full-minus-a": ["a21oi", "a21o", "o21ai", "o21a"],
}

# Cells the flow itself needs no matter which logic preset is used: tap cells,
# fillers, decap, antenna diodes.  Dropping them breaks tapcell/pdn/fill steps.
MANDATORY_KEEP = ["fill", "tap", "diode", "decap", "conb", "probec", "gray"]



def short_name(cell):
    """Cell name without the vendor/library prefix.

    Handles both sky130_fd_sc_hd__xxx and the efabless extras
    sky130_ef_sc_hd__xxx, whose family is still the trailing token.
    """
    if "__" in cell:
        return cell.rsplit("__", 1)[1]
    return cell


def family_of(cell):
    """Leading family token of the cell name (drive strength stripped)."""
    return short_name(cell).split("_")[0]


def keep_cell(cell, keep_fams, drop_fams):
    fam = family_of(cell)
    if drop_fams:
        for d in drop_fams:
            if fam.startswith(d):
                return False
    for k in MANDATORY_KEEP:
        if fam.startswith(k):
            return True
    if keep_fams is None:
        return True
    for k in keep_fams:
        if fam.startswith(k):
            return True
    return False


# ------------------------------------------------------------------ liberty

CELL_START = re.compile(r"^\s*cell\s*\(\s*\"?([A-Za-z0-9_]+)\"?\s*\)\s*\{", re.M)


def trim_liberty(text, keep_fams, drop_fams):
    """Return (new_text, kept_cells, dropped_cells)."""
    kept, dropped = [], []
    pieces = []
    pos = 0
    header_written = False
    for m in CELL_START.finditer(text):
        start = m.start()
        # brace-match from the opening brace of this cell
        i = text.index("{", m.end() - 1)
        depth = 0
        j = i
        n = len(text)
        while j < n:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        cell_name = m.group(1)
        body = text[start:j + 1]
        if not header_written:
            pieces.append(text[:start])
            header_written = True
        if keep_cell(cell_name, keep_fams, drop_fams):
            pieces.append(body)
            kept.append(cell_name)
        else:
            dropped.append(cell_name)
        pos = j + 1
    if not header_written:          # no cells at all -> return input unchanged
        return text, [], []
    tail = text[pos:]
    pieces.append("\n" + tail if not tail.lstrip().startswith("}") else tail)
    return "".join(pieces), kept, dropped


# ------------------------------------------------------------------ lef

MACRO_START = re.compile(r"^\s*MACRO\s+([A-Za-z0-9_]+)\s*$", re.M)


def trim_lef(text, keep_fams, drop_fams):
    lines = text.splitlines(True)
    out = []
    kept, dropped = [], []
    i = 0
    n = len(lines)
    while i < n:
        m = MACRO_START.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        name = m.group(1)
        # find matching "END <name>"
        j = i + 1
        while j < n and lines[j].strip() != "END " + name:
            j += 1
        block = "".join(lines[i:j + 1])
        if j >= n:                      # unterminated: keep as-is
            out.append(block)
            i = j
            continue
        if keep_cell(name, keep_fams, drop_fams):
            out.append(block)
            kept.append(name)
        else:
            dropped.append(name)
        i = j + 1
    return "".join(out), kept, dropped


# ------------------------------------------------------------------ main


def resolve_sets(preset=None, keep=None, drop=None):
    keep_fams = None
    drop_fams = None
    if preset:
        if preset not in PRESETS:
            raise SystemExit("unknown preset %r (have %s)" % (preset, ", ".join(PRESETS)))
        keep_fams = PRESETS[preset]
        drop_fams = DROP_PRESETS.get(preset)
    if keep:
        keep_fams = [k.strip() for k in keep.split(",") if k.strip()]
    if drop:
        drop_fams = [d.strip() for d in drop.split(",") if d.strip()]
    return keep_fams, drop_fams


def trim(lib_path, lef_path, outdir, keep_fams, drop_fams, tag=None):
    os.makedirs(outdir, exist_ok=True)
    with open(lib_path, "r", encoding="utf-8", errors="replace") as f:
        lib_text = f.read()
    new_lib, lib_kept, lib_dropped = trim_liberty(lib_text, keep_fams, drop_fams)
    out_lib = os.path.join(outdir, os.path.basename(lib_path))
    with open(out_lib, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_lib)

    result = {
        "tag": tag,
        "keep_families": keep_fams,
        "drop_families": drop_fams,
        "lib_in": lib_path, "lib_out": out_lib,
        "lef_in": lef_path, "lef_out": None,
        "lib_cells_kept": len(lib_kept), "lib_cells_dropped": len(lib_dropped),
        "lef_macros_kept": None, "lef_macros_dropped": None,
        "cells_kept": sorted(lib_kept),
        "cells_dropped_sample": sorted(lib_dropped)[:10],
    }
    if lef_path:
        with open(lef_path, "r", encoding="utf-8", errors="replace") as f:
            lef_text = f.read()
        new_lef, lef_kept, lef_dropped = trim_lef(lef_text, keep_fams, drop_fams)
        out_lef = os.path.join(outdir, os.path.basename(lef_path))
        with open(out_lef, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_lef)
        result["lef_out"] = out_lef
        result["lef_macros_kept"] = len(lef_kept)
        result["lef_macros_dropped"] = len(lef_dropped)
        # check 1 (corrected): every cell we keep in the .lib MUST have geometry.
        # The stock merged LEF is a superset of the liberty (it also carries
        # sky130_ef_* extras and the fill/tap cells that the tt corner lib does
        # not model), so equality is the wrong predicate -- inclusion is.
        missing = sorted(set(lib_kept) - set(lef_kept))
        result["check_count_ok"] = not missing
        result["cells_without_lef"] = missing[:20]
        result["lef_only_cells"] = sorted(set(lef_kept) - set(lib_kept))
        result["lib_lef_counts"] = {"lib": len(lib_kept), "lef": len(lef_kept),
                                    "lef_only": len(result["lef_only_cells"])}
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--lef", default=None)
    ap.add_argument("--preset", default=None, choices=sorted(PRESETS))
    ap.add_argument("--keep", default=None, help="comma separated family prefixes")
    ap.add_argument("--drop", default=None, help="comma separated family prefixes")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--json", default=None, help="write the report json here")
    args = ap.parse_args()
    keep_fams, drop_fams = resolve_sets(args.preset, args.keep, args.drop)
    res = trim(args.lib, args.lef, args.outdir, keep_fams, drop_fams, tag=args.preset)
    txt = json.dumps({k: v for k, v in res.items() if k != "cells_kept"}, ensure_ascii=False, indent=1)
    print(txt)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    if res.get("check_count_ok") is False:
        print("CHECK FAILED: .lib cell count != .lef MACRO count", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
