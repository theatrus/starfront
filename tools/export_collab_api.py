"""Write the collaboration server's OpenAPI document to server/openapi.json.

The types live in server/schemas.py; FastAPI builds the document from them.
Run this after changing a request or response, and commit the result, so the
protocol's shape can be read and diffed without starting a server.

    python tools/export_collab_api.py          # write it
    python tools/export_collab_api.py --check  # fail if it is out of date
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "server" / "openapi.json"


def build() -> str:
    # Importing the app opens its database; point it somewhere disposable.
    os.environ["ASTROCOLLAB_DATA"] = tempfile.mkdtemp(prefix="collab-openapi-")
    sys.path.insert(0, str(ROOT))
    from server.app import app
    return json.dumps(app.openapi(), indent=2, sort_keys=False) + "\n"


def main() -> int:
    text = build()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
            print("server/openapi.json is out of date: run python tools/export_collab_api.py")
            return 1
        print("server/openapi.json matches server/schemas.py")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
