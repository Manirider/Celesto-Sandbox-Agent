import re
from app import audit

try:
    from celesto import Callback, CommandBlockedError
except ImportError:
    class Callback:
        """Base callback class compatible with Celesto SDK specification."""
        def on_pre_run(self, ctx):
            pass

        def on_post_run(self, ctx):
            pass

        def on_run_error(self, ctx):
            pass

    class CommandBlockedError(PermissionError):
        """Raised when a command is blocked by on_pre_run safety hooks."""
        def __init__(self, message: str, vm_id: str = "", command: str = ""):
            super().__init__(message)
            self.vm_id = vm_id
            self.command = command


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


class CelestoSafetyGuard(Callback):
    """
    Official Celesto Callback hook implementation.
    Reference: https://celesto.ai/docs/smolvm/features/callbacks
    
    Inspects commands in on_pre_run, halts unauthorized instructions,
    and logs immutable audit events in on_post_run and on_run_error.
    """
    def __init__(self, sandbox_name: str = "sandbox"):
        self.sandbox_name = sandbox_name

    def on_pre_run(self, ctx):
        cmd = getattr(ctx, "command", "") or ""
        vm_id = getattr(ctx, "vm_id", self.sandbox_name) or self.sandbox_name
        if not authorize_command(cmd):
            audit.log_command(self.sandbox_name, cmd, "block", "celesto_sandbox")
            raise CommandBlockedError(
                f"Blocked unsafe command: {cmd!r}",
                vm_id=vm_id,
                command=cmd,
            )

    def on_post_run(self, ctx):
        cmd = getattr(ctx, "command", "") or ""
        audit.log_command(self.sandbox_name, cmd, "allow", "celesto_sandbox")

    def on_run_error(self, ctx):
        cmd = getattr(ctx, "command", "") or ""
        audit.log_command(self.sandbox_name, f"error: {cmd}", "error", "celesto_sandbox")
