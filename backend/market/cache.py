from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Dict, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """Small in-memory, thread-safe TTL cache."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        self._ttl_seconds = ttl_seconds
        self._entries: Dict[str, _CacheEntry[T]] = {}
        self._lock = RLock()

    def get(self, key: str) -> Optional[T]:
        now = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._entries[key] = _CacheEntry(
                value=value,
                expires_at=monotonic() + self._ttl_seconds,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
