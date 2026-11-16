"""Orientation / pin-coordinate unit tests for lefdef.py (no data needed).

Checks that the 8 placement orientations map the macro's local corner box onto
either (0..w, 0..h) [N/S/FN/FS] or (0..h, 0..w) [W/E/FW/FE], and that the
transforms are isometries (distances preserved, 4 distinct rotations).
"""
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lefdef

W, H = 1.38, 2.72
CORNER_ORIENTS = ["N", "S", "W", "E", "FN", "FS", "FW", "FE"]


def bbox_of(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def test_bbox():
    corners = [(0, 0), (W, 0), (0, H), (W, H)]
    for o in CORNER_ORIENTS:
        pts = [lefdef.xform(u, v, W, H, o) for u, v in corners]
        bb = bbox_of(pts)
        swap = o[-1] in ("W", "E")
        ew, eh = (H, W) if swap else (W, H)
        ok = (abs(bb[0]) < 1e-9 and abs(bb[1]) < 1e-9
              and abs(bb[2] - ew) < 1e-9 and abs(bb[3] - eh) < 1e-9)
        print("  %-2s bbox=%s expect=(0,0,%.2f,%.2f) %s"
              % (o, tuple(round(x, 3) for x in bb), ew, eh, "OK" if ok else "FAIL"))
        assert ok, o


def test_isometry():
    pts = [(0, 0), (0.3, 0.1), (0.9, 2.0), (1.0, 2.7)]
    for o in CORNER_ORIENTS:
        t = [lefdef.xform(u, v, W, H, o) for u, v in pts]
        for (a, b), (c, d) in itertools.combinations(list(zip(pts, t)), 2):
            d0 = math.hypot(a[0] - c[0], a[1] - c[1])
            d1 = math.hypot(b[0] - d[0], b[1] - d[1])
            assert abs(d0 - d1) < 1e-9, (o, d0, d1)
    print("  isometry OK for all 8 orientations")


def test_distinct_rotations():
    p = (0.4, 0.9)
    seen = {}
    for o in ["N", "W", "S", "E"]:
        seen[o] = tuple(round(x, 6) for x in lefdef.xform(p[0], p[1], W, H, o))
    assert len(set(seen.values())) == 4, seen
    print("  4 rotations distinct:", seen)


def test_pin_abs_extents():
    """pin_abs must land inside the placed instance box for every orientation."""
    m = lefdef.Macro("m")
    m.w, m.h = W, H
    m.pins = {"A": (0.2, 1.0), "Y": (W - 0.2, 1.8)}
    inst = lefdef.Inst("i0", "m", 10000, 20000, "N")
    for o in CORNER_ORIENTS:
        inst.orient = o
        swap = o[-1] in ("W", "E")
        ew, eh = (H, W) if swap else (W, H)
        for pn in m.pins:
            px, py = lefdef.pin_abs(inst, m, pn, 1000)
            lx = (px - inst.x) / 1000.0
            ly = (py - inst.y) / 1000.0
            assert -1e-9 <= lx <= ew + 1e-9, (o, pn, lx, ew)
            assert -1e-9 <= ly <= eh + 1e-9, (o, pn, ly, eh)
    print("  pin_abs inside placed bbox for all 8 orientations")


if __name__ == "__main__":
    print("test_bbox:"); test_bbox()
    print("test_isometry:"); test_isometry()
    print("test_distinct_rotations:"); test_distinct_rotations()
    print("test_pin_abs_extents:"); test_pin_abs_extents()
    print("ALL TESTS PASSED")
