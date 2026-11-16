"""Minimal LEF / DEF parsers for the CellE physical-layer study.

Only what the measurement needs:
  * LEF: MACRO -> SIZE (w,h), class, SITE, PIN -> union bbox of PORT RECTs
  * DEF: UNITS, DIEAREA, COMPONENTS -> (inst, master, x, y, orient)

Coordinates are returned in DEF database units (DBU) unless noted.
Orientation handling follows the LEF/DEF reference: the 8 placement
orientations are built from (mirror-y?) + rotation, applied to the macro's
local coordinates.
"""
import math
import re

# ---------------------------------------------------------------- LEF


class Macro:
    __slots__ = ("name", "w", "h", "cls", "site", "pins")

    def __init__(self, name):
        self.name = name
        self.w = 0.0
        self.h = 0.0
        self.cls = ""
        self.site = ""
        self.pins = {}          # pin name -> (cx, cy) in microns, union-bbox centre

    def __repr__(self):
        return "<Macro %s %.3fx%.3f pins=%d>" % (self.name, self.w, self.h, len(self.pins))


def parse_lef(path, wanted=None):
    """Parse a LEF file, return {macro_name: Macro} in microns."""
    macros = {}
    stack = []
    cur = None
    pin = None
    bbox = None            # [x0,y0,x1,y1] for the current pin
    scale = 1.0            # LEF is in microns by default
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("MACRO "):
                name = line.split()[1]
                cur = Macro(name)
                macros[name] = cur
                stack.append("MACRO")
                pin = None
                continue
            if cur is None:
                continue
            if line == "END %s" % cur.name or (line.startswith("END ") and len(stack) == 1):
                cur = None
                stack.pop()
                continue
            if line.startswith("END ") and stack and stack[-1] == "PIN":
                stack.pop()
                if pin is not None and bbox is not None:
                    cur.pins[pin] = ((bbox[0] + bbox[2]) / 2.0 * scale,
                                     (bbox[1] + bbox[3]) / 2.0 * scale)
                pin, bbox = None, None
                continue
            if line.startswith("PIN ") and "PORT" not in line:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "PIN":
                    pin = parts[1]
                    bbox = None
                    stack.append("PIN")
                continue
            if line.startswith("PORT"):
                continue
            if line.startswith("SIZE "):
                m = re.match(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", line)
                if m:
                    cur.w, cur.h = float(m.group(1)), float(m.group(2))
                continue
            if line.startswith("CLASS "):
                cur.cls = line.split()[1]
                continue
            if line.startswith("SITE "):
                cur.site = line.split()[1]
                continue
            if pin is not None and line.startswith("RECT "):
                p = line.split()
                try:
                    x0, y0, x1, y1 = (float(p[1]), float(p[2]), float(p[3]), float(p[4]))
                except (IndexError, ValueError):
                    continue
                if bbox is None:
                    bbox = [x0, y0, x1, y1]
                else:
                    bbox = [min(bbox[0], x0), min(bbox[1], y0), max(bbox[2], x1), max(bbox[3], y1)]
                continue
    if wanted is not None:
        macros = {k: v for k, v in macros.items() if k in wanted}
    return macros


def parse_lef_macros_list(path):
    """Fast path: only macro names + sizes (used by the lib trimming checks)."""
    out = {}
    name = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("MACRO "):
                name = line.split()[1]
                out[name] = None
            elif name and line.startswith("SIZE "):
                m = re.match(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", line)
                if m:
                    out[name] = (float(m.group(1)), float(m.group(2)))
            elif line.startswith("END ") and name and line.split()[1] == name:
                name = None
    return out


# ---------------------------------------------------------------- DEF


class Inst:
    __slots__ = ("name", "master", "x", "y", "orient")

    def __init__(self, name, master, x, y, orient):
        self.name = name
        self.master = master
        self.x = x
        self.y = y
        self.orient = orient

    def __repr__(self):
        return "<Inst %s %s (%d,%d) %s>" % (self.name, self.master, self.x, self.y, self.orient)


def parse_def(path):
    """Return dict(units, dbu, diearea, rows, rowlist, insts)."""
    units = 1000
    diearea = None
    rowlist = []
    insts = []
    pat_comp = re.compile(r"^-\s+(\S+)\s+(\S+)")
    pat_placed = re.compile(r"\+\s+(?:PLACED|FIXED|COVER)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*(\w+)")
    pat_row = re.compile(r"^ROW\s+(\S+)\s+(\S+)\s+(-?\d+)\s+(-?\d+)\s+(\w+)\s+DO\s+(\d+)\s+BY\s+(\d+)\s+STEP\s+(-?\d+)\s+(-?\d+)")
    in_components = False
    buf = ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if not in_components:
                if line.startswith("UNITS DISTANCE MICRONS"):
                    units = int(line.split()[3])
                elif line.startswith("DIEAREA"):
                    nums = [int(n) for n in re.findall(r"-?\d+", line)]
                    if len(nums) >= 4:
                        diearea = (nums[0], nums[1], nums[2], nums[3])
                elif line.startswith("ROW "):
                    m = pat_row.match(line)
                    if m:
                        rowlist.append({
                            "name": m.group(1), "site": m.group(2),
                            "x": int(m.group(3)), "y": int(m.group(4)),
                            "orient": m.group(5), "do": int(m.group(6)),
                            "by": int(m.group(7)),
                            "stepx": int(m.group(8)), "stepy": int(m.group(9)),
                        })
                elif line.startswith("COMPONENTS "):
                    in_components = True
                    buf = ""
                continue
            # inside COMPONENTS
            if line.startswith("END COMPONENTS"):
                in_components = False
                continue
            if line.startswith("- "):
                if buf:
                    _flush_comp(buf, insts, pat_comp, pat_placed)
                buf = line
            else:
                buf += " " + line
    if buf:
        _flush_comp(buf, insts, pat_comp, pat_placed)
    return {"units": units, "dbu": units, "diearea": diearea,
            "rows": len(rowlist), "rowlist": rowlist, "insts": insts}


def rows_bbox(rowlist, site_h=None):
    """Bounding box (DBU) covered by the placement rows."""
    if not rowlist:
        return None
    xs, ys, xe, ye = [], [], [], []
    for r in rowlist:
        w = r["do"] * r["stepx"]
        h = (r["by"] - 1) * r["stepy"] + (site_h or 0)
        x0, y0 = r["x"], r["y"]
        # orient S/W rows grow downwards / leftwards in some PDKs; handle sign
        x1 = x0 + w if r["stepx"] >= 0 else x0 - w
        y1 = y0 + h if r["stepy"] >= 0 else y0 - h
        xs.append(min(x0, x1)); xe.append(max(x0, x1))
        ys.append(min(y0, y1)); ye.append(max(y0, y1))
    return (min(xs), min(ys), max(xe), max(ye))


def _flush_comp(buf, insts, pat_comp, pat_placed):
    m = pat_comp.match(buf)
    if not m:
        return
    name, master = m.group(1), m.group(2)
    p = pat_placed.search(buf)
    if p:
        insts.append(Inst(name, master, int(p.group(1)), int(p.group(2)), p.group(3)))
    else:
        insts.append(Inst(name, master, 0, 0, "N"))


# ---------------------------------------------------------------- orientations


def xform(u, v, w, h, orient):
    """Map a macro-local point to layout-local coordinates for one orientation.

    Reference (LEF/DEF): N=0, W=90 CCW, S=180, E=270 CCW; the F* variants add a
    y-mirror before the rotation.  w,h are the unrotated macro size.
    """
    o = orient.upper()
    mirror = o.startswith("F")
    rot = o[-1] if mirror else o
    if mirror:
        v = h - v
    if rot == "N":
        return u, v
    if rot == "S":
        return w - u, h - v
    if rot == "W":
        # 90 deg CCW: (x,y) -> (-y, x), shifted by h in x
        return h - v, u
    if rot == "E":
        # 270 deg CCW: (x,y) -> (y, -x), shifted by w in y
        return v, w - u
    raise ValueError("bad orientation %r" % orient)


def pin_abs(inst, macro, pin_name, dbu):
    """Absolute pin centre in DEF DBU."""
    u, v = macro.pins[pin_name]
    dx, dy = xform(u, v, macro.w, macro.h, inst.orient)
    return inst.x + dx * dbu, inst.y + dy * dbu


# ---------------------------------------------------------------- grid density


def grid_density(macros, insts, grid_um, dbu=1000, origin=None):
    """Bucket every pin into a floor(x/g) x floor(y/g) grid.

    Returns dict with:
      grid_um, ncols, nrows, origin,
      pins     : {(i,j): n_pins}
      cells    : {(i,j): n_cells}
      cellarea : {(i,j): occupied cell area in um^2}
      total_pins
    Pin exactly on a grid line goes to the upper-right cell (floor semantics).
    """
    g = float(grid_um)
    ox, oy = (origin if origin else (0.0, 0.0))
    pins = {}
    cells = {}
    cellarea = {}
    total = 0
    for inst in insts:
        m = macros.get(inst.master)
        if m is None:
            continue
        x_um = inst.x / float(dbu)
        y_um = inst.y / float(dbu)
        w, h = m.w, m.h
        # occupied area and cell anchor cell (anchor = lower-left placed corner)
        i0 = int(math.floor((x_um - ox) / g))
        j0 = int(math.floor((y_um - oy) / g))
        cells[(i0, j0)] = cells.get((i0, j0), 0) + 1
        cellarea[(i0, j0)] = cellarea.get((i0, j0), 0.0) + w * h
        for pname in m.pins:
            px, py = pin_abs(inst, m, pname, dbu)
            i = int(math.floor((px / dbu - ox) / g))
            j = int(math.floor((py / dbu - oy) / g))
            pins[(i, j)] = pins.get((i, j), 0) + 1
            total += 1
    iis = [k[0] for k in pins] or [0]
    jjs = [k[1] for k in pins] or [0]
    return {
        "grid_um": g,
        "origin": (ox, oy),
        "ncols": max(iis) - min(iis) + 1,
        "nrows": max(jjs) - min(jjs) + 1,
        "imin": min(iis), "jmin": min(jjs),
        "pins": pins, "cells": cells, "cellarea": cellarea,
        "total_pins": total,
    }


def density_stats(gd):
    """Summary stats for one grid size."""
    g = gd["grid_um"]
    area = g * g
    vals = sorted(v / area for v in gd["pins"].values())
    if not vals:
        return {}
    n = len(vals)

    def q(p):
        return vals[min(n - 1, int(p * (n - 1)))]

    tot_cells = sum(gd["cells"].values())
    tot_area = sum(gd["cellarea"].values())
    nbins = gd["ncols"] * gd["nrows"]
    return {
        "grid_um": g,
        "occupied_bins": n,
        "bins_in_bbox": nbins,
        "pins": gd["total_pins"],
        "pins_per_um2_mean": sum(vals) / n,
        "pins_per_um2_p50": q(0.50),
        "pins_per_um2_p95": q(0.95),
        "pins_per_um2_max": vals[-1],
        "cell_area_um2": tot_area,
        "cells": tot_cells,
        "cell_util_in_bbox": tot_area / (nbins * area) if nbins else 0.0,
    }
