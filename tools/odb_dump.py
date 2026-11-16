"""Dump ground truth from OpenROAD's odb for parser cross-checking.

Runs *inside* the ORFS container:  openroad -python odb_dump.py <out.json> <def> <lef> [<lef> ...]
Writes per-instance placement + orient + per-ITerm bbox (DBU), plus core area.
"""
import json
import sys

import odb


def main():
    out_json, def_path = sys.argv[1], sys.argv[2]
    lefs = sys.argv[3:]

    db = odb.dbDatabase.create()
    for lf in lefs:
        odb.read_lef(db, lf)
    odb.read_def(db, def_path)
    chip = db.getChip()
    block = chip.getBlock()
    dbu = block.getDefUnits()

    def rect(r):
        if r is None:
            return None
        r = r  # odb.Rect
        return [r.xMin(), r.yMin(), r.xMax(), r.yMax()]

    insts = []
    for inst in block.getInsts():
        iterms = {}
        for it in inst.getITerms():
            iterms[it.getMTerm().getName()] = rect(it.getBBox())
        insts.append({
            "name": inst.getName(),
            "master": inst.getMaster().getName(),
            "x": inst.getLocation()[0],
            "y": inst.getLocation()[1],
            "orient": str(inst.getOrient()),
            "bbox": rect(inst.getBBox()),
            "iterms": iterms,
        })

    data = {
        "def": def_path,
        "dbu": dbu,
        "diearea": rect(block.getDieArea()),
        "corearea": rect(block.getCoreArea()),
        "n_insts": len(insts),
        "insts": insts,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print("wrote %s: %d insts, dbu=%s, core=%s" % (out_json, len(insts), dbu, data["corearea"]))


if __name__ == "__main__":
    main()
