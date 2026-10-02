"""EA-4D.4F Hermes authority integration tests.

This module verifies that the Regional Hand Repair pilot can compose
with the existing Hermes authority chain without modifying it.
"""

from __future__ import annotations

from tools.hermes_core.execution_authorization import (
    ExecutionAuthorizationScope,
    ExecutionAuthorizationActor,
    ExecutionAuthorizationPolicyRef,
)
from tools.hermes_core.execution_authorization_issuance import (
    issue_execution_authorization,
)
from tools.hermes_core.execution_authorization_attempt import (
    consume_claim_into_attempt,
)
from tools.hermes_core.execution_authorization_claim import (
    claim_execution_authorization,
)
from tools.hermes_core.execution_authorization_store import (
    ExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_governance_store import (
    SQLiteGovernanceStore,
)
from tools.hermes_core.worker_router import (
    WorkerDescriptor,
    WorkerRegistry,
    WorkerRouterActor,
    WorkerRoutingPolicyRef,
    build_worker_descriptor,
    build_worker_registry,
    build_worker_route_decision,
)
from tools.hermes_core.worker_router_service import (
    select_and_record_worker_route,
)
from tools.hermes_core.execution_start_service import (
    reserve_execution_start,
)
from tools.hermes_core.execution_launch_admission_service import (
    admit_execution_launch_attempt,
)
from tools.hermes_core.execution_launch_coordinator import (
    ExecutionLaunchCoordinator,
    LaunchCoordinationResult,
)
from tools.hermes_core.execution_post_launch_dispatcher import (
    ExecutionPostLaunchDispatcher,
)
from tools.hermes_core.post_launch_execution_orchestrator import (
    PostLaunchExecutionOrchestrator,
)
from tools.hermes_core.execution_state_projection_orchestrator import (
    ExecutionStateProjectionOrchestrator,
)
from tools.hermes_core.execution_state_projector import (
    ExecutionStateProjector,
)
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService,
    RuntimeStartLookup,
)
from tools.hermes_core.sqlite_execution_start_store import (
    SQLiteExecutionStartStore,
)
from tools.hermes_core.deterministic_fake_runtime_adapter import (
    DeterministicFakeRuntimeAdapter,
)
from tools.hermes_core.execution_start import (
    ExecutionLaunchAttemptStatus,
    WorkerRuntimeAdapterKind,
    build_worker_runtime_binding,
)
from tools.hermes_core.runtime_binding_registry import (
    build_worker_runtime_binding_registry,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)
from tools.hermes_core.post_launch_execution_orchestrator import PostLaunchStatus
from tools.regional_hand_repair import (
    HandRepairRegion,
    RepairRequest,
    derive_repair_execution_id,
)
from tools.regional_hand_repair_pilot import (
    PilotConfig,
    RegionalHandRepairPilotRoot,
)
from tests.hermes_core.test_execution_launch_admission import (
    _build_canonical_chain,
    _launcher_actor,
    _persist_canonical_chain,
)


def _repair_request() -> RepairRequest:
    return RepairRequest(
        source_image_sha256="a" * 64,
        hand_guide_sha256="b" * 64,
        structural_request_sha256="c" * 64,
        repair_region=HandRepairRegion(
            label="test", x=0.1, y=0.1, w=0.2, h=0.2,
            padding=0.05, image_width=1024, image_height=1024,
            hand_bbox=(0.1, 0.1, 0.3, 0.3),
            contact_rect=(0.2, 0.2, 0.4, 0.4),
            blade_rect=(0.3, 0.3, 0.5, 0.5),
            subject_rect=(0.0, 0.0, 1.0, 1.0),
        ),
        repair_mask_sha256="d" * 64,
        repair_prompt="fix hand",
        repair_negative_prompt="bad",
        repair_seed=42,
        sampler="dpmpp_2m",
        scheduler="karras",
        steps=24,
        cfg=4.5,
        denoise=0.58,
        checkpoint_asset_id="sdxl_base",
        checkpoint_reference="sd_xl_base_1.0.safetensors",
        checkpoint_sha256="e" * 64,
        lora_asset_id="lora_main",
        lora_reference="lora.safetensors",
        lora_sha256="f" * 64,
        lora_strength=0.85,
    )


