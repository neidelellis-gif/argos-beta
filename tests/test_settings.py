import os

import pytest

from backend.config import MissingSettingError, get_setting, require_setting


def test_get_setting_reads_environment(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "secret-key")

    assert get_setting("FINNHUB_API_KEY") == "secret-key"


def test_get_setting_returns_default_when_absent(monkeypatch):
    monkeypatch.delenv("OPTIONAL_SETTING", raising=False)

    assert get_setting("OPTIONAL_SETTING", "fallback") == "fallback"


def test_get_setting_reads_environment_at_call_time(monkeypatch):
    monkeypatch.setenv("DYNAMIC_SETTING", "first")
    assert get_setting("DYNAMIC_SETTING") == "first"

    monkeypatch.setenv("DYNAMIC_SETTING", "second")
    assert get_setting("DYNAMIC_SETTING") == "second"


def test_require_setting_reads_environment(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "secret-key")

    assert require_setting("FINNHUB_API_KEY") == "secret-key"


def test_require_setting_raises_clear_error_when_absent(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    with pytest.raises(
        MissingSettingError,
        match="Required environment variable 'FINNHUB_API_KEY' is not set",
    ):
        require_setting("FINNHUB_API_KEY")


def test_settings_do_not_write_to_output(monkeypatch, capsys):
    monkeypatch.setenv("PRESENT_SETTING", "value")
    monkeypatch.delenv("ABSENT_SETTING", raising=False)

    get_setting("PRESENT_SETTING")
    get_setting("ABSENT_SETTING", "default")
    with pytest.raises(MissingSettingError):
        require_setting("ABSENT_SETTING")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_settings_use_os_environ(monkeypatch):
    monkeypatch.setitem(os.environ, "DIRECT_ENVIRON_SETTING", "value")

    assert require_setting("DIRECT_ENVIRON_SETTING") == "value"
