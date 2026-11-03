"""Stop hook (runs as SubagentStop): a specialist cannot hand back a sloppy report.

Wired in each specialist's file:
    python3 .claude/hooks/report_gate.py <agent-name>

The desk lead reads hand-backs section by section, and the plan and promotion scripts
read the verdict lines, so a missing section or verdict is refused (exit code 2, the
reason on stderr) and the agent is told what to fix. The engine developer's tests must
also pass. A stuck agent is never trapped: on the second stop attempt it goes through.
"""

import json
import os
import subprocess
import sys

REQUIRED = {
    "market-analyst": ["MARKET:", "## Read", "## Changed", "## Escalate"],
    "market-strategist": ["## Proposal", "## Thesis", "## Exits", "## Known failures", "## Costs"],
    "quant-researcher": ["RESULT:", "## Numbers", "## Method", "## Caveats"],
    "risk-officer": ["RISK:", "## Findings"],
    "engine-developer": ["## Built", "## Not built", "## Tests"],
}
VERDICTS = {
    "MARKET:": {"CALM", "NORMAL", "HOT", "ALERT"},
    "RESULT:": {"PASS", "FAIL", "INCONCLUSIVE"},
    "RISK:": {"APPROVE", "REJECT"},
}


def last_message(payload: dict) -> str:
    """The agent's final text: from the payload if this version sends it, else its transcript."""
    if payload.get("last_assistant_message"):
        return payload["last_assistant_message"]
    path = payload.get("agent_transcript_path") or payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return ""
    text = ""
    with open(path, encoding="utf-8") as transcript:
        for line in transcript:
            try:
                message = json.loads(line).get("message") or {}
            except ValueError:
                continue
            content = message.get("content")
            if message.get("role") != "assistant" or not isinstance(content, list):
                continue
            parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            if any(p.strip() for p in parts):
                text = "\n".join(parts)
    return text


def verdict_problem(word: str, allowed: set[str], message: str) -> str | None:
    for line in message.splitlines():
        line = line.strip().strip("*").strip()
        if line.startswith(word):
            value = line[len(word):].strip().strip("*.`").split()
            if value and value[0] in allowed:
                return None
            break
    return f"Start a line with {word} followed by exactly one of {', '.join(sorted(allowed))}."


def tests_pass(root: str) -> tuple[bool, str]:
    if not os.path.isdir(os.path.join(root, "tests")):
        return False, "There is no tests/ folder. Everything you build needs tests."
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
            cwd=root, capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "The tests took more than 10 minutes and were stopped."
    out = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode == 0, "\n".join(out.splitlines()[-15:])


def problems_with(role: str, message: str, root: str) -> list[str]:
    problems = []
    missing = [s for s in REQUIRED.get(role, []) if s not in message]
    if missing:
        problems.append(
            "Your hand-back is missing: " + ", ".join(missing)
            + ". Use the report format from your instructions."
        )
    for word, allowed in VERDICTS.items():
        if word in REQUIRED.get(role, []) and word not in missing:
            problem = verdict_problem(word, allowed, message)
            if problem:
                problems.append(problem)
    if role == "engine-developer":
        ok, tail = tests_pass(root)
        if not ok:
            problems.append("The tests are not green. Fix them, or explain under ## Tests why not:")
            problems.append(tail)
    return problems


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = json.load(sys.stdin)
    if role not in REQUIRED:
        sys.exit(0)
    # Second stop attempt: let it through rather than trap the agent.
    if payload.get("stop_hook_active"):
        sys.exit(0)
    caller = payload.get("agent_type")
    if caller and caller != role:
        sys.exit(0)
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    problems = problems_with(role, last_message(payload), root)
    if problems:
        print("Hand-back refused.\n" + "\n".join(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
