"""AgentPathfinder v2 — Visual confirmation constants & formatting macros.

Every agent reply about task status uses these emoji/formatting helpers
for at-a-glance indicator: ✅ complete, ❌ failed, ⏳ running, etc.
"""

from typing import Dict, Any, List, Optional

# ── Core Status Emojis ──────────────────────────────────────────────
PASS         = "✅"
FAIL         = "❌"
WARN         = "⚠️"
SPINNER      = "⏳"
PENDING      = "○"
LOCK         = "🔒"
UNLOCK       = "🔓"
SHEILD       = "🛡️"
CHART        = "📊"
DASHBOARD    = "🖥️"
AGENT        = "🤖"
KEY          = "🔑"
CHECK        = "✓"
CROSS        = "✗"
ARROW        = "→"
BULLET       = "•"
STAR         = "⭐"
ROCKET       = "🚀"
INFO         = "ℹ️"
BELL         = "🔔"

# ── Step State Mapping ──────────────────────────────────────────────
STEP_ICONS = {
    "pending":   PENDING,
    "running":   SPINNER,
    "complete":  PASS,
    "failed":    FAIL,
}
STEP_COLORS = {
    "pending":   "#64748b",
    "running":   "#0ea5e9",
    "complete":  "#10b981",
    "failed":    "#ef4444",
}
STEP_EMOJI_COLOR = {
    "pending":   ("○", "dim"),
    "running":   ("⏳", "blue"),
    "complete":  ("✅", "green"),
    "failed":    ("❌", "red"),
}

# ── Task State Mapping ──────────────────────────────────────────────
TASK_ICONS = {
    "registered":            "📋",
    "in_progress":           SPINNER,
    "task_complete":         PASS,
    "paused":                WARN,
    "reconstruction_failed": FAIL,
    "aborted":               CROSS,
}

# ── Audit Result ───────────────────────────────────────────────────
AUDIT_OK   = f"{PASS} Audit integrity verified"
AUDIT_FAIL = f"{FAIL} Audit tampering detected"

# ── Reconstruction Result ──────────────────────────────────────────
RECON_OK   = f"{PASS} Key reconstructed successfully"
RECON_FAIL = f"{FAIL} Reconstruction failed — incomplete or tampered"

# ── Agent Auth ─────────────────────────────────────────────────────
AUTH_OK  = f"{PASS} Agent authenticated"
AUTH_FAIL = f"{FAIL} Agent authentication failed"

# ── Crash Recovery ─────────────────────────────────────────────────
CRASH_DETECTED = f"{WARN} Crash detected — step stuck in 'running'"
CRASH_RESET    = f"{PASS} Step reset to 'pending' for retry"

# ── Summary Badges ─────────────────────────────────────────────────
def badge_ok(text: str) -> str:
    return f"{PASS} {text}"

def badge_fail(text: str) -> str:
    return f"{FAIL} {text}"

def badge_warn(text: str):
    return f"{WARN} {text}"

def badge_info(text: str) -> str:
    return f"{INFO} {text}"

def badge_running(text: str) -> str:
    return f"{SPINNER} {text}"

# ── Terminal helpers (no colorama dep) ─────────────────────────────
ANSI = {
    "reset":    "\033[0m",
    "bold":     "\033[1m",
    "dim":      "\033[2m",
    "italic":   "\033[3m",
    "underline":"\033[4m",
    "red":      "\033[31m",
    "green":    "\033[32m",
    "yellow":   "\033[33m",
    "blue":     "\033[34m",
    "magenta":  "\033[35m",
    "cyan":     "\033[36m",
    "white":    "\033[37m",
    "bg_red":   "\033[41m",
    "bg_green": "\033[42m",
    "bg_yellow":"\033[43m",
}


def color(text: str, *codes: str) -> str:
    """Wrap text in ANSI color codes."""
    prefix = "".join(ANSI.get(c, "") for c in codes)
    return f"{prefix}{text}{ANSI['reset']}"


def dim(text: str) -> str:
    return color(text, "dim")


def bold(text: str) -> str:
    return color(text, "bold")


def green(text: str) -> str:
    return color(text, "green")


def red(text: str) -> str:
    return color(text, "red")


def yellow(text: str) -> str:
    return color(text, "yellow")


def blue(text: str) -> str:
    return color(text, "blue")


# ── Status Formatters ──────────────────────────────────────────────
def fmt_status(status: Dict[str, Any]) -> str:
    """Format a full task status dict into a visual, at-a-glance string."""
    lines = [
        "",
        f"{bold('Task:')} {status['name']} ({dim(status['task_id'])})",
        f"{bold('State:')} {fmt_state(status['overall_state'])}",
        f"{bold('Progress:')} {status['progress']}",
        "",
        bold("Steps:"),
    ]
    for step in status["steps"]:
        icon, color_name = STEP_EMOJI_COLOR.get(step["state"], ("?", "dim"))
        line = f"  {icon} Step {step['step_number']}: {step['name']}"
        if step.get("token_id"):
            line += f"  {dim('token:')}{dim(step['token_id'][:12])}…"
        if step.get("error"):
            line += f"  {red(step['error'][:60])}"
        lines.append(line)
    return "\n".join(lines)


