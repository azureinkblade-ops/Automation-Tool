"""Tests for receiver-neutral adapter protocol and registry."""
from __future__ import annotations

import pytest
from tools.hermes_core.receiver_adapter import (
    BinaryIdentity,
    ExecutionOutcome,
    InvocationRecord,
    ProcessResult,
    QualifiedRuntimeBinding,
    ReceiverAdapter,
    ReceiverError,
    VerifiedResult,
)
from tools.hermes_core.receiver_registry import (
    ReceiverDescriptor,
    ReceiverRegistry,
    UnknownReceiverError,
    build_receiver_descriptor,
    build_receiver_registry,
)


class DummyAdapter:
    def __init__(self):
        self._id = "dummy"
    @property
    def receiver_id(self): return self._id
    @property
    def receiver_version(self): return "1.0"
    @property
    def adapter_version(self): return "1.0"
    def verify_binary(self) -> BinaryIdentity:
        return BinaryIdentity("a"*64, "1.0", "/bin/d", 1000)
    def qualify_runtime(self) -> QualifiedRuntimeBinding:
        return QualifiedRuntimeBinding("/bin/d", "a"*64, "1.0", "dummy-v1")
    def qualify_schema_contract(self) -> dict:
        return {"schema_id": "test"}
    def build_argv(self, runtime_run_id: str):
        return ["dummy", "--run", runtime_run_id]
    def parse_output(self, stdout: str) -> dict:
        return {"out": stdout}
    def classify_start_state(self, pid, result):
        return "PREPARED" if pid is None else "TERMINAL"
    def prepare_invocation(self, *, idempotency_key, launch_attempt_id, delegation_id, stdin_data):
        return InvocationRecord(idempotency_key, "r1", "PREPARED", None, None, "h"*64), ["d"], False
    def execute(self, *, idempotency_key, launch_attempt_id, delegation_id, stdin_data):
        return ExecutionOutcome(True, False, InvocationRecord("k","r","T","T",1,"hh"), VerifiedResult(True, {}))


class TestReceiverDescriptor:
    def test_build_and_hash(self):
        d = build_receiver_descriptor(
            receiver_id="opencode-cli-agent", receiver_class="OPENCODE",
            receiver_version="1.18.11", adapter_version="1.0",
            executable_path=r"C:\test\opencode.exe", expected_sha256="a"*64,
            expected_version="1.18.11", transport_contract_id="acp-stdio/v1",
            approval_policy="never", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="trusted-config", registration_version="1",
        )
        assert d.receiver_id == "opencode-cli-agent"
        assert d.verify_hash()

    def test_immutable(self):
        d = build_receiver_descriptor(
            receiver_id="opencode-cli-agent", receiver_class="OPENCODE",
            receiver_version="1.18.11", adapter_version="1.0",
            executable_path=r"C:\t.exe", expected_sha256="a"*64,
            expected_version="1.18.11", transport_contract_id="t/v1",
            approval_policy="never", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="t", registration_version="1",
        )
        with pytest.raises(AttributeError):
            d.receiver_id = "other"

    def test_distinct_receivers(self):
        c = build_receiver_descriptor(
            receiver_id="codex-cli-agent", receiver_class="CODEX",
            receiver_version="0.151.0", adapter_version="1.1",
            executable_path=r"C:\c.exe", expected_sha256="b"*64,
            expected_version="0.151.0", transport_contract_id="exec/v1",
            approval_policy="never", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="t", registration_version="1",
        )
        o = build_receiver_descriptor(
            receiver_id="opencode-cli-agent", receiver_class="OPENCODE",
            receiver_version="1.18.11", adapter_version="1.0",
            executable_path=r"C:\o.exe", expected_sha256="a"*64,
            expected_version="1.18.11", transport_contract_id="acp-stdio/v1",
            approval_policy="never", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="t", registration_version="1",
        )
        assert c.receiver_id != o.receiver_id
        assert c.receiver_class != o.receiver_class
        assert c.descriptor_hash != o.descriptor_hash


