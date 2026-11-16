"""Cross-check our LEF/DEF pin geometry against OpenROAD's own odb database.

Truth file: produced by tools/odb_dump.py inside the ORFS container, containing
per-instance placement + orient and the bbox of every ITerm in DBU.

For every pin we compare the *centre of the union of PORT RECTs* (our parser)
with *odb's ITerm bbox centre*.  A wrong orientation transform shows up as a
systematic offset for the W/E/F* cells, so we report the error per orientation.

    python tools/check_orient.py --truth odb_truth.json --def 6_final.def \
        --lef merged.lef --out orient_check.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lefdef


def centre(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", required=True)
    ap.add_argument("--def", dest="def_path", required=True)
    ap.add_argument("--lef", dest="lef", action="append", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--tol-nm", type=float, default=50.0)
    a = ap.parse_args()

    with open(a.truth, "r", encoding="utf-8") as f:
        truth = json.load(f)
    macros = {}
    for lp in a.lef:
        macros.update(lefdef.parse_lef(lp))
    d = lefdef.parse_def(a.def_path)
    dbu = d["dbu"]
    by_name = {i.name: i for i in d["insts"]}

    per_orient = {}
    total = 0
    compared = 0
    missing_pin = 0
    worst = 0.0
    worst_info = None
    for t in truth["insts"]:
        inst = by_name.get(t["name"])
        if inst is None:
            continue
        m = macros.get(t["master"])
        if m is None:
            continue
        o = t["orient"]
        st = per_orient.setdefault(o, {"n": 0, "max_nm": 0.0, "sum_nm": 0.0, "over_tol": 0})
        for pname, bb in t["iterms"].items():
            total += 1
            if not bb or pname not in m.pins:
                missing_pin += 1
                continue
            px, py = lefdef.pin_abs(inst, m, pname, dbu)
            tx, ty = centre(bb)
            err = ((px - tx) ** 2 + (py - ty) ** 2) ** 0.5      # DBU == nm for sky130
            compared += 1
            st["n"] += 1
            st["sum_nm"] += err
            st["max_nm"] = max(st["max_nm"], err)
            if err > a.tol_nm:
                st["over_tol"] += 1
            if err > worst:
                worst = err
                worst_info = {"inst": t["name"], "master": t["master"], "orient": o,
                              "pin": pname, "ours": [px, py], "odb": [tx, ty],
                              "err_nm": round(err, 3)}

    report = {
        "def": a.def_path,
        "truth": a.truth,
        "pins_total": total,
        "pins_compared": compared,
        "pins_skipped_no_geom": missing_pin,
        "tol_nm": a.tol_nm,
        "max_err_nm": round(worst, 3),
        "worst": worst_info,
        "n_over_tol": sum(v["over_tol"] for v in per_orient.values()),
        "per_orient": {k: {"n": v["n"], "max_nm": round(v["max_nm"], 3),
                           "mean_nm": round(v["sum_nm"] / v["n"], 3) if v["n"] else None,
                           "over_tol": v["over_tol"]}
                       for k, v in sorted(per_orient.items())},
        "pass": (compared > 0 and worst <= a.tol_nm),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    sys.exit(0 if report["pass"] else 3)


if __name__ == "__main__":
    main()
