"""Require measured 90% branch coverage independently for change and ledger."""

import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/evidence/g6-coverage.json")
files = json.loads(path.read_text(encoding="utf-8"))["files"]
for module in ["change", "ledger"]:
    record = next(
        value for name, value in files.items() if name.replace("\\", "/") == f"backend/{module}.py"
    )
    percent = record["summary"]["percent_branches_covered"]
    print(f"{module}: {percent:.2f}% branches")
    if percent < 90:
        raise SystemExit(f"{module} is below 90% branch coverage")
