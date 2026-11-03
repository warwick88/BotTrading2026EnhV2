"""Usage governor: keep the desk inside the Claude Pro usage window.

Two ways to run it:

1. As a PreToolUse hook on the desk lead's Agent tool (wired in desk-lead.md). It
   reads which specialist is about to be dispatched and refuses research when the
   window is half spent, and everything but the analyst and risk officer when it is
   mostly spent.
2. From the wake script, before a session starts:
       python3 .claude/hooks/usage_governor.py --status        # prints JSON, always exit 0
       python3 .claude/hooks/usage_governor.py --allow RESEARCH # exit 0 if allowed, 1 if not

Pro does not publish its limits as token counts, so the budget in
config/cadence.yaml is an estimate. Tokens are read from Claude Code's own
transcripts under ~/.claude/projects/, weighted (cache reads at 10%), over the
rolling window. Calibrate the budget after a week of real runs.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULTS = {
    "window_hours": 5,
    "budget_weighted_tokens": 1_500_000,
    "research_stops_at_pct": 50,
    "essentials_only_at_pct": 80,
}
RESEARCH_AGENTS = {"quant-researcher"}
ESSENTIAL_AGENTS = {"market-analyst", "risk-officer"}
# Wake tiers and the level at which they stop being allowed.
TIER_CEILING = {"RESEARCH": "research", "BUILD": "research", "DAILY_REVIEW": "essentials",
                "ESCALATION": None, "CHECK": None}


def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


def load_config(root: Path) -> dict:
    config = dict(DEFAULTS)
    try:
        import yaml  # PyYAML is in the brain container's requirements
        with open(root / "config" / "cadence.yaml", encoding="utf-8") as f:
            config.update((yaml.safe_load(f) or {}).get("usage") or {})
    except Exception:
        pass  # fall back to the conservative defaults
    return config


def transcripts_dir(root: Path) -> Path:
    slug = "".join(c if c.isalnum() else "-" for c in str(root))
    return Path.home() / ".claude" / "projects" / slug


def line_time(entry: dict, fallback: float) -> float:
    stamp = entry.get("timestamp")
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return fallback


def weighted_tokens(root: Path, window_hours: float) -> int:
    since = time.time() - window_hours * 3600
    folder = transcripts_dir(root)
    if not folder.exists():
        return 0
    final: dict[str, tuple[float, dict]] = {}
    for path in folder.rglob("*.jsonl"):
        mtime = path.stat().st_mtime
        if mtime < since:
            continue
        with open(path, encoding="utf-8", errors="replace") as lines:
            for raw in lines:
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                message = entry.get("message") or {}
                if message.get("usage") and message.get("id"):
                    # Streaming writes partial usage first; keep the last per response.
                    final[message["id"]] = (line_time(entry, mtime), message["usage"])
    total = 0
    for when, usage in final.values():
        if when < since:
            continue
        total += usage.get("input_tokens", 0)
        total += usage.get("cache_creation_input_tokens", 0)
        total += usage.get("output_tokens", 0)
        total += usage.get("cache_read_input_tokens", 0) // 10
    return total


def status(root: Path) -> dict:
    config = load_config(root)
    used = weighted_tokens(root, config["window_hours"])
    pct = round(100 * used / max(config["budget_weighted_tokens"], 1), 1)
    if pct >= config["essentials_only_at_pct"]:
        level = "essentials"
    elif pct >= config["research_stops_at_pct"]:
        level = "research"
    else:
        level = "open"
    return {"used_weighted_tokens": used, "budget": config["budget_weighted_tokens"],
            "pct": pct, "restricted": level}


def tier_allowed(tier: str, current: str) -> bool:
    ceiling = TIER_CEILING.get(tier, "research")
    if ceiling is None:
        return True
    order = {"open": 0, "research": 1, "essentials": 2}
    return order[current] < order[ceiling]


def main() -> None:
    root = project_root()
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        print(json.dumps(status(root)))
        sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[1] == "--allow":
        s = status(root)
        sys.exit(0 if tier_allowed(sys.argv[2].upper(), s["restricted"]) else 1)

    # Hook mode.
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Agent":
        sys.exit(0)
    target = (payload.get("tool_input") or {}).get("subagent_type", "")
    s = status(root)
    if s["restricted"] == "research" and target in RESEARCH_AGENTS:
        print(f"Usage governor: {s['pct']}% of the usage window is spent. Research waits for "
              "the window to roll over. Note it in desk/research-queue.md.", file=sys.stderr)
        sys.exit(2)
    if s["restricted"] == "essentials" and target not in ESSENTIAL_AGENTS:
        print(f"Usage governor: {s['pct']}% of the usage window is spent. Only the market "
              "analyst and risk officer run now. Protect positions with what you have, log "
              "what is waiting, and stop.", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
