import asyncio
import socket

import httpx
import pytest

from backend.config import Settings
from backend.db import Store
from backend.inference_client import Clock, InferenceClient


class FakeClock(Clock):
    def __init__(self):
        self.value = 100.0
        self.sleeps = []

    def now(self):
        return self.value

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("External networking forbidden in offline tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture
def factory(tmp_path):
    stores = []

    def make(handler=None, **config):
        # Explicit fixture prices, not real provider pricing. Production defaults are unknown.
        config.setdefault("text_input_price_per_million", 0.05)
        config.setdefault("text_output_price_per_million", 0.15)
        config.setdefault("image_price_per_output", 0.01)
        config.setdefault("structured_strategy", "tools")
        # Existing fixtures exercise the prior gateway adapter, explicitly.
        config.setdefault("text_model", "ollama/gpt-oss:120b")
        config.setdefault("image_model", "nb/nanobanana-flash")
        offline_video = config.pop("enable_video", False)
        settings = Settings(
            _env_file=None, database_path=tmp_path / f"{len(stores)}.sqlite3", **config
        )
        if offline_video:
            # Keep historical video parser/composition invariant tests offline.
            # Ordinary Settings validation can never enable an unsupported model.
            settings = settings.model_copy(update={"enable_video": True})
        store = Store(settings.database_path)
        stores.append(store)
        client = InferenceClient(
            settings,
            store,
            clock=FakeClock(),
            mock_transport=httpx.MockTransport(handler) if handler else None,
        )
        return client

    yield make
    for store in stores:
        store.close()