def fmt_state(state: str) -> str:
    """Color-code a task state string."""
    mapping = {
        "task_complete":  green,
        "registered":     dim,
        "in_progress":    blue,
        "paused":         yellow,
        "reconstruction_failed": red,
        "aborted":        red,
    }
    return mapping.get(state, str)(state)


def fmt_audit_event(event: Dict[str, Any]) -> str:
    """Format a single audit event for display."""
    tamper = "OK" if event.get("tamper_ok") else "TAMPERED"
    ts = event.get("timestamp", "?")
    ev_type = event.get("event", "UNKNOWN")
    icon = PASS if event.get("tamper_ok") else FAIL
    return f"  [{ts}] {icon} {ev_type} [{tamper}]"


def fmt_step_complete(step_number: int, name: str, token_id: str = "") -> str:
    """Visual confirmation when a step completes."""
    tok = f" (token: {token_id[:12]}…)" if token_id else ""
    return f"{PASS} Step {step_number} complete: {name}{tok}"


def fmt_step_failed(step_number: int, name: str, error: str) -> str:
    """Visual indication when a step fails, with retry suggestion."""
    return (
        f"{FAIL} Step {step_number} failed: {name}\n"
        f"   {WARN} {error}\n"
        f"   {INFO} Suggestion: run  {bold('pf status <task_id>')}  then retry."
    )


def fmt_task_complete(name: str, task_id: str) -> str:
    return f"{PASS} {bold(name)} is complete! ID: {dim(task_id)}"


def fmt_task_failed(name: str, task_id: str, reason: str) -> str:
    return f"{FAIL} {bold(name)} failed. {reason}  ID: {dim(task_id)}"


def fmt_crash_recovery(step_number: int, name: str) -> str:
    return (
        f"{WARN} Crash recovery: Step {step_number} ({name}) was stuck in 'running'.\n"
        f"{CRASH_RESET}"
    )


def fmt_reconstruct_ok(key_hash: str) -> str:
    return f"{RECON_OK}\n   {dim('Key hash:')} {dim(key_hash[:16])}…"


def fmt_reconstruct_fail() -> str:
    return f"{RECON_FAIL}\n   {INFO} Not all steps finished. Check status."


def fmt_agent_registered(agent_id: str, api_key: str) -> str:
    masked = api_key[:8] + "…" + api_key[-8:]
    return (
        f"{PASS} Agent registered: {bold(agent_id)}\n"
        f"   {KEY} API key: {dim(masked)}"
    )


def fmt_dashboard_url(port: int) -> str:
    return f"{DASHBOARD} Dashboard live at {bold(f'http://localhost:{port}')}"


# ── Task Summary Visuals ─────────────────────────────────────────────
def fmt_task_summary(tasks: List[dict]) -> str:
    """Format task summary with visual badges."""
    count = len(tasks) if tasks else 0
    if not count:
        return f"  {INFO} No active tasks"
    
    complete = sum(1 for t in tasks if t.get("status") == "complete")
    lines = [
        "",
        f"{CHART} {bold('Task Summary')}",
        f"  {PASS} Active tasks:     {count}",
        f"  {PASS} Complete:         {complete}",
        f"  {SPINNER} In progress:      {count - complete}",
    ]
    return "\n".join(lines)


def fmt_install_ready() -> str:
    """The 'we're ready' banner."""
    return (
        f"\n{ROCKET} {bold(color('AgentPathfinder Ready!', 'green', 'bold'))}\n"
        f"   {PASS} Skill installed\n"
        f"   {PASS} Data directory initialized\n"
        f"   {DASHBOARD} Dashboard:  {bold('pf dashboard')}\n"
        f"   {INFO} Quick start:  {bold('pf create my_task step1 step2')}\n"
        f"\n{faint('All data stays in ~/.agentpathfinder — no external servers.')}\n"
    )


def fmt_box(title: str, body_lines: List[str], width: int = 58) -> str:
    """Draw a simple ASCII box."""
    top = "┌" + "─" * (width - 2) + "┐"
    mid = "│ " + title.ljust(width - 4) + " │"
    sep = "├" + "─" * (width - 2) + "┤"
    bot = "└" + "─" * (width - 2) + "┘"
    lines = [top, mid, sep]
    for line in body_lines:
        lines.append("│ " + line.ljust(width - 4) + " │")
    lines.append(bot)
    return "\n".join(lines)
