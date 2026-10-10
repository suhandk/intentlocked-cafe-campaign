"""Enforce branch coverage per critical module, not a misleading aggregate average."""

import json
import sys
from pathlib import Path


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/evidence/g2-coverage.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    critical = {"claims", "normalize", "rules", "slots", "report"}
    seen = set()
    for name, result in report["files"].items():
        module = Path(name.replace("\\", "/")).stem
        if module in critical:
            seen.add(module)
            summary = result["summary"]
            total = summary["num_branches"]
            percent = 100 * summary["covered_branches"] / total if total else 100
            print(f"{module}: {percent:.2f}% branches")
            if percent < 90:
                raise SystemExit(f"G2 failed: {module} below 90% branch coverage")
    if seen != critical:
        raise SystemExit("G2 failed: critical module missing from coverage report")


if __name__ == "__main__":
    main()
