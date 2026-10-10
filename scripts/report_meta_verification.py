"""Build a redacted report from executed pytest/browser evidence, never fake success."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.contracts import utc_now


def main():
    directory = Path("docs/evidence")
    root = ET.parse(directory / "meta-tests.xml").getroot()
    cases = list(root.iter("testcase"))
    meta = [c for c in cases if c.get("classname", "").endswith("test_meta")]
    assert meta, "Execute Meta tests with JUnit output first"
    outcomes = [
        {
            "name": c.get("name"),
            "seconds": float(c.get("time", "0")),
            "outcome": "FAILED"
            if c.find("failure") is not None or c.find("error") is not None
            else "SKIPPED"
            if c.find("skipped") is not None
            else "PASS",
        }
        for c in meta
    ]
    report = {
        "timestamp": utc_now(),
        "mode": "MOCK",
        "provider": "Meta",
        "inference_provider": "Configured provider; unchanged",
        "model": "not applicable to delivery",
        "candidate_graph_pin": "v25.0; support/retirement NOT_VERIFIED",
        "documentation": {
            "status": "DOCUMENTATION_UNAVAILABLE",
            "outcome": "Official fetches returned 429/inaccessible; live contracts not verified",
            "attempt_date": "2026-10-09",
        },
        "backend_suite": {
            "total": len(cases),
            "failed": sum(
                c.find("failure") is not None or c.find("error") is not None for c in cases
            ),
        },
        "meta_tests": outcomes,
        "raw_transport": [
            {
                "platform": platform,
                "endpoint": endpoint,
                "mode": "MOCK",
                "http_status": "fixture 200",
                "outcome": "MOCK_TESTED; see raw-shape assertions",
                "authenticated_outcome": "NOT_TESTED",
            }
            for platform, endpoint in [
                ("whatsapp", "POST /[version]/[phone-id]/messages"),
                ("facebook", "POST /[version]/[page-id]/feed or photos"),
                ("instagram", "POST /[version]/[ig-id]/media; GET status; POST media_publish"),
            ]
        ],
        "authenticated": {p: "NOT_TESTED" for p in ("whatsapp", "facebook", "instagram")},
        "live_messages_or_posts": 0,
        "live_gate": "BLOCKED until documentation/account/live checks "
        "and exact live-action authorization",
    }
    browser = directory / "meta-browser.json"
    report["browser"] = (
        json.loads(browser.read_text()) if browser.exists() else {"outcome": "NOT_TESTED"}
    )
    (directory / "meta-contract.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Wrote redacted Meta report from executed evidence; authenticated checks remain NOT_TESTED"
    )


if __name__ == "__main__":
    main()
