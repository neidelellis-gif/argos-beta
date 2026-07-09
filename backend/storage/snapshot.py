import json
from datetime import datetime
from pathlib import Path

SNAPSHOT_DIR = Path("backend/storage/snapshots")
LATEST_FILE = SNAPSHOT_DIR / "latest.json"


def save_snapshot(portfolio):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": "UBS",
        "total": portfolio["total"],
        "positions_count": portfolio["positions_count"],
        "high_priority": portfolio["high_priority"],
        "medium_priority": portfolio["medium_priority"],
    }

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dated_file = SNAPSHOT_DIR / f"{timestamp}.json"

    with open(dated_file, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, indent=2, ensure_ascii=False)

    with open(LATEST_FILE, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, indent=2, ensure_ascii=False)

    return dated_file