class TestReceiverRegistry:
    def test_build_registry(self):
        d = build_receiver_descriptor(
            receiver_id="opencode-cli-agent", receiver_class="OPENCODE",
            receiver_version="1.18.11", adapter_version="1.0",
            executable_path=r"C:\t.exe", expected_sha256="a"*64,
            expected_version="1.18.11", transport_contract_id="t/v1",
            approval_policy="never", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="t", registration_version="1",
        )
        r = build_receiver_registry(registry_version="1", receivers=[d])
        assert r.registry_version == "1"
        assert r.verify_hash()
        assert len(r.receivers) == 1

    def test_get_receiver_found(self):
        d = build_receiver_descriptor(
            receiver_id="opencode-cli-agent", receiver_class="OPENCODE",
            receiver_version="1.18.11", adapter_version="1.0",
            executable_path=r"C:\t.exe", expected_sha256="a"*64,
            expected_version="1.18.11", transport_contract_id="t/v1",
            approval_policy="never", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="t", registration_version="1",
        )
        r = build_receiver_registry(registry_version="1", receivers=[d])
        found = r.get_receiver("opencode-cli-agent")
        assert found is not None
        assert found.receiver_id == "opencode-cli-agent"

    def test_get_receiver_unknown(self):
        r = build_receiver_registry(registry_version="1", receivers=[])
        assert r.get_receiver("unknown") is None

    def test_get_adapter_unknown(self):
        r = build_receiver_registry(registry_version="1", receivers=[])
        with pytest.raises(UnknownReceiverError, match="Unknown"):
            r.get_adapter("unknown")

    def test_get_adapter_disabled(self):
        d = build_receiver_descriptor(
            receiver_id="opencode-cli-agent", receiver_class="OPENCODE",
            receiver_version="1.18.11", adapter_version="1.0",
            executable_path=r"C:\t.exe", expected_sha256="a"*64,
            expected_version="1.18.11", transport_contract_id="t/v1",
            approval_policy="never", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=False, registration_source="t", registration_version="1",
        )
        r = build_receiver_registry(registry_version="1", receivers=[d])
        with pytest.raises(Exception, match="Disabled"):
            r.get_adapter("opencode-cli-agent")

    def test_kilo_unqualified(self):
        r = build_receiver_registry(registry_version="1", receivers=[])
        assert r.get_receiver("kilo-cli-agent") is None


class TestProtocolConformance:
    def test_binary_identity(self):
        b = BinaryIdentity("a"*64, "1.18.11", "/bin/d", 1000000)
        assert b.sha256 == "a"*64
        assert b.version == "1.18.11"
        assert b.metadata_probe_spawned is True

    def test_verified_result(self):
        v = VerifiedResult(valid=True, payload={"outcome": "SUCCEEDED"})
        assert v.valid and v.parse_error is None
        v2 = VerifiedResult(valid=False, payload={}, parse_error="bad")
        assert not v2.valid and v2.parse_error == "bad"

    def test_invocation_record(self):
        ir = InvocationRecord("key", "r", "PREPARED", None, None, "h"*64)
        assert ir.start_state == "PREPARED"
        assert ir.terminal_state is None

    def test_execution_outcome(self):
        eo = ExecutionOutcome(True, False, InvocationRecord("k","r","T","T",1,"h"), VerifiedResult(True, {}))
        assert eo.process_started and not eo.replayed and eo.verified_result is not None

    def test_protocol_structure(self):
        """ReceiverAdapter protocol is receiver-neutral and has no Codex import."""
        assert hasattr(ReceiverAdapter, "receiver_id")
        assert hasattr(ReceiverAdapter, "receiver_version")
        assert hasattr(ReceiverAdapter, "verify_binary")
        assert hasattr(ReceiverAdapter, "execute")
        adapter = DummyAdapter()
        assert isinstance(adapter, ReceiverAdapter)
