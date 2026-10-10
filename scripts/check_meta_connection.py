"""Read-only configured identity probe. Never publishes, sends, or prints credentials."""

import argparse
import asyncio
import json

from backend.config import Settings
from backend.contracts import utc_now
from backend.errors import ProviderError
from backend.meta_client import MetaClient


async def run(platform):
    config = Settings()
    report = {
        "timestamp": utc_now(),
        "platform": platform,
        "mode": config.meta_mode,
        "graph_version": config.meta_graph_version,
        "publishing": "NOT_TESTED",
    }
    if not config.meta_enabled:
        report["outcome"] = "NOT_TESTED; optional integration is disabled"
    else:
        client = MetaClient(config)
        try:
            account, _ = client.credentials(platform)
            result = await client.request(
                platform, "GET", account or "mock-account", params={"fields": "id"}
            )
            report["outcome"] = (
                "READ_CHECK_PASSED" if isinstance(result.get("id"), str) else "FAILED"
            )
            report["endpoint"] = (
                f"GET https://graph.facebook.com/{config.meta_graph_version}/[account]?fields=id"
            )
        except ProviderError as exc:
            report["outcome"], report["error_code"] = "FAILED", exc.body.code
        finally:
            await client.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=["whatsapp", "facebook", "instagram"])
    asyncio.run(run(parser.parse_args().platform))
