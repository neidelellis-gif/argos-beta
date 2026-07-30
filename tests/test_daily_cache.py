from pathlib import Path

from backend.daily.cache import DailyCache


def test_cache_uses_centralized_settings(monkeypatch):
    settings = {
        "ARGOS_DAILY_CACHE_DIR": "configured/cache",
        "ARGOS_DAILY_CACHE_TTL_SECONDS": "1200",
    }
    monkeypatch.setattr(
        "backend.daily.cache.get_setting",
        lambda name, default: settings.get(name, default),
    )

    cache = DailyCache()

    assert cache.directory == Path("configured/cache")
    assert cache.ttl_seconds == 1200


def test_cache_preserves_default_settings(monkeypatch):
    monkeypatch.setattr(
        "backend.daily.cache.get_setting",
        lambda name, default: default,
    )

    cache = DailyCache()

    assert cache.directory == Path(".cache/daily")
    assert cache.ttl_seconds == 900


def test_cache_treats_empty_ttl_setting_as_default(monkeypatch):
    monkeypatch.setattr(
        "backend.daily.cache.get_setting",
        lambda name, default: (
            "" if name == "ARGOS_DAILY_CACHE_TTL_SECONDS" else default
        ),
    )

    cache = DailyCache()

    assert cache.ttl_seconds == 900
