"""Persistent last-good cache for ARGOS historical market prices."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from .models import PriceHistory, PricePoint


class PersistentHistoryCache:
    schema_version = 1

    def __init__(self, cache_dir: Path, *, ttl_seconds: int, clock: Callable[[], float] | None = None) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer")
        self._cache_dir = Path(cache_dir)
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.time

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"

    @staticmethod
    def _history_to_payload(history: PriceHistory) -> dict[str, object]:
        return {
            "ticker": history.ticker,
            "currency": history.currency,
            "provider": history.provider,
            "status": history.status,
            "error": history.error,
            "points": [{"date": p.date, "close": p.close} for p in history.points],
        }

    @staticmethod
    def _history_from_payload(payload: object) -> Optional[PriceHistory]:
        if not isinstance(payload, dict):
            return None
        ticker = payload.get("ticker")
        provider = payload.get("provider")
        status = payload.get("status")
        raw_points = payload.get("points")
        if not isinstance(ticker, str) or not ticker.strip() or not isinstance(provider, str) or status != "ok" or not isinstance(raw_points, list) or not raw_points:
            return None
        points: list[PricePoint] = []
        for item in raw_points:
            if not isinstance(item, dict) or not isinstance(item.get("date"), str):
                return None
            try:
                close = float(item.get("close"))
            except (TypeError, ValueError):
                return None
            if close <= 0:
                return None
            points.append(PricePoint(date=item["date"], close=close))
        currency = payload.get("currency")
        if currency is not None and not isinstance(currency, str):
            return None
        error = payload.get("error")
        if error is not None and not isinstance(error, str):
            return None
        return PriceHistory(
            ticker=ticker.upper().strip(), currency=currency, provider=provider,
            points=tuple(points), status="ok", error=error,
        )

    def _read_entry(self, key: str) -> Optional[tuple[float, PriceHistory]]:
        try:
            raw = json.loads(self._path_for(key).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict) or raw.get("schema_version") != self.schema_version:
            return None
        try:
            cached_at = float(raw.get("cached_at"))
        except (TypeError, ValueError):
            return None
        history = self._history_from_payload(raw.get("history"))
        return None if history is None else (cached_at, history)

    def get(self, key: str) -> Optional[PriceHistory]:
        entry = self._read_entry(key)
        if entry is None:
            return None
        cached_at, history = entry
        return None if self._clock() - cached_at >= self._ttl_seconds else history

    def get_stale(self, key: str) -> Optional[PriceHistory]:
        entry = self._read_entry(key)
        return None if entry is None else entry[1]

    def set(self, key: str, history: PriceHistory) -> bool:
        if history.status != "ok" or not history.points:
            return False
        payload = {
            "schema_version": self.schema_version,
            "cached_at": self._clock(),
            "history": self._history_to_payload(history),
        }
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".history-", suffix=".tmp", dir=self._cache_dir)
            temp_path = Path(temp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self._path_for(key))
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        except OSError:
            return False
        return True

    def clear(self) -> None:
        try:
            if not self._cache_dir.exists():
                return
            for path in self._cache_dir.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
        except OSError:
            pass
