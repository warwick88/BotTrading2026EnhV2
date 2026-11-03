"""Is a scheduled wake due? Used by ops/wake.sh before CHECK and RESEARCH.

    python3 ops/due.py CHECK      # exit 0 if the analyst's next check is due
    python3 ops/due.py RESEARCH   # exit 0 if the market is quiet enough for research

The analyst writes market/<YYYYMMDD-HHMM>.md starting with a MARKET: line. The newest
one sets the pace from config/cadence.yaml: calm 4h, normal 2h, hot 1h. ALERT means
check every hour. With no note yet, everything is due.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACE_KEYS = {"CALM": "calm_every_hours", "NORMAL": "normal_every_hours",
             "HOT": "hot_every_hours", "ALERT": "hot_every_hours"}
DEFAULT_PACE = {"calm_every_hours": 4, "normal_every_hours": 2, "hot_every_hours": 1}
QUIET = {"CALM", "NORMAL"}


def cadence() -> dict:
    try:
        import yaml
        with open(ROOT / "config" / "cadence.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def last_call() -> tuple[str | None, float]:
    notes = sorted((ROOT / "market").glob("*.md"))
    if not notes:
        return None, float("inf")
    newest = notes[-1]
    label = None
    for line in newest.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().strip("*").strip()
        if line.startswith("MARKET:"):
            words = line[len("MARKET:"):].split()
            label = words[0].strip("*.`") if words else None
            break
    age_hours = (time.time() - newest.stat().st_mtime) / 3600
    return label, age_hours


def main() -> None:
    tier = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    label, age = last_call()
    config = cadence()
    if tier == "CHECK":
        if label is None:
            sys.exit(0)
        pace = {**DEFAULT_PACE, **(config.get("analyst_check") or {})}
        hours = pace[PACE_KEYS.get(label, "normal_every_hours")]
        # Ten minutes of slack so an hourly cron doesn't miss by seconds.
        sys.exit(0 if age >= hours - 1 / 6 else 1)
    if tier == "RESEARCH":
        allowed = set((config.get("research") or {}).get("only_when_market") or QUIET)
        sys.exit(0 if label in allowed else 1)
    sys.exit(0)


if __name__ == "__main__":
    main()
