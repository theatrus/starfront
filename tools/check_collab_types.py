"""The collaboration server's types: lenient where the program has always been,
and the published OpenAPI document current.

    python tools/check_collab_types.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["ASTROCOLLAB_DATA"] = tempfile.mkdtemp(prefix="collab-types-")
os.environ["ASTROCOLLAB_ADMIN_TOKEN"] = "admin-token-for-checks"
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402

passed = failed = 0


def check(ok: bool, name: str, detail: object = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  - {detail}")


client = TestClient(app)
admin = {"Authorization": "Bearer admin-token-for-checks"}

made = client.post("/api/v1/agents", json={"name": "Blank settings"}, headers=admin)
check(made.status_code == 200, "a telescope is enrolled", made.text)
rig = {"Authorization": f"Bearer {made.json()['token']}"}

# A rig whose settings were never filled in sends blanks, and always has.
hello = client.post("/api/v1/agent/hello", headers=rig, json={"profile": {
    "name": "Blank settings", "focalLength": "", "pixelSize": None,
    "sensorWidth": "abc", "sensorHeight": "", "binning": "", "filters": {"Ha": ""},
    "exposures": {"Ha": ""}, "hoursPerNight": "", "somethingNewer": 1}})
check(hello.status_code == 200, "a hello with blank numbers is accepted, not refused", hello.text)
stored = client.get("/api/v1/agents", headers=admin).json()["agents"][0]["profile"]
check(stored.get("somethingNewer") == 1, "fields the server does not know are kept", stored)
check("scale" not in stored, "a model adds no keys the rig did not send", sorted(stored))

report = client.post("/api/v1/agent/report", headers=rig, json={"contributions": [
    {"filterName": "Ha", "frames": "", "seconds": "", "exposure": "", "hfr": "n/a"}]})
check(report.status_code == 200, "a report with blank numbers is judged, not refused", report.text)

bad = client.post("/api/v1/agent/task/no-such-task", headers=rig, json={"state": "maybe"})
check(bad.status_code == 422, "a task state outside the protocol is refused by its type", bad.status_code)

region = {"ra": 10.68, "dec": 41.27, "width": 3.0, "height": 1.0}
project = client.post("/api/v1/projects", headers=admin, json={
    "name": "Typed", "region": region, "goals": {"Ha": 10},
    "requirements": {"filters": {"Ha": 7}, "minExposure": "", "minFramesPerVisit": ""}})
check(project.status_code == 200, "a project with blank rule fields is created", project.text)
check(client.post("/api/v1/projects", headers=admin, json={"name": "No sky"}).status_code == 422,
      "a project with no region is refused by its type")

sys.argv = [sys.argv[0], "--check"]
sys.path.insert(0, str(ROOT / "tools"))
import export_collab_api  # noqa: E402
check(export_collab_api.main() == 0, "server/openapi.json matches server/schemas.py")

print()
print(f"{passed}/{passed + failed} passed")
sys.exit(1 if failed else 0)
