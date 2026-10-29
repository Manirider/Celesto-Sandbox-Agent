import re

BLOCKED_PATTERNS = [
    re.compile(r"\b(curl|wget)\b", re.IGNORECASE),
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+(/|\*)", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\s+", re.IGNORECASE),
    re.compile(r"\b(mkdir\s+/root|chmod\s+777\s+/)", re.IGNORECASE),
    re.compile(r":\s*;\s*rm\b", re.IGNORECASE),
    re.compile(r"\b(shutdown|reboot|poweroff|init\s+0)\b", re.IGNORECASE),
]

def authorize_command(command: str) -> bool:
    """Pre-execution security hook for sandboxed agent commands."""
    if not command or not isinstance(command, str):
        return False
    # Strip leading/trailing whitespace
    cmd = command.strip()
    if not cmd:
        return False
    # Check blocked patterns
    for pat in BLOCKED_PATTERNS:
        if pat.search(cmd):
            return False
    return True
