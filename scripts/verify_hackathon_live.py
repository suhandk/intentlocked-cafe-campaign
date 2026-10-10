"""Bounded real-provider rehearsal on a separate, explicitly synthetic campaign.

Start the ordinary backend first. This creates test data, simulates owner review
only for that test data, and never publishes a website or sends social messages.
"""

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

import httpx

from backend.contracts import utc_now

API = "http://127.0.0.1:8000/api"
REPORT = Path("docs/evidence/hackathon-live-workflow.json")


async def run(resume=None, optimize=False, image=False, retry_partial=False):
    report = {
        "timestamp": utc_now(),
        "owner_review": "SIMULATED_TEST_OPERATOR",
        "scenario": "Synthetic hackathon test campaign; not a real business approval",
        "stages": {},
        "native_review": "NOT_TESTED",
        "social_delivery": "NOT_ATTEMPTED",
    }
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:

        async def call(path, body=None, method=None):
            response = await client.request(
                method or ("GET" if body is None else "POST"), API + path, json=body
            )
            if not response.is_success:
                try:
                    data = response.json()
                except ValueError:
                    data = {}
                raise RuntimeError(
                    json.dumps(
                        {
                            "path": path,
                            "http_status": response.status_code,
                            "code": data.get("code"),
                            "message": data.get("message"),
                        }
                    )
                )
            return response.json()

        async def job(cid, kind, body, target=None):
            value = await call(
                f"/campaigns/{cid}/work",
                {
                    "kind": kind,
                    "idempotency_key": f"hackathon-{kind}-{time.time_ns()}",
                    "input": body,
                    "target_id": target,
                },
            )
            deadline = time.monotonic() + 480
            while value["status"] in {"queued", "running"} and time.monotonic() < deadline:
                await asyncio.sleep(0.5)
                value = await call(f"/work/{value['id']}")
            report["stages"][kind] = {
                "status": value["status"],
                "id": value["id"],
                "error_code": value.get("error_code"),
                "calls": value["calls"],
                "elapsed_seconds": value["elapsed_seconds"],
                "notices": value["notices"],
            }
            report.setdefault("jobs", []).append({"kind": kind, **report["stages"][kind]})
            REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(kind, value["status"], value.get("error_code"), flush=True)
            if value["status"] not in {"completed", "partial"}:
                raise RuntimeError(f"{kind} stopped: {value.get('error_code')}")
            return value["result"]

        try:
            health = await call("/ready")
            assert health["mode"] == "LIVE", "Use live mode for this authenticated rehearsal"
            report["health"] = health
            if resume:
                campaign = await call(f"/campaigns/{resume}")
            else:
                campaign = await call(
                    "/campaigns",
                    {"languages": ["en"], "channels": ["instagram", "facebook", "whatsapp"]},
                )
            cid = campaign["id"]
            report["campaign_id"] = cid
            base = f"/campaigns/{cid}"
            if campaign["status"] == "draft":
                await job(
                    cid,
                    "intent",
                    {
                        "expected_revision": campaign["revision"],
                        "transcript": "Café name: Hackathon Test Cafe. Location: Bengaluru. "
                        "Product: coffee. Offer: 20 percent off. "
                        "Dates: 2026-10-10 to 2026-10-11. "
                        "Open to all. Students are the target audience, "
                        "not an eligibility restriction.",
                    },
                )
                campaign = await call(base)
                report["R1_missing_before_owner_review"] = [
                    f["key"]
                    for f in campaign["facts"]
                    if f["key"] in {"CAFE", "LOCATION", "PRODUCT", "OFFER", "DATES", "DAYS"}
                    and f["canonical"] is None
                ]
                # Explicit synthetic owner clarification through the same editable draft API.
                owner_values = {
                    "CAFE": {"kind": "text", "value": "Hackathon Test Cafe"},
                    "LOCATION": {"kind": "text", "value": "Bengaluru"},
                    "PRODUCT": {"kind": "text", "value": "coffee"},
                    "OFFER": {"kind": "percent_off", "value": 20.0, "unit": "percent"},
                    "DATES": {
                        "kind": "dates",
                        "start": "2026-10-10",
                        "end": "2026-10-11",
                        "original_phrase": "2026-10-10 to 2026-10-11",
                        "timezone": "Asia/Kolkata",
                    },
                }
                campaign = await call(
                    base + "/facts/draft",
                    {
                        "expected_revision": campaign["revision"],
                        "facts": [
                            {
                                "key": f["key"],
                                "canonical": owner_values.get(f["key"], f["canonical"]),
                            }
                            for f in campaign["facts"]
                            if f["key"] != "DAYS"
                        ],
                        "languages": campaign["languages"],
                        "channels": campaign["channels"],
                        "target_audiences": campaign["target_audiences"],
                        "brand": campaign["brand"],
                        "acknowledged_warning_ids": [w["id"] for w in campaign["warnings"]],
                    },
                    method="PUT",
                )
            if campaign["status"] in {"draft", "canonical_confirmed"}:
                await job(
                    cid,
                    "forms",
                    {"expected_revision": campaign["revision"], "confirm_canonical": True},
                )
                campaign = await call(base)
            if campaign["status"] != "locked":
                campaign = await call(
                    base + "/facts/lock",
                    {
                        "expected_revision": campaign["revision"],
                        "idempotency_key": "hackathon-test-lock-" + cid,
                        "reviewed_fact_versions": {
                            f["key"]: f["version"] for f in campaign["facts"]
                        },
                        "forms": [
                            {"key": f["key"], "surface": f["surface"]}
                            for f in campaign["facts"]
                            if f["canonical"]
                        ],
                        "approve_canonical_and_forms": True,
                        "acknowledged_warning_ids": [w["id"] for w in campaign["warnings"]],
                    },
                )
            rev = campaign["revision"]
            report["stages"]["lock"] = "PASS_SIMULATED_OWNER"
            plan = await job(cid, "strategy", {"expected_revision": rev})
            matrix = await call(base + "/matrix")
            if retry_partial and matrix["run"] and matrix["run"]["status"] == "partial":
                source = matrix["run"]
                report["stages"]["previous_partial_generation"] = {
                    "id": source["id"],
                    "ready": sum(c["state"] == "ready" for c in source["cells"]),
                    "total": len(source["cells"]),
                    "preserved": True,
                }
                request = {
                    **source["request"],
                    "retry_source_run_id": source["id"],
                    "idempotency_key": f"live-explicit-retry-{time.time_ns()}",
                }
                await job(cid, "generate", request)
                matrix = await call(base + "/matrix")
            if not matrix["run"] or matrix["run"]["status"] not in {"completed", "partial"}:
                await job(
                    cid,
                    "generate",
                    {
                        "expected_revision": rev,
                        "strategy_id": plan["id"],
                        "audience_ids": [plan["hero_audience_id"]],
                        "languages": ["en"],
                        "channels": campaign["channels"],
                        "idempotency_key": f"live-copy-{cid}-{rev}",
                    },
                )
                matrix = await call(base + "/matrix")
            variants = [
                cell["variant"] for cell in matrix["run"]["cells"] if cell["state"] == "ready"
            ]
            report["stages"]["copy_matrix"] = {
                "ready": len(variants),
                "total": len(matrix["run"]["cells"]),
            }
            assert variants, "No valid live copy; no placeholder output substituted"
            if optimize:
                await job(
                    cid,
                    "optimize",
                    {
                        "expected_revision": rev,
                        "variant_ids": [variants[0]["id"]],
                        "idempotency_key": f"live-optimization-{cid}-{rev}-{time.time_ns()}",
                    },
                )
            poster = (
                await job(
                    cid,
                    "poster_batch",
                    {
                        "expected_revision": rev,
                        "variant_id": variants[0]["id"],
                        "sizes": ["story"],
                        "source": "provider" if image else "deterministic",
                    },
                )
            )["posters"][0]
            report["live_image"] = (
                "REQUESTED" if image else "NOT_TESTED; owner key pending; local artwork selected"
            )
            delivery = await call(base + "/delivery")
            selected = [
                i
                for i in delivery["items"]
                if i.get("poster_id") == poster["id"]
                or i["source_id"] in {v["id"] for v in variants}
            ]
            warnings = set()
            for item in selected:
                audit = await job(cid, "item_audit", {"expected_revision": rev}, item["id"])
                assert audit["status"] == "PASS", "Audit blocked; approval remains pending"
                warnings.update(audit["warning_ids"])
            await call(
                base + "/approve",
                {
                    "expected_revision": rev,
                    "item_ids": [i["id"] for i in selected],
                    "observed_hashes": {i["id"]: i["snapshot_hash"] for i in selected},
                    "acknowledged_warning_ids": sorted(warnings),
                    "owner_approves": True,
                    "idempotency_key": f"live-test-approve-{cid}-{rev}",
                },
            )
            query = f"?expected_revision={rev}" + "".join("&item_ids=" + i["id"] for i in selected)
            pack = await call(base + "/export" + query)
            archive = await client.get(API + base + "/export.zip" + query)
            assert archive.is_success and archive.content.startswith(b"PK")
            Path("data/hackathon-live-approved.zip").write_bytes(archive.content)
            report["stages"]["approved_export"] = {
                "status": "PASS_SIMULATED_OWNER",
                "files": len(pack["files"]),
                "bytes": len(archive.content),
                "sha256": hashlib.sha256(archive.content).hexdigest(),
            }
            video = await job(
                cid,
                "local_video",
                {"expected_revision": rev, "poster_id": poster["id"], "duration": 12},
            )
            await call(
                f"/videos/{video['id']}/approve",
                {
                    "expected_revision": rev,
                    "observed_hash": video["sha256"],
                    "owner_approves": True,
                    "idempotency_key": "live-test-video-" + video["id"],
                },
            )
            clip = await client.get(API + f"/videos/{video['id']}/approved.mp4")
            assert clip.is_success and hashlib.sha256(clip.content).hexdigest() == video["sha256"]
            Path("data/hackathon-live-animation.mp4").write_bytes(clip.content)
            report["stages"]["approved_video"] = {
                "status": "PASS_SIMULATED_OWNER",
                "id": video["id"],
                "bytes": len(clip.content),
            }
            draft = await call(base + "/website")
            draft["fields"].update(name="Hackathon Test Cafe", area="Bengaluru", style="warm")
            draft = await call(
                f"/websites/{draft['id']}",
                {"expected_version": draft["version"], "step": 5, "fields": draft["fields"]},
                method="PUT",
            )
            bundle = await call(
                f"/websites/{draft['id']}/generate", {"expected_version": draft["version"]}
            )
            website = await client.get(API + f"/websites/{draft['id']}/download.zip")
            assert (
                website.is_success
                and hashlib.sha256(website.content).hexdigest() == bundle["sha256"]
            )
            Path("data/hackathon-live-website.zip").write_bytes(website.content)
            report["stages"]["website"] = {
                "status": "PASS_DRAFT_ZIP",
                "sha256": bundle["sha256"],
                "published": False,
            }
            report["status"] = "PASS"
        except (RuntimeError, AssertionError, KeyError, httpx.HTTPError) as exc:
            report.update(status="BLOCKED", error=str(exc)[:1000])
        finally:
            report["elapsed_seconds"] = round(time.monotonic() - started, 2)
            REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume")
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument(
        "--retry-partial", action="store_true", help="One explicit retry of unfinished cells"
    )
    parser.add_argument(
        "--image", action="store_true", help="Requires the actual direct OpenAI key"
    )
    args = parser.parse_args()
    asyncio.run(run(args.resume, args.optimize, args.image, args.retry_partial))
