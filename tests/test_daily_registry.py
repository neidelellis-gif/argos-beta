"""Tests for the configured daily-provider registry."""

import backend.daily.registry as registry_module


class Provider:
    def __init__(self, name):
        self.name = name


def _factory(name):
    return lambda: Provider(name)


def test_build_default_registry_uses_centralized_setting(monkeypatch):
    calls = []

    def get_setting(name, default):
        calls.append((name, default))
        return "configured"

    monkeypatch.setattr(registry_module, "get_setting", get_setting)
    monkeypatch.setitem(
        registry_module._PROVIDER_FACTORIES,
        "configured",
        _factory("configured"),
    )

    built = registry_module.build_default_registry()

    assert calls == [("ARGOS_DAILY_PROVIDERS", "finnhub")]
    assert [provider.name for provider in built.providers] == ["configured"]


def test_build_default_registry_preserves_original_default(monkeypatch):
    captured = {}

    def get_setting(name, default):
        captured["default"] = default
        return default

    monkeypatch.setattr(registry_module, "get_setting", get_setting)
    monkeypatch.setitem(
        registry_module._PROVIDER_FACTORIES,
        "finnhub",
        _factory("finnhub"),
    )

    built = registry_module.build_default_registry()

    assert captured["default"] == "finnhub"
    assert [provider.name for provider in built.providers] == ["finnhub"]


def test_build_default_registry_preserves_provider_list_processing(monkeypatch):
    monkeypatch.setattr(
        registry_module,
        "get_setting",
        lambda name, default: " Second, ,FIRST,second ",
    )
    monkeypatch.setitem(
        registry_module._PROVIDER_FACTORIES,
        "first",
        _factory("first"),
    )
    monkeypatch.setitem(
        registry_module._PROVIDER_FACTORIES,
        "second",
        _factory("second"),
    )

    built = registry_module.build_default_registry()

    assert [provider.name for provider in built.providers] == [
        "second",
        "first",
        "second",
    ]


def test_build_default_registry_preserves_empty_and_absent_behavior(monkeypatch):
    monkeypatch.setitem(
        registry_module._PROVIDER_FACTORIES,
        "finnhub",
        _factory("finnhub"),
    )
    monkeypatch.setattr(
        registry_module,
        "get_setting",
        lambda name, default: "",
    )
    empty = registry_module.build_default_registry()

    monkeypatch.setattr(
        registry_module,
        "get_setting",
        lambda name, default: default,
    )
    absent = registry_module.build_default_registry()

    assert empty.providers == ()
    assert [provider.name for provider in absent.providers] == ["finnhub"]
