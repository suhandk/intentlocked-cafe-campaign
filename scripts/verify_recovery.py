"""Local-only abrupt restart verification. Uses labeled mock fixtures, never a key."""

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from backend.db import Store
from backend.tests.test_generation import locked, seed

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8001/api"


def kill_owned(process):
    # Windows venv python.exe may launch a child interpreter: kill the owned tree.
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.kill()
    process.wait(timeout=10)


def wait_for(check, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise AssertionError("Recovery condition did not complete within its finite deadline")


def main():
    identifier = str(time.time_ns())
    db_path = ROOT / "data" / f"b7-recovery-{identifier}.sqlite3"
    assets = ROOT / "data" / f"b7-recovery-{identifier}-assets"
    campaign = locked.__wrapped__()
    with_store = Store(db_path)
    seed(type("Fixture", (), {"store": with_store}), campaign)
    with_store.close()
    env = {
        **os.environ,
        "INFERENCE_MODE": "mock",
        "DATABASE_PATH": str(db_path),
        "ASSET_PATH": str(assets),
        "TEXT_RPM": "8",
        "DEMO_FAST": "0",
    }
    env.pop("INFERENCE_API_KEY", None)

    def start():
        # Refuse to attach to somebody else's listener, especially a live process.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", 8001)) == 0:
                raise RuntimeError("Port 8001 already has a listener; do not attach to it")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def ready():
            if process.poll() is not None:
                raise RuntimeError("The owned mock server could not start")
            response = httpx.get(BASE + "/ready", trust_env=False)
            return response.status_code == 200 and response.json()["mode"] == "MOCK"

        wait_for(ready)
        return process

    process = None
    report = {"mode": "MOCK", "provider_live_checks": "NOT_TESTED"}
    with httpx.Client(timeout=5, trust_env=False) as http:

        def read(path):
            response = http.get(BASE + path)
            response.raise_for_status()
            return response.json()

        def submit(kind, input_values, key):
            response = http.post(
                BASE + f"/campaigns/{campaign.id}/work",
                json={
                    "kind": kind,
                    "idempotency_key": key,
                    "input": {"expected_revision": campaign.revision, **input_values},
                },
            )
            assert response.status_code == 202
            return response.json()

        try:
            process = start()
            prefix = f"/campaigns/{campaign.id}"
            background_job = submit(
                "background",
                {"size": "square", "source": "deterministic"},
                "recovery-background-key",
            )
            wait_for(lambda: read(f"/work/{background_job['id']}")["status"] == "completed")
            background = read(f"/work/{background_job['id']}")["result"]
            raw = http.get(BASE + f"/assets/{background['id']}").content
            assert hashlib.sha256(raw).hexdigest() == background["sha256"]
            strategy = submit("strategy", {}, "recovery-strategy-key")
            wait_for(lambda: read(f"/work/{strategy['id']}")["status"] == "completed")
            plan = read(f"/work/{strategy['id']}")["result"]
            job = submit(
                "generate",
                {
                    "strategy_id": plan["id"],
                    "idempotency_key": "native-recovery-key",
                    "audience_ids": [plan["hero_audience_id"]],
                    "languages": ["en", "kn"],
                    "channels": ["whatsapp"],
                },
                "recovery-generation-key",
            )
            wait_for(
                lambda: any(c["state"] == "ready" for c in read(prefix + "/matrix")["run"]["cells"])
            )
            before = read(prefix + "/matrix")["run"]
            ready_ids = [c["variant"]["id"] for c in before["cells"] if c["state"] == "ready"]
            before_cost = read("/cost")
            kill_owned(process)  # actual abrupt process termination, not graceful cancellation
            process = start()
            after = read(prefix + "/matrix")["run"]
            assert after["status"] == "interrupted"
            assert [
                c["variant"]["id"] for c in after["cells"] if c["state"] == "ready"
            ] == ready_ids
            assert read(f"/work/{job['id']}")["status"] == "interrupted"
            assert read("/cost") == before_cost
            assert http.get(BASE + f"/assets/{background['id']}").content == raw
            snap = read(prefix + "/work")
            assert snap["active"] == 0 and snap["queued"] == 0
            # Verify raw HTTP SSE replay using a real Last-Event-ID request header.
            with http.stream(
                "GET", BASE + f"/stream/{campaign.id}", headers={"Last-Event-ID": "0"}
            ) as stream:
                assert stream.status_code == 200
                assert stream.headers["content-type"].startswith("text/event-stream")
                first_id = next(
                    int(line[4:]) for line in stream.iter_lines() if line.startswith("id: ")
                )
            with http.stream(
                "GET", BASE + f"/stream/{campaign.id}", headers={"Last-Event-ID": str(first_id)}
            ) as stream:
                replay_id = next(
                    int(line[4:]) for line in stream.iter_lines() if line.startswith("id: ")
                )
            assert replay_id > first_id and read("/cost") == before_cost
            report.update(
                {
                    "abrupt_restart": "PASS",
                    "completed_cells_retained": ready_ids,
                    "interrupted_job": job["id"],
                    "persistent_asset_sha256": background["sha256"],
                    "asset_bytes_restored": "PASS",
                    "sse_last_event_id_raw_http": "PASS",
                    "replay_no_new_calls_or_costs": "PASS",
                    "calls_before_and_after": before_cost["calls"],
                    "timestamp": __import__("datetime")
                    .datetime.now(__import__("datetime").UTC)
                    .isoformat(),
                }
            )
            target = ROOT / "docs/evidence/b7-recovery.json"
            target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
        finally:
            if process:
                kill_owned(process)


if __name__ == "__main__":
    main()
