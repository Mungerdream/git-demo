"""Turn one ORFS run directory into one runs.csv row (15 fields, append-only).

    python tools/collect.py --rundir runs/sky130_full_adder128_s1 \
        --design adder128 --lib full --seed 1 --pdk sky130 [--density density.json]

Reads, in this order (all optional except the DEF):
  results/<pdk>/<design>/<variant>/6_final.def   core area / cell count / density
  reports/.../synth_stat.txt                     logic area (.lib nominal sum)
  logs/.../6_report.json                         area, util, WNS, TNS, DRV
  logs/.../5_2_route.json                        wirelength, DRC errors
"""
import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lefdef

FIELDS = ["run_id", "design", "pdk", "lib", "seed", "area_logic", "area_layout",
          "util", "wirelen", "cong", "wns", "cells", "pin_density",
          "status", "script_ver", "area_die", "tns", "drc_errors",
          "cells_stdcell", "area_logic_synth", "n_insts_def", "grid_um",
          "pin_density_p95", "pin_density_max", "variant", "notes"]


def find_first(root, names):
    for n in names:
        p = os.path.join(root, n)
        if os.path.exists(p):
            return p
    for dirpath, _dirs, files in os.walk(root):
        for n in names:
            if n in files:
                return os.path.join(dirpath, n)
    return None


def find_json(root, name):
    return find_first(root, [name])


def load_json(p):
    if not p or not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return {}


def parse_synth_area(root):
    p = find_first(root, ["synth_stat.txt"])
    if not p:
        return None, None
    top = None
    allv = {}
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.search(r"Chip area for module '\\?([^']+)':\s*([\d.]+)", line)
            if m:
                allv[m.group(1)] = float(m.group(2))
            m2 = re.search(r"Chip area for top module '\\?([^']+)':\s*([\d.]+)", line)
            if m2:
                top = float(m2.group(2))
    if top is None and allv:
        top = max(allv.values())
    return top, allv


def count_netlist_cells(root):
    """Count instantiated cells in the mapped netlist (post-route 6_final.v)."""
    p = find_first(root, ["6_final.v"])
    if not p:
        return None
    n = 0
    pat = re.compile(r"^\s+(sky130_fd_sc_hd__\w+)\s+\S+\s*\(")
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if pat.match(line):
                n += 1
    return n

def build_row(rundir, design, lib, seed, pdk="sky130", script_ver="tools-0.1",
              density=None, status=None, notes="", site_height_um=2.72):
    rid = "%s_%s_%s_s%s" % (pdk, lib, design, seed)
    row = dict.fromkeys(FIELDS, "")
    row.update(run_id=rid, design=design, pdk=pdk, lib=lib, seed=seed,
               script_ver=script_ver, notes=notes)

    rpt = load_json(find_json(rundir, "6_report.json"))
    route = load_json(find_json(rundir, "5_2_route.json"))
    logic, _all = parse_synth_area(rundir)

    def g(key, default=""):
        v = rpt.get(key, default)
        return v

    row["area_logic"] = round(logic, 3) if logic else ""
    row["area_logic_synth"] = row["area_logic"]
    row["area_layout"] = g("finish__design__core__area")
    row["area_die"] = g("finish__design__die__area")
    row["util"] = g("finish__design__instance__utilization")
    row["wns"] = g("finish__timing__setup__ws")
    row["tns"] = g("finish__timing__setup__tns")
    row["wirelen"] = route.get("detailedroute__route__wirelength", "")
    row["drc_errors"] = route.get("detailedroute__route__drc_errors", "")
    row["cong"] = route.get("detailedroute__route__drc_errors", "")
    row["grt_wirelength"] = rpt.get("globalroute__global_route__wirelength", "")
    cnt = g("finish__design__instance__count", "")
    fill = g("finish__design__instance__count__class:fill_cell", 0) or 0
    tap = g("finish__design__instance__count__class:tap_cell", 0) or 0
    row["cells"] = cnt
    try:
        row["cells_stdcell"] = int(cnt) - int(fill) - int(tap)
    except (TypeError, ValueError):
        row["cells_stdcell"] = ""

    # DEF-derived numbers
    defp = find_first(rundir, ["6_final.def"])
    if defp:
        d = lefdef.parse_def(defp)
        dbu = d["dbu"]
        row["n_insts_def"] = len(d["insts"])
        rb = lefdef.rows_bbox(d["rowlist"])
        if rb:
            row["def_rows_bbox_um2"] = ""  # extra field kept out of FIELDS order
        row["variant"] = os.path.basename(os.path.dirname(defp))
        nc = count_netlist_cells(rundir)
        row["netlist_cells"] = nc
        row["check_components_eq_netlist"] = (
            nc is not None and row["cells_stdcell"] != ""
            and int(row["cells_stdcell"]) == nc)
        rb = lefdef.rows_bbox(d["rowlist"], site_h=site_height_um * dbu)
        if rb:
            area_um2 = (rb[2] - rb[0]) / float(dbu) * (rb[3] - rb[1]) / float(dbu)
            row["rows_area_um2"] = round(area_um2, 2)
            try:
                rep = float(row["area_layout"])
                row["check_core_area_delta_pct"] = round(100.0 * (area_um2 - rep) / rep, 3)
            except (TypeError, ValueError):
                row["check_core_area_delta_pct"] = ""

    if density:
        d5 = None
        for k, v in density.get("grids", {}).items():
            if abs(float(k) - 5.0) < 1e-6:
                d5 = v
        if d5:
            row["pin_density"] = round(d5.get("pins_per_um2_mean", ""), 5)
            row["pin_density_p95"] = round(d5.get("pins_per_um2_p95", ""), 5)
            row["pin_density_max"] = round(d5.get("pins_per_um2_max", ""), 5)
            row["grid_um"] = 5

    if status is None:
        ok = bool(rpt) and row["area_layout"] != ""
        status = "success" if ok else "fail"
    row["status"] = status
    return row


def append_row(csv_path, row):
    exists = os.path.exists(csv_path)
    keys = list(row.keys())
    if exists:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            have = r.fieldnames or []
        for k in have:
            if k not in keys:
                keys.append(k)
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in keys})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rundir", required=True)
    ap.add_argument("--design", required=True)
    ap.add_argument("--lib", required=True)
    ap.add_argument("--seed", default="1")
    ap.add_argument("--pdk", default="sky130")
    ap.add_argument("--density", default=None)
    ap.add_argument("--script-ver", default="tools-0.1")
    ap.add_argument("--status", default=None)
    ap.add_argument("--notes", default="")
    ap.add_argument("--csv", default="runs.csv")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dens = None
    if a.density and os.path.exists(a.density):
        with open(a.density, "r", encoding="utf-8") as f:
            dens = json.load(f)
    row = build_row(a.rundir, a.design, a.lib, a.seed, a.pdk, a.script_ver,
                    dens, a.status, a.notes)
    print(json.dumps(row, ensure_ascii=False, indent=1))
    if not a.dry_run:
        append_row(a.csv, row)
        print("appended to", a.csv)


if __name__ == "__main__":
    main()
