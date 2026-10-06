"""A collaboration chunk on the plan keeps the server's allocation.

    python tools/check_collab_plan.py

The bug this pins down, found on a real night: the server dealt three panels
in one filter; Auto-arrange with "pick exposures" then chose filters for the
chunk as though it were the operator's own target, divided its slot by the
whole mosaic's panel count, found room for nothing and emptied its list; the
plan's repair step put the project's full depth on every filter back onto
it, and the telescope set off to shoot one panel in five filters.

Driven against the real application module with a stub task in place of the
collaboration server, so the plan endpoints are the ones the window uses.

No test framework, for the same reason as the other checks here.
"""
import os
import sys
import tempfile
import time
import warnings as _warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["ASTRO_DATA_DIR"] = tempfile.mkdtemp()
_warnings.simplefilter("ignore")

from astrocontrol import main                                      # noqa: E402

results = []


def case(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))
    results.append(bool(ok))
    return ok


main.watchdog.stop()
main.config.update("site", {"latitude": 31.5, "longitude": -99.4, "useMount": False})
main.config.update("camera", {"filterNames": ["L", "R", "G", "B", "S", "H", "O"]})

# -- a mosaic target stamped as a collaboration chunk ----------------------
# Five rows by three columns, like the real one; the server dealt panels
# 3, 4 and 9 and tonight's visit is ten frames of H on each.
TASK = {
    "id": "task-1", "project": "proj-1", "projectName": "heart neb mosaic",
    "version": 4, "state": "accepted", "kind": "mosaic",
    "region": {"ra": 38.0, "dec": 61.5, "width": 11.0, "height": 13.0},
    "filters": [{"filter": name, "exposure": 600.0, "hours": 6.0}
                for name in ("H", "O", "R", "G", "B")],
    "share": [3, 4, 9],
    "visit": {"seconds": 6000.0, "frames": {"H": 10}, "filter": "H"},
}
main.collab_client._task = TASK
main.collab_client._tasks = [TASK]
main.collab_client._open = []

target = main.targets.create(
    "heart neb mosaic", 38.0 / 15.0, 61.5, rotation=0.0,
    panel_width=5.3, panel_height=3.5, rows=5, columns=3,
    collab={"project": "proj-1", "projectName": "heart neb mosaic",
            "task": "task-1", "version": 4})
main.targets.stamp_collab(target["id"], {"share": [3, 4, 9]})
target = main.targets.get(target["id"])
case("the stub target is a fifteen-panel mosaic stamped as a chunk",
     len(target["panels"]) == 15 and target["collab"]["task"] == "task-1")
entry = main.plan.add(target["id"], target["name"])
main.plan.set_options(entry["id"], {"panels": [3, 4, 9]})
main._apply_task_allocation(entry["id"], TASK, target)


def allocation():
    stored = next(e for e in main.plan.raw()["entries"] if e["id"] == entry["id"])
    return {f["name"]: f["count"] for f in stored.get("filters") or []}


first = allocation()
case("the visit's one filter is the only one with frames",
     first == {"H": 10}, str(first))

# -- Auto-arrange with "pick exposures" leaves it alone ---------------------
answer = main.arrange_plan(main.ArrangeRequest(chooseExposures=True))
after = allocation()
case("Auto-arrange choosing exposures does not touch the chunk's filters",
     after == {"H": 10}, str(after))
note = next((c for c in answer.get("chosen") or [] if c["id"] == entry["id"]), {})
case("...and says so in its notes",
     any("collaboration server" in n for n in note.get("notes") or []), str(note.get("notes")))

# -- the plan endpoint, which repairs an empty list, keeps it one filter ----
shown = main.get_plan(date=None)
row = next(e for e in shown["entries"] if e["id"] == entry["id"])
counts = {f["name"]: f["count"] for f in row.get("filters") or []}
case("the plan shows the one filter the server dealt", counts == {"H": 10}, str(counts))
forecast = (row.get("tonight") or {}).get(main.rigs.master.id) or {}
case("...and tonight reaches more than one panel at that depth",
     len(forecast.get("panels") or []) >= 2, str(forecast.get("panels")))

# -- an emptied list is repaired to the visit, not to the full depth ---------
main.plan.set_filters(entry["id"], [], 3, 1e12, main._overheads())
shown = main.get_plan(date=None)
row = next(e for e in shown["entries"] if e["id"] == entry["id"])
counts = {f["name"]: f["count"] for f in row.get("filters") or []}
case("a chunk that lost its frames gets tonight's visit back, not the project's depth",
     counts == {"H": 10}, str(counts))

# -- an older server with no visit still gets the full depth ----------------
old = {**TASK, "id": "task-2", "visit": {}}
main._apply_task_allocation(entry["id"], old, target)
counts = allocation()
case("without a visit the project's full depth goes on every filter, as before",
     counts == {name: 36 for name in ("H", "O", "R", "G", "B")}, str(counts))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
