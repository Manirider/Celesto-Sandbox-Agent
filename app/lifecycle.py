import json
import os
import time
from datetime import datetime, timezone
from app.sandbox.provider import get_provider, SandboxProviderError


TRACE_PATH = os.getenv("FAILURE_TRACE_PATH", "reports/failure_trace.jsonl")


def _emit_trace(event_data: dict):
    """Append a trace event to the failure trace JSONL log."""
    event_data.setdefault("ts", datetime.now(timezone.utc).isoformat())
    os.makedirs(os.path.dirname(TRACE_PATH) or ".", exist_ok=True)
    with open(TRACE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_data) + "\n")


class SandboxLifecycle:
    """
    Manages the lifecycle of a sandbox execution run.

    States: Created -> Ready -> Running -> Succeeded | Failed -> Deleted
    Cleanup is attempted on success, failure, and interrupt.
    Step-7 failure triggers the 'fresh' recovery policy.
    """

    VALID_TRANSITIONS = {
        "Created": {"Ready"},
        "Ready": {"Running"},
        "Running": {"Succeeded", "Failed"},
        "Succeeded": {"Deleted"},
        "Failed": {"Deleted"},
    }

    def __init__(self, sandbox_name: str, provider=None):
        self.sandbox_name = sandbox_name
        self.provider = provider or get_provider()
        self.state = "Created"
        self.handle = None
        self.error = None

    def _transition(self, new_state: str):
        allowed = self.VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid state transition: {self.state} -> {new_state}"
            )
        self.state = new_state

    def run(self, steps: list[str], inject_failure_at: int = 7):
        """
        Execute a sequence of steps inside the sandbox.
        Injects a failure at the specified step number (1-indexed) for testing.
        Returns a result dict.
        """
        try:
            self._transition("Ready")
            self.handle = self.provider.create_sandbox(self.sandbox_name)
            self.provider.wait_ready(self.handle)
            self._transition("Running")

            for i, step in enumerate(steps, start=1):
                if i == inject_failure_at and inject_failure_at <= len(steps):
                    _emit_trace({
                        "event": "step_started",
                        "step": i,
                        "sandbox_name": self.sandbox_name,
                    })
                    _emit_trace({
                        "event": "failure_detected",
                        "step": i,
                        "error": f"Injected failure at step {i}",
                        "sandbox_name": self.sandbox_name,
                    })
                    raise RuntimeError(f"Injected failure at step {i}")
                self.provider.execute_command(self.handle, step)

            self._transition("Succeeded")
            return {"sandbox_name": self.sandbox_name, "state": self.state}

        except Exception as e:
            self.error = str(e)
            self.state = "Failed"
            if self.handle:
                try:
                    self.provider.cleanup(self.handle)
                except Exception:
                    pass
            raise

    def cleanup(self) -> bool:
        """
        Attempt cleanup of sandbox resources.
        Always attempts cleanup regardless of current state.
        """
        success = True
        if self.handle:
            try:
                success = self.provider.cleanup(self.handle)
            except Exception:
                success = False
        self.state = "Deleted"
        return success

    def recover_fresh(self, steps: list[str], new_sandbox_name: str) -> dict:
        """
        Apply 'fresh' recovery policy: clean up old sandbox, create new one,
        and re-run all steps from the beginning.
        """
        # Clean up old sandbox
        self.cleanup()

        _emit_trace({
            "event": "policy_applied",
            "policy": "fresh",
            "old_sandbox": self.sandbox_name,
            "new_sandbox": new_sandbox_name,
        })

        # Create fresh lifecycle with new sandbox
        fresh = SandboxLifecycle(new_sandbox_name, provider=self.provider)
        # Run without injecting failure on the fresh attempt
        result = fresh.run(steps, inject_failure_at=-1)
        fresh.cleanup()
        return result
