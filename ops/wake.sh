#!/usr/bin/env bash
# Wake the desk. Called by cron (schedule) and by the watcher (escalations).
#
#   ops/wake.sh CHECK
#   ops/wake.sh ESCALATION "ADA down 4.2% in 1h"
#   ops/wake.sh DAILY_REVIEW
#   ops/wake.sh RESEARCH
#
# Runs Claude Code headless with the desk lead as the main agent. Only one desk
# session runs at a time; a wake that arrives during a session waits up to 10
# minutes, except CHECK, which is simply skipped.
#
# Setup notes (verify on the VPS when the brain container is built):
#   - Auth: CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token`, set in the brain
#     container's environment, never in this repo.
#   - Confirm `claude --help` lists --agent and --max-turns on the installed
#     version. If --agent is missing, start the session with the desk lead's
#     instructions through --append-system-prompt instead.

set -euo pipefail

TIER="${1:?usage: wake.sh TIER [reason]}"
REASON="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CLAUDE_PROJECT_DIR="$ROOT"
cd "$ROOT"

LOG_DIR="$ROOT/logs/wakes"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/$STAMP-$TIER.json"
LOCK="$ROOT/logs/desk.lock"

case "$TIER" in
  CHECK)        TURNS=15; WAIT=0 ;;
  ESCALATION)   TURNS=60; WAIT=600 ;;
  DAILY_REVIEW) TURNS=80; WAIT=600 ;;
  RESEARCH)     TURNS=60; WAIT=0 ;;
  BUILD)        TURNS=150; WAIT=600 ;;
  *) echo "unknown tier: $TIER" >&2; exit 2 ;;
esac

# Scheduled CHECK and RESEARCH wakes run only when due (pace follows the analyst's last call).
if [ "$TIER" = "CHECK" ] || [ "$TIER" = "RESEARCH" ]; then
  if ! python3 ops/due.py "$TIER"; then
    exit 0
  fi
fi

# Ask the usage governor before spending anything.
if ! python3 .claude/hooks/usage_governor.py --allow "$TIER"; then
  echo "$STAMP $TIER skipped: usage window" >> "$ROOT/logs/wakes.log"
  exit 0
fi

PROMPT="Wake: $TIER."
if [ -n "$REASON" ]; then
  PROMPT="$PROMPT Reason from the watcher: $REASON"
fi
PROMPT="$PROMPT Usage window: $(python3 .claude/hooks/usage_governor.py --status)"

exec 9>"$LOCK"
if ! flock -w "$WAIT" 9; then
  echo "$STAMP $TIER skipped: another desk session is running" >> "$ROOT/logs/wakes.log"
  exit 0
fi

claude -p "$PROMPT" \
  --agent desk-lead \
  --max-turns "$TURNS" \
  --output-format json \
  > "$LOG" 2>&1 || echo "$STAMP $TIER exited non-zero, see $LOG" >> "$ROOT/logs/wakes.log"

echo "$STAMP $TIER done" >> "$ROOT/logs/wakes.log"
