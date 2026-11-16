"""Grid-level pin density from LEF + DEF (no OpenROAD needed).

    python tools/pin_density.py --def 6_final.def --lef sky130_fd_sc_hd.lef \
        --grids 2.5,5,10 --out density.json

Grid size is in microns; pins exactly on a grid line go to the upper-right bin
(floor semantics), as documented in the paper's method section.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lefdef


def load(lef_paths, def_path):
    macros = {}
    for lp in lef_paths:
        macros.update(lefdef.parse_lef(lp))
    d = lefdef.parse_def(def_path)
    return macros, d


def run(def_path, lef_paths, grids, out_json=None, top=10, quiet=False):
    macros, d = load(lef_paths, def_path)
    dbu = d["dbu"]
    missing = {}
    for inst in d["insts"]:
        if inst.master not in macros:
            missing[inst.master] = missing.get(inst.master, 0) + 1
    if missing and not quiet:
        print("WARN: %d macros not found in LEF: %s" % (len(missing), list(missing)[:5]), file=sys.stderr)

    out = {
        "def": def_path,
        "lefs": lef_paths,
        "dbu": dbu,
        "diearea_um": [v / float(dbu) for v in d["diearea"]] if d["diearea"] else None,
        "n_insts": len(d["insts"]),
        "missing_masters": missing,
        "grids": {},
    }
    for g in grids:
        gd = lefdef.grid_density(macros, d["insts"], g, dbu=dbu)
        st = lefdef.density_stats(gd)
        st["top_bins"] = sorted(
            ((k[0], k[1], v, v / (g * g)) for k, v in gd["pins"].items()),
            key=lambda t: -t[2])[:top]
        out["grids"]["%g" % g] = st
        if not quiet:
            print("grid %5.2f um : bins=%d occupied=%d  pins=%d  "
                  "mean=%.4f p50=%.4f p95=%.4f max=%.4f pin/um2"
                  % (g, st["bins_in_bbox"], st["occupied_bins"], st["pins"],
                     st["pins_per_um2_mean"], st["pins_per_um2_p50"],
                     st["pins_per_um2_p95"], st["pins_per_um2_max"]))
    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        if not quiet:
            print("wrote", out_json)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--def", dest="def_path", required=True)
    ap.add_argument("--lef", dest="lefs", action="append", required=True)
    ap.add_argument("--grids", default="2.5,5,10")
    ap.add_argument("--out", default=None)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    grids = [float(x) for x in a.grids.split(",") if x.strip()]
    run(a.def_path, a.lefs, grids, a.out, a.top)


if __name__ == "__main__":
    main()