class _StartedLookup(RuntimeStartLookup):
    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        return RuntimeLookupResult(
            outcome=RuntimeLookupOutcome.FOUND_STARTED,
            runtime_run_id=f"run-{idempotency_key[:12]}",
            error_code=None,
            error_summary=None,
        )


class TestAuthorityChainComposition:
    """Verify the pilot can compose with the existing authority chain."""

    def test_authorization_chain_exists(self):
        """Verify the authorization chain modules are importable."""
        assert issue_execution_authorization is not None
        assert consume_claim_into_attempt is not None
        assert claim_execution_authorization is not None
        assert select_and_record_worker_route is not None
        assert reserve_execution_start is not None
        assert admit_execution_launch_attempt is not None

    def test_worker_descriptor_can_be_created(self):
        """Verify a WorkerDescriptor can be created for the repair worker."""
        descriptor = build_worker_descriptor(
            worker_id="regional-hand-repair-worker",
            worker_class="REGIONAL_HAND_REPAIR_WORKER",
            worker_version="1.0",
            capabilities=[
                "regional-hand-repair-submit",
                "regional-hand-repair-status-read",
                "regional-hand-repair-output-read",
                "bounded-repair-input-read",
                "bounded-repair-output-write",
            ],
            allowed_operations=["regional-hand-repair-inpaint"],
            enabled=True,
            registration_source="ea4d4f-r6-w1",
            registration_version="1.0",
        )
        assert descriptor.worker_id == "regional-hand-repair-worker"
        assert descriptor.worker_class == "REGIONAL_HAND_REPAIR_WORKER"
        assert descriptor.worker_version == "1.0"
        assert descriptor.verify_hash()

    def test_worker_registry_can_be_created(self):
        """Verify a WorkerRegistry can be created with the repair worker."""
        descriptor = build_worker_descriptor(
            worker_id="regional-hand-repair-worker",
            worker_class="REGIONAL_HAND_REPAIR_WORKER",
            worker_version="1.0",
            capabilities=["regional-hand-repair-submit"],
            allowed_operations=["regional-hand-repair-inpaint"],
            enabled=True,
            registration_source="ea4d4f-r6-w1",
            registration_version="1.0",
        )
        registry = build_worker_registry(
            registry_version="1.0",
            workers=[descriptor],
        )
        assert len(registry.workers) == 1
        assert registry.verify_hash()

    def test_pilot_root_does_not_modify_authority_chain(self):
        """Verify the pilot root is a separate module that doesn't modify authority code."""
        from tools.regional_hand_repair_pilot import RegionalHandRepairPilotRoot
        # The pilot root should be instantiable without touching authority stores
        root = RegionalHandRepairPilotRoot(
            PilotConfig(enabled=False)
        )
        assert not root.is_active
        root.close()

    def test_full_repair_authority_flow_preserves_identity_and_projects_once(
        self, tmp_path
    ):
        request = _repair_request()
        repair_execution_id = derive_repair_execution_id(request)
        descriptor = build_worker_descriptor(
            worker_id="regional-hand-repair-worker",
            worker_class="REGIONAL_HAND_REPAIR_WORKER",
            worker_version="1.0",
            capabilities=["regional-hand-repair-submit"],
            allowed_operations=["regional-hand-repair-inpaint"],
            enabled=True,
            registration_source="ea4d4f-r6-w1",
            registration_version="1.0",
        )
        worker_registry = build_worker_registry(
            registry_version="1.0",
            workers=[descriptor],
        )
        chain = _build_canonical_chain(
            seed="regional-hand-repair",
            operation="regional-hand-repair-inpaint",
            worker_class="REGIONAL_HAND_REPAIR_WORKER",
            input_hash=request.sha256(),
            worker_id=descriptor.worker_id,
            worker_registry=worker_registry,
        )
        authority_store = SQLiteExecutionAuthorizationStore(
            db_path=str(tmp_path / "authority.db")
        )
        start_store = SQLiteExecutionStartStore(
            db_path=str(tmp_path / "start.db")
        )
        start_store.migrate_to_v3()
        root = RegionalHandRepairPilotRoot(PilotConfig(enabled=True))
        try:
            _persist_canonical_chain(authority_store, chain)
            reservation = reserve_execution_start(
                store=authority_store,
                start_store=start_store,
                attempt_id=chain.attempt.attempt_id,
                launcher_actor=_launcher_actor(),
                worker_registry=worker_registry,
                clock=lambda: "2024-01-01T00:05:00Z",
            )
            binding = build_worker_runtime_binding(
                runtime_binding_id="regional-hand-repair-binding-v1",
                worker_id=descriptor.worker_id,
                worker_version=descriptor.worker_version,
                worker_class=descriptor.worker_class,
                adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
                adapter_version="1",
                configuration_reference="regional-hand-repair-local-v1",
                configuration_hash="9" * 64,
                allowed_operations=["regional-hand-repair-inpaint"],
                supports_idempotency=True,
                enabled=True,
            )
            binding_registry = build_worker_runtime_binding_registry(
                registry_version="1.0",
                bindings=[binding],
            )
            launch_attempt = admit_execution_launch_attempt(
                authority_store=authority_store,
                start_store=start_store,
                binding_registry=binding_registry,
                reservation_id=reservation.reservation_id,
                launcher_actor=_launcher_actor(),
                clock=lambda: "2024-01-01T00:06:00Z",
            )
            assert launch_attempt.status == ExecutionLaunchAttemptStatus.RECORDED
            assert repair_execution_id != chain.attempt.attempt_id
            assert repair_execution_id != launch_attempt.launch_attempt_id
            assert chain.attempt.attempt_id != launch_attempt.launch_attempt_id

            start_result_service = ExecutionStartResultService(
                start_store, _StartedLookup()
            )
            projector = ExecutionStateProjector(start_store, authority_store)
            projection_orchestrator = ExecutionStateProjectionOrchestrator(
                projector=projector,
                enabled=True,
            )
            post_launch = PostLaunchExecutionOrchestrator(
                start_result_service=start_result_service,
                projection_orchestrator=projection_orchestrator,
            )
            dispatcher = ExecutionPostLaunchDispatcher(
                post_launch_orchestrator=post_launch,
                enabled=True,
            )
            result = root.dispatch_authorized_post_launch(
                launch_attempt_id=launch_attempt.launch_attempt_id,
                dispatcher=dispatcher,
            )

            assert result.launch_attempt_id == launch_attempt.launch_attempt_id
            assert result.status == PostLaunchStatus.STARTED_PROJECTED
            assert result.projection.launch_attempt_id == launch_attempt.launch_attempt_id
            assert authority_store._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections"
            ).fetchone()[0] == 1
            assert authority_store._conn.execute(
                "SELECT COUNT(*) FROM authority_ledger "
                "WHERE event_type = 'ATTEMPT_EXECUTING'"
            ).fetchone()[0] == 1
        finally:
            root.close()
            start_store.close()
            authority_store.close()


class TestIdentitySeparation:
    """Verify the three identity domains are separate."""

    def test_task_input_identity_independent(self):
        """Task input identity should not include worker or runtime fields."""
        r = _repair_request()
        preimage = r.hash_preimage()
        assert "worker_id" not in preimage
        assert "worker_class" not in preimage
        assert "worker_version" not in preimage
        assert "runtime_binding_id" not in preimage

    def test_worker_identity_independent(self):
        """Worker identity should not include task input or runtime fields."""
        descriptor = build_worker_descriptor(
            worker_id="regional-hand-repair-worker",
            worker_class="REGIONAL_HAND_REPAIR_WORKER",
            worker_version="1.0",
            capabilities=["regional-hand-repair-submit"],
            allowed_operations=["regional-hand-repair-inpaint"],
            enabled=True,
            registration_source="ea4d4f-r6-w1",
            registration_version="1.0",
        )
        canonical = descriptor.to_canonical_dict()
        assert "source_image_sha256" not in canonical
        assert "repair_mask_sha256" not in canonical
        assert "runtime_binding_id" not in canonical
