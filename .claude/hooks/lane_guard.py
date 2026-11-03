"""PreToolUse hook: keep each agent in its own lane, and keep every agent away from
the exchange, the secrets and the safety files.

Each agent file wires this script with its name as the only argument:
    python3 .claude/hooks/lane_guard.py <agent-name>
Claude Code passes the pending tool call as JSON on stdin. Exit code 2 blocks the
call, and stderr goes back to the agent as the reason.

File tools are checked exactly. Shell commands are checked on a best effort basis,
which catches honest mistakes; the hard guarantees are the tool allowlists in the
agent files, the deny rules in settings.json, the read-only database role, and the
fact that only the engine container holds the exchange keys.
"""

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

MEMORY = ".claude/agent-memory/{}/*"

LANES = {
    "desk-lead": ["desk/*"],
    "market-analyst": ["market/*"],
    "market-strategist": ["strategies/*", "opportunities/*", "docs/playbook.md"],
    "quant-researcher": ["research/*"],
    "risk-officer": ["risk/*"],
    "engine-developer": [
        "engine/*",
        "collector/*",
        "watcher/*",
        "scripts/*",
        "tests/*",
        "docs/schema.md",
        "Dockerfile*",
        "docker-compose*.yml",
        ".dockerignore",
        ".env.example",
        "requirements*.txt",
        "pyproject.toml",
        "pytest.ini",
    ],
}
for name, patterns in LANES.items():
    patterns.append(MEMORY.format(name))

# Nobody writes these, whatever their lane. Checked before the lanes.
FORBIDDEN = [
    "CLAUDE.md",
    ".claude/agents/*",
    ".claude/hooks/*",
    ".claude/settings*.json",
    "config/limits.yaml",
    "config/cadence.yaml",
    "config/fees.yaml",
    "engine/guard.py",
    "docs/known-failures.md",
    "ops/*",
    ".env",
    ".env.*",
]
# .env.example is the one exception to the .env rule.
FORBIDDEN_EXCEPT = [".env.example"]

OWNERS = [
    ("desk/*", "the desk lead"),
    ("market/*", "the market analyst"),
    ("strategies/*", "the market strategist"),
    ("opportunities/*", "the market strategist"),
    ("docs/playbook.md", "the market strategist"),
    ("research/*", "the quant researcher"),
    ("risk/*", "the risk officer"),
    ("engine/*", "the engine developer"),
    ("collector/*", "the engine developer"),
    ("watcher/*", "the engine developer"),
    ("scripts/*", "the engine developer"),
    ("tests/*", "the engine developer"),
    ("docs/schema.md", "the engine developer"),
]

FILE_TOOLS = {"Write", "Edit", "NotebookEdit"}

# Only the engine developer changes files or installs things from the shell.
# Everyone else may run scripts (which write their own output) but not write directly.
SHELL_WRITERS = {"engine-developer"}

WRITE_PATTERNS = [
    r"(?<![0-9&])>(?!\s*/dev/null)(?!&)",
    r"\btee\b",
    r"\bsed\s+-i\b",
    r"\b(rm|mv|cp|touch|mkdir|rmdir|chmod|chown|truncate|ln)\b",
    r"\bgit\s+(commit|checkout|reset|restore|clean|stash|merge|rebase|apply)\b",
    r"\b(pip|pip3|uv|npm|npx)\s+(install|add|uninstall|remove)\b",
]

# Nobody runs these from the shell.
OFF_LIMITS = [
    (r"(?<![\w.])\.env(?!\.example)(?![\w-])", "reads or names .env, which holds the secrets"),
    (r"\bgit\s+push\b", "pushes to a remote; only Warwick does that"),
    (r"\bdocker\b|\bpodman\b", "controls containers; deploys happen outside the agents' reach"),
    (r"api\.binance\.", "talks to the exchange API; only the engine does that"),
    (r"\b(curl|wget)\b", "fetches from the network outside the web tools; use WebFetch"),
    (r"\bprintenv\b|\benv\s*$|\benv\s*\|", "dumps environment variables, which can hold secrets"),
    (r"BINANCE_API|GMAIL_APP|SMTP_PASS", "names a secret"),
]

QUOTED = re.compile(r"'[^']*'" + r'|"(?:\\.|[^"\\])*"')


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def project_root(payload: dict) -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(root).resolve()


def relative(path_str: str, root: Path) -> str | None:
    path = Path(path_str)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def matches(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def owner_of(rel: str) -> str:
    for pattern, owner in OWNERS:
        if fnmatch.fnmatch(rel, pattern):
            return owner
    return "nobody on the desk (it is setup, safety, or Warwick's)"


def check_file_tool(role: str, tool_input: dict, root: Path) -> None:
    target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    rel = relative(target, root)
    if rel is None:
        block(f"Lane guard: {target} is outside the project. Nobody on the desk writes there.")
    if matches(rel, FORBIDDEN) and not matches(rel, FORBIDDEN_EXCEPT):
        block(
            f"Lane guard: {rel} is setup, safety or secrets, and no agent writes it. "
            "If it looks wrong, say so in your report to the desk lead."
        )
    if not matches(rel, LANES[role]):
        block(
            f"Lane guard: the {role} does not write {rel}. It belongs to {owner_of(rel)}. "
            "Do not work around this. Put what you need in your report and the desk lead will route it."
        )


def check_bash(role: str, command: str) -> None:
    for pattern, why in OFF_LIMITS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            block(f"Lane guard: no agent runs this, because it {why}. Command: {command!r}")
    if role in SHELL_WRITERS:
        return
    bare = QUOTED.sub("''", command)
    if any(re.search(p, bare) for p in WRITE_PATTERNS):
        block(
            f"Lane guard: the {role} does not change files or install anything from the shell, "
            f"and this looks like it would: {command!r}. Use the Write or Edit tool inside your "
            "own folder, or run a script that writes its own output."
        )


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role not in LANES:
        block(f"Lane guard misconfigured: unknown agent {role!r}.")
    payload = json.load(sys.stdin)
    # When the desk lead is the main session, the hooks in its file see every
    # subagent's calls too. Each agent has its own guard, so judge only our own.
    caller = payload.get("agent_type")
    if caller and caller != role:
        sys.exit(0)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if tool in FILE_TOOLS:
        check_file_tool(role, tool_input, project_root(payload))
    elif tool == "Bash":
        check_bash(role, tool_input.get("command", ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
