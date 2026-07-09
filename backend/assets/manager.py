import json
from pathlib import Path

ASSET_MASTER_PATH = Path(__file__).with_name("asset_master.json")


def _clean(value):
    if value is None:
        return ""
    return str(value).strip().upper()


def load_asset_master():
    with open(ASSET_MASTER_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def build_alias_index():
    asset_master = load_asset_master()
    alias_index = {}

    for canonical, data in asset_master.items():
        alias_index[_clean(canonical)] = canonical
        alias_index[_clean(data.get("ticker"))] = canonical
        alias_index[_clean(data.get("name"))] = canonical

        for alias in data.get("aliases", []):
            alias_index[_clean(alias)] = canonical

    return alias_index


def normalize_position(position):
    alias_index = build_alias_index()

    raw_symbol = _clean(position.get("symbol"))
    raw_name = _clean(position.get("name"))
    raw_description = _clean(position.get("description"))

    candidates = [raw_symbol, raw_name, raw_description]

    for candidate in candidates:
        if candidate and candidate != "N/A" and candidate in alias_index:
            canonical = alias_index[candidate]
            normalized = dict(position)
            normalized["symbol"] = canonical
            normalized["name"] = canonical
            return normalized

    fallback = raw_symbol if raw_symbol and raw_symbol != "N/A" else raw_name or raw_description or "UNKNOWN"

    normalized = dict(position)
    normalized["symbol"] = fallback
    normalized["name"] = fallback
    return normalized
