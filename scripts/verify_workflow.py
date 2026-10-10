"""Campaign-to-export browser regression on isolated MOCK storage and owned servers."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def test_workspace():
    temporary = tempfile.TemporaryDirectory(prefix="campaign-workflow-")
    target = Path(temporary.name).resolve()
    assert target.parent == Path(tempfile.gettempdir()).resolve()
    assert target.name.startswith("campaign-workflow-")
    try:
        yield temporary.name
    finally:
        # Windows may retain a just-terminated child's file handle briefly.
        for attempt in range(6):
            try:
                temporary.cleanup()
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.5)


def create_app():
    from backend import main as application
    from backend.config import Settings
    from backend.inference_client import InferenceClient
    from backend.tests.conftest import FakeClock
    from backend.work_context import work_id

    held_campaigns = set()

    class OfflineClient(InferenceClient):
        def __init__(self, settings, store):
            assert settings.inference_mode == "mock"
            super().__init__(settings, store, clock=FakeClock())

        async def request(self, operation, payload, budget, **kwargs):
            job_id = work_id.get()
            if operation == "text" and job_id:
                row = self.store.connection.execute(
                    "SELECT payload FROM work_jobs WHERE id=?", (job_id,)
                ).fetchone()
                job = json.loads(row[0]) if row else {}
                if job.get("kind") == "generate" and job.get("campaign_id") in held_campaigns:
                    held_campaigns.remove(job["campaign_id"])
                    # Deterministically pending until cancelled; no inference dispatched.
                    await asyncio.Event().wait()
            return await super().request(operation, payload, budget, **kwargs)

    # Test process only: mocked inference and virtual quota waits; real renderer/browser.
    application.InferenceClient = OfflineClient
    app = application.create_app(
        Settings(
            _env_file=None,
            inference_mode="mock",
            database_path=Path(os.environ["WORKFLOW_TEST_DB"]),
            asset_path=Path(os.environ["WORKFLOW_TEST_ASSETS"]),
            demo_fast=True,
            today_override="2026-10-09",
            structured_strategy="tools",
        )
    )

    @app.post("/api/__test/hold-next-generation/{campaign_id}")
    async def hold_next(campaign_id: str):
        # Exists only in this MOCK factory, never backend.main's production routes.
        held_campaigns.add(campaign_id)
        return {"source": "MOCK test control", "held": True}

    return app


def stop(process):
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main():
    for port in [3000, 8000]:
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "Existing app server left untouched"
    node = shutil.which("node")
    assert node, "Node must be installed"
    selection = sys.argv[1:] or [
        "e2e/foundation.spec.ts",
        "e2e/facts.spec.ts",
        "e2e/brand-draft.spec.ts",
        "e2e/matrix.spec.ts",
        "e2e/optimization.spec.ts",
        "e2e/posters.spec.ts",
        "e2e/guardian.spec.ts",
        "e2e/delivery.spec.ts",
        "e2e/workflow.spec.ts",
        "e2e/video-option.spec.ts",
        "e2e/approval-recovery.spec.ts",
        "e2e/intent-recovery.spec.ts",
        "e2e/surface-recovery.spec.ts",
        "e2e/hackathon-media.spec.ts",
        "e2e/website-recovery.spec.ts",
    ]
    processes = []
    report_path = Path("docs/evidence/workflow-browser-debug.json")
    with test_workspace() as folder:
        env = dict(
            os.environ,
            WORKFLOW_TEST_DB=str(Path(folder) / "test.sqlite3"),
            WORKFLOW_TEST_ASSETS=str(Path(folder) / "assets"),
            INFERENCE_MODE="mock",
            INFERENCE_API_KEY="",
            ENABLE_VIDEO="false",
            VIDEO_MODEL="disabled",
            BACKEND_ORIGIN="http://127.0.0.1:8000",
            WORKFLOW_ISOLATED="1",
        )
        began = time.monotonic()
        try:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "scripts.verify_workflow:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=env,
                )
            )
            processes.append(
                subprocess.Popen(
                    [
                        node,
                        "node_modules/next/dist/bin/next",
                        "start",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        "3000",
                    ],
                    cwd=ROOT / "frontend",
                    env=env,
                )
            )
            deadline = time.monotonic() + 30
            with httpx.Client(trust_env=False) as client:
                while True:
                    try:
                        if (
                            client.get("http://127.0.0.1:8000/api/ready").status_code == 200
                            and client.get("http://127.0.0.1:3000/api/ready").status_code == 200
                            and client.get("http://127.0.0.1:3000").status_code == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "Isolated startup timed out"
                    time.sleep(0.2)
            result = subprocess.run(
                [
                    node,
                    "node_modules/@playwright/test/cli.js",
                    "test",
                    *selection,
                    "--workers=1",
                    "--reporter=line",
                ],
                cwd=ROOT / "frontend",
                env=env,
                timeout=900,
            )
            report_path.write_text(
                json.dumps(
                    {
                        "mode": "MOCK",
                        "source": "isolated fixture inference with virtual quota waits",
                        "renderer": "real Chrome canvas and PNG bytes",
                        "exit_code": result.returncode,
                        "tests_selected": selection,
                        "elapsed_seconds": round(time.monotonic() - began, 2),
                        "live_provider_calls": 0,
                        "paid_video_calls": 0,
                        "cleanup": "PENDING",
                        "timing_limit": "Real rendering; virtual waits are not live latency",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if result.returncode:
                raise SystemExit(result.returncode)
        finally:
            for process in reversed(processes):
                stop(process)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["cleanup"] = "PASS"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
