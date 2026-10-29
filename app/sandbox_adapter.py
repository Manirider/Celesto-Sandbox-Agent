import os
from app import audit, security
from app.config import settings

class CelestoSandboxAdapter:
    def __init__(self):
        self.enabled = bool(settings.celesto_api_key and settings.celesto_provider)
        self.client = None
        if self.enabled:
            try:
                import celesto
                # actual client init would happen here
                self.client = celesto.Celesto()
            except Exception:
                self.enabled = False

    def create_sandbox(self, sandbox_name: str):
        if not self.enabled:
            raise RuntimeError("Celesto not configured")
        # placeholder: actual creation
        return {"sandbox_name": sandbox_name, "status": "created"}

    def execute_command(self, sandbox_name: str, command: str):
        allowed = security.authorize_command(command)
        audit.log_command(sandbox_name, command, "allow" if allowed else "block")
        if not allowed:
            raise PermissionError("Command blocked by safety hook")
        if not self.enabled:
            raise RuntimeError("Celesto not configured - cannot execute")
        # placeholder execution
        return {"output": "ok", "exit_code": 0}
