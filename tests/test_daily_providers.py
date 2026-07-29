import json
from io import BytesIO

import pytest

from backend.daily import providers
from backend.daily.providers import FinnhubDailyProvider


class _Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def test_finnhub_api_key_is_read_from_centralized_settings(monkeypatch):
    calls = []

    def fake_get_setting(name):
        calls.append(name)
        return "centralized-key"

    monkeypatch.setattr(providers, "get_setting", fake_get_setting)

    provider = FinnhubDailyProvider()

    assert provider.api_key == "centralized-key"
    assert calls == ["FINNHUB_API_KEY"]


def test_finnhub_behavior_is_preserved_when_key_exists(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "secret-key")
    requests = []

    def opener(url, timeout):
        requests.append((url, timeout))
        return _Response(json.dumps({"status": "ok"}).encode())

    provider = FinnhubDailyProvider(opener=opener)

    assert provider._get("test", symbol="NVDA") == {"status": "ok"}
    assert requests == [
        ("https://finnhub.io/api/v1/test?symbol=NVDA&token=secret-key", 10)
    ]


def test_finnhub_behavior_is_preserved_when_key_is_absent(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    provider = FinnhubDailyProvider()

    with pytest.raises(RuntimeError, match="^FINNHUB_API_KEY não configurada$"):
        provider._get("test")


def test_explicit_finnhub_api_key_still_bypasses_settings(monkeypatch):
    def unexpected_get_setting(name):
        pytest.fail(f"get_setting was unexpectedly called for {name}")

    monkeypatch.setattr(providers, "get_setting", unexpected_get_setting)

    provider = FinnhubDailyProvider(api_key="explicit-key")

    assert provider.api_key == "explicit-key"
