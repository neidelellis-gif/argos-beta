"""Small file cache for normalized daily provider results."""

from pathlib import Path
import pickle

from backend.config.settings import get_setting
from backend.daily.models import ExternalDataResult


class DailyCache:
    def __init__(self, directory=None, ttl_seconds=None):
        self.directory = Path(directory or get_setting("ARGOS_DAILY_CACHE_DIR", ".cache/daily"))
        configured_ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else get_setting("ARGOS_DAILY_CACHE_TTL_SECONDS", "900")
        )
        self.ttl_seconds = int(str(configured_ttl).strip() or "900")

    def _path(self, kind):
        return self.directory / f"{kind}.pickle"

    def put(self, kind, result, now):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._path(kind).open("wb") as file_obj:
            pickle.dump({"saved_at": now, "result": result}, file_obj)

    def _read(self, kind):
        try:
            with self._path(kind).open("rb") as file_obj:
                return pickle.load(file_obj)
        except (OSError, EOFError, pickle.PickleError):
            return None

    def get_fresh(self, kind, now):
        record = self._read(kind)
        if not record or (now - record["saved_at"]).total_seconds() > self.ttl_seconds:
            return None
        result = record["result"]
        return ExternalDataResult(result.status, result.items, True, result.error)

    def get_last_valid(self, kind):
        record = self._read(kind)
        if not record:
            return None
        result = record["result"]
        return result if result.status in {"available", "empty"} else None
