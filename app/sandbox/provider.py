from __future__ import annotations
import base64
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from app.config import settings
from app import audit, security


class SandboxProviderError(RuntimeError):
    """Base error for sandbox provider failures."""
    pass


class CelestoPaymentRequiredError(SandboxProviderError):
    """Raised when Celesto Cloud returns HTTP 402 Payment Required."""
    pass


class CelestoSandboxProvider:
    """
    Real Celesto provider abstraction using Celesto SDK 0.1.4.
    Fails closed when credentials are missing.
    Dispatches to CloudComputer for celesto_cloud, and Celesto for local backends.
    """
    def __init__(self):
        self.enabled = bool(settings.celesto_api_key and settings.celesto_provider)
        self.mode = "real" if self.enabled else "disabled"
        self._is_cloud = (settings.celesto_provider == "celesto_cloud")

    def _ensure_enabled(self):
        if not self.enabled:
            raise SandboxProviderError(
                "Celesto not configured – missing CELESTO_API_KEY or CELESTO_PROVIDER"
            )

    def create_sandbox(
        self,
        sandbox_name: str,
        backend: Optional[str] = None,
        internet_settings: Optional[dict] = None,
    ) -> dict:
        """Create a Celesto VM sandbox and return a handle dict."""
        self._ensure_enabled()
        resolved_backend = backend or settings.celesto_backend or "qemu"
        vm = None

        try:
            if self._is_cloud:
                from celesto import CloudComputer, CloudAPIError
                # CloudComputer connects to api.celesto.ai
                vm = CloudComputer(api_key=settings.celesto_api_key)
                vm.start()
                return {
                    "sandbox_name": sandbox_name,
                    "backend": "celesto_cloud",
                    "status": "created",
                    "mode": self.mode,
                    "_vm": vm,
                    "_is_cloud": True,
                }
            else:
                from celesto import Celesto, InternetSettings
                inet = None
                if internet_settings:
                    inet = InternetSettings(**internet_settings)

                vm = Celesto(
                    vm_id=sandbox_name,
                    backend=resolved_backend,
                    internet_settings=inet,
                )
                vm.start()
                return {
                    "sandbox_name": sandbox_name,
                    "backend": resolved_backend,
                    "status": "created",
                    "mode": self.mode,
                    "_vm": vm,
                    "_is_cloud": False,
                }

        except SandboxProviderError:
            raise
        except Exception as e:
            # Clean up partially initialized VM if start failed
            if vm is not None:
                try:
                    if hasattr(vm, "delete"):
                        vm.delete()
                    elif hasattr(vm, "close"):
                        vm.close()
                except Exception:
                    pass

            err_str = str(e)
            status_code = getattr(e, "status_code", None)
            err_code = getattr(e, "code", None)
            err_op = getattr(e, "operation", None)
            recovery = getattr(e, "recovery_action", None)
            if status_code == 402 or "402" in err_str:
                raise CelestoPaymentRequiredError(
                    "Celesto Cloud returned HTTP 402 Payment Required: "
                    "account requires active subscription/sandbox hours entitlement on https://app.celesto.ai"
                ) from None

            detail = f"Failed to create sandbox {sandbox_name}: {err_str}"
            if err_code:
                detail += f" (code: {err_code})"
            if recovery:
                detail += f" (recovery: {recovery})"
            raise SandboxProviderError(detail)

    def wait_ready(self, handle: dict, timeout_s: int = 60) -> dict:
        """Wait for the sandbox VM to become ready."""
        self._ensure_enabled()
        vm = handle.get("_vm")
        if vm is None:
            raise SandboxProviderError("No VM instance in handle – was create_sandbox called?")
        try:
            if hasattr(vm, "wait_for_ready"):
                vm.wait_for_ready(timeout=float(timeout_s))
            return {**handle, "status": "ready"}
        except Exception as e:
            raise SandboxProviderError(f"Sandbox readiness timeout for {handle['sandbox_name']}: {e}")

    def execute_command(
        self, handle: dict, command: str, timeout_s: int = 30
    ) -> dict:
        """Execute a command inside the Celesto guest after authorization check."""
        self._ensure_enabled()
        # Authorization before execution
        allowed = security.authorize_command(command)
        audit.log_command(
            handle["sandbox_name"], command,
            "allow" if allowed else "block",
            "celesto_sandbox",
        )
        if not allowed:
            raise PermissionError("Command blocked by safety policy")

        vm = handle.get("_vm")
        if vm is None:
            raise SandboxProviderError("No VM instance in handle")

        try:
            result = vm.run(command, timeout=timeout_s)
            stdout = getattr(result, "stdout", "")
            stderr = getattr(result, "stderr", "")
            exit_code = getattr(result, "exit_code", 0 if getattr(result, "ok", True) else 1)
            output = getattr(result, "output", stdout or str(result))
            ok = getattr(result, "ok", exit_code == 0)
            return {
                "output": output,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code if isinstance(exit_code, int) else (0 if ok else 1),
                "command": command,
            }
        except TimeoutError as te:
            raise SandboxProviderError(f"Command execution timed out after {timeout_s}s: {te}")
        except Exception as e:
            raise SandboxProviderError(f"Command execution failed: {e}")

    def get_file(self, handle: dict, guest_path: str, local_path: str = "") -> bytes:
        """Retrieve a file from the Celesto guest."""
        self._ensure_enabled()
        vm = handle.get("_vm")
        if vm is None:
            raise SandboxProviderError("No VM instance in handle")
        try:
            if handle.get("_is_cloud"):
                # Retrieve via guest command execution with base64 encoding
                res = vm.run(f"base64 -w 0 '{guest_path}' 2>/dev/null || base64 '{guest_path}'", timeout=15)
                raw_bytes = base64.b64decode(res.output.strip())
                if local_path:
                    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(raw_bytes)
                return raw_bytes
            else:
                if local_path:
                    vm.download_file(guest_path, local_path)
                    with open(local_path, "rb") as f:
                        return f.read()
                else:
                    tmp_path = f"/tmp/_celesto_download_{uuid.uuid4().hex}"
                    vm.download_file(guest_path, tmp_path)
                    with open(tmp_path, "rb") as f:
                        return f.read()
        except Exception as e:
            raise SandboxProviderError(f"File retrieval failed for '{guest_path}': {e}")

    def get_status(self, handle: dict) -> str:
        """Get current status of the sandbox VM."""
        self._ensure_enabled()
        vm = handle.get("_vm")
        if vm is None:
            return "unknown"
        try:
            if hasattr(vm, "status"):
                return str(vm.status())
            return "running"
        except Exception:
            return "unknown"

    def cleanup(self, handle: dict) -> bool:
        """Delete the sandbox VM and release resources."""
        self._ensure_enabled()
        vm = handle.get("_vm")
        if vm is None:
            return True
        try:
            if hasattr(vm, "delete"):
                vm.delete()
            elif hasattr(vm, "close"):
                vm.close()
            return True
        except Exception as e:
            # Log cleanup failure but do not raise
            audit.log_command(
                handle.get("sandbox_name", "unknown"),
                f"cleanup_failed: {e}",
                "error",
                "celesto_sandbox",
            )
            return False


class FakeSandboxProvider:
    """
    Explicit test fake. Not used in production.
    Mirrors the CelestoSandboxProvider interface for test isolation.
    """
    def __init__(self):
        self.mode = "fake"

    def create_sandbox(self, sandbox_name: str, **kwargs):
        return {"sandbox_name": sandbox_name, "status": "created", "mode": self.mode}

    def wait_ready(self, handle: dict, timeout_s: int = 60):
        return {**handle, "status": "ready"}

    def execute_command(self, handle: dict, command: str, timeout_s: int = 30):
        allowed = security.authorize_command(command)
        audit.log_command(
            handle["sandbox_name"], command,
            "allow" if allowed else "block",
            "celesto_sandbox",
        )
        if not allowed:
            raise PermissionError("Command blocked by safety policy")
        return {"output": "fake output", "exit_code": 0, "command": command}

    def get_file(self, handle: dict, guest_path: str, local_path: str = "") -> bytes:
        return b"fake"

    def get_status(self, handle: dict) -> str:
        return "running"

    def cleanup(self, handle: dict) -> bool:
        return True


def get_provider():
    """Production provider – never silently falls back to fake."""
    return CelestoSandboxProvider()
