# EA-4E - Multi-Receiver Agent Integration Design

Status: DESIGN ONLY - NOT IMPLEMENTED

Authority granted by this packet: design only

Implementation authority: NOT GRANTED

## 1. Course Correction

EA-4D.4F is closed and frozen. It proved one governed receiver: `codex-cli-agent`.

EA-4E extends the governed delegation architecture to support multiple receiving agents:

- `codex-cli-agent` (existing, frozen qualification evidence)
- `opencode-cli-agent` (new)
- `kilo-cli-agent` (new)

The governing flow is:

```
Originator Agent
    -> Hermes Governance + Execution Authority
    -> authorization / claim / ExecutionAttempt
    -> WorkerRouter
    -> named receiving agent + runtime binding
    -> Receiving Agent
    -> DelegationAcceptance
    -> bounded execution
    -> DelegationResult + evidence
    -> Hermes
    -> lineage verification / terminal state
    -> ResultDelivery to originator or next authorized agent
```

## 2. Design Principles

1. **Preserve the qualified Codex path.** Do not redesign working abstractions.
2. **Receiver capability is not Hermes authority.** Receivers cannot mint authorizations, mutate authority decisions, expand their capability leases, select other agents, or activate scheduler behavior.
3. **Static receiver binding.** Receivers are resolved from trusted configuration/static binding only. No arbitrary executable paths from delegated task material.
4. **Independent receiver identity.** Each receiver has its own pinned executable identity, version, protocol contract, permissions, model/provider binding, result contract, and qualification status.
5. **Fail-closed.** Any mismatch or uncertainty fails closed. No silent substitution.
6. **Deterministic routing.** Same inputs produce same route/receiver selection.

## 3. Receiver Adapter Abstraction

### 3.1 Generic Receiver Protocol

All receivers implement a common protocol:

```python
class ReceiverAdapter(Protocol):
    """Governed receiver adapter protocol."""
    
    @property
    def receiver_id(self) -> str: ...
    
    @property
    def receiver_version(self) -> str: ...
    
    @property
    def adapter_version(self) -> str: ...
    
    def verify_binary(self) -> BinaryIdentity: ...
    
    def qualify_runtime(self) -> QualifiedRuntimeBinding: ...
    
    def qualify_schema_contract(self) -> SchemaQualification: ...
    
    def build_argv(self, runtime_run_id: str) -> Argv: ...
    
    def parse_jsonl(self, stdout: str) -> JsonlResult: ...
    
    def classify_start_state(self, pid: Optional[int], result: Optional[ProcessResult]) -> StartState: ...
    
    def prepare_invocation(self, *, idempotency_key: str, launch_attempt_id: str,
                          delegation_id: str, stdin_data: str, ...) -> Tuple[InvocationRecord, Argv, bool]: ...
    
    def execute(self, *, idempotency_key: str, launch_attempt_id: str,
                delegation_id: str, stdin_data: str, ...) -> ExecutionOutcome: ...
```

### 3.2 Receiver-Specific Implementations

| Receiver | Module | Binary | CLI Contract |
|---|---|---|---|
| Codex | `codex_adapter.py` | `codex.exe` | `--ask-for-approval never --sandbox read-only exec --json ...` |
| OpenCode | `opencode_adapter.py` | TBD | TBD |
| Kilo | `kilo_adapter.py` | TBD | TBD |

Each adapter is Codex-specific in its implementation but receiver-neutral in its interface.

## 4. Receiver Registry

### 4.1 Static Receiver Binding

Receivers are registered in a static, versioned registry:

```python
@dataclass(frozen=True)
class ReceiverDescriptor:
    receiver_id: str           # codex-cli-agent | opencode-cli-agent | kilo-cli-agent
    receiver_class: str        # CODEX | OPENCODE | KILO
    receiver_version: str
    adapter_version: str
    executable_path: str       # absolute, resolved
    expected_sha256: str
    expected_version: str
    cli_contract_id: str
    approval_policy: str       # never
    sandbox_policy: str        # read-only
    allowed_operations: Sequence[str]
    capabilities: Sequence[str]
    enabled: bool
    registration_source: str   # trusted-config
    registration_version: str
    descriptor_hash: str
```

### 4.2 Receiver Registry

```python
@dataclass(frozen=True)
class ReceiverRegistry:
    registry_version: str
    registry_hash: str
    receivers: Sequence[ReceiverDescriptor]
    
    def get_receiver(self, receiver_id: str) -> ReceiverDescriptor: ...
    def get_adapter(self, receiver_id: str) -> ReceiverAdapter: ...
```

### 4.3 Routing Integration

The existing `WorkerRegistry` and `WorkerRouteDecision` are extended to bind receiver identity explicitly:

```python
# In WorkerRouteDecision, the worker_id field binds to receiver_id
# The worker_class field binds to receiver_class (CODEX | OPENCODE | KILO)
# The receiver_descriptor_hash binds the exact receiver snapshot
```

## 5. Multi-Receiver Lifecycle

### 5.1 Delegation Request

The originator requests a target agent:

```python
envelope = build_delegated_task_envelope(
    ...
    requested_target_agent_id="opencode-cli-agent",  # or codex-cli-agent, kilo-cli-agent
    ...
)
```

### 5.2 Route Selection

The router selects the exact receiver:

```python
route = build_worker_route_decision(
    ...
    worker_id="opencode-cli-agent",
    worker_class="OPENCODE",
    ...
)
```

### 5.3 Receiver Resolution

The receiver adapter is resolved from the registry:

```python
adapter = registry.get_adapter(route.worker_id)
# Returns OpenCodeReceiverAdapter for opencode-cli-agent
```

### 5.4 Invocation

The receiver adapter handles the full lifecycle:

```python
outcome = adapter.execute(
    idempotency_key=launch.idempotency_key,
    launch_attempt_id=launch.launch_attempt_id,
    delegation_id=envelope.delegation_id,
    stdin_data=stdin_data,
)
```

## 6. Security and Trust Boundaries

### 6.1 Per-Receiver Security Contract

Each receiver must satisfy:

- `APPROVAL_POLICY=NEVER`
- `SANDBOX=READ_ONLY`
- `DANGEROUS_BYPASS=NO`
- `WORKSPACE_WRITE=NO`
- `FULL_ACCESS=NO`
- `ARBITRARY_EXECUTABLE=NO`
- `ARBITRARY_FLAGS=NO`

### 6.2 Binary Pinning

Each receiver's binary is pinned by:
- Absolute path (resolved)
- SHA-256 hash
- Version string
- CLI contract ID

Any change fails closed pending requalification.

### 6.3 Capability Boundary

Receivers cannot:
- Issue new ExecutionAuthorizations
- Mutate authority decisions
- Expand their capability lease
- Authorize another agent
- Activate scheduler behavior
- Choose a different receiver
- Expand allowed filesystem scope
- Alter delegation identity
- Alter task input hash
- Bypass mailbox acceptance
- Directly project themselves EXECUTING

## 7. Result Return Path

The result return path is receiver-agnostic:

```
Verified Result
    -> Canonical Delegation Result
    -> Durable Result Store
    -> Result Delivery
    -> Originator Acknowledgement
    -> Hermes COMPLETED projection
```

Each stage is independently proven. No receiver-specific shortcuts.

## 8. Failure Handling

### 8.1 Receiver Unavailable

If a receiver binary is missing, hash mismatched, or version changed:
- Route selection fails closed
- No silent substitution to another receiver
- Durable failure evidence preserved

### 8.2 Receiver Runtime Failure

If a receiver process fails:
- Failure evidence preserved
- No automatic retry (retry policy is separate)
- Historical evidence immutable

### 8.3 Cross-Attempt Replay

Same receiver, same material:
- Idempotent replay returns existing result
- No duplicate process

Different receiver for same attempt:
- Divergent replay conflicts
- No state advancement

## 9. Implementation Boundaries

### 9.1 Frozen (Do Not Modify)

- `tools/hermes_core/codex_adapter.py` (qualified Codex path)
- `tools/hermes_core/delegated_task.py` (R12A domain)
- `tools/hermes_core/delegation_delivery.py` (R12B mailbox)
- `tools/hermes_core/delegation_result.py` (result domain)
- `tools/hermes_core/sqlite_delegation_store.py` (R12A/B persistence)
- `tools/hermes_core/sqlite_delegation_result_store.py` (result persistence)
- `tools/hermes_core/execution_start.py` (start domain)
- `tools/hermes_core/sqlite_execution_start_store.py` (start persistence)
- `tools/hermes_core/worker_router.py` (routing domain)
- `tools/hermes_core/lease_window.py` (lease domain)
- `tools/hermes_core/runtime_namespace.py` (namespace domain)

### 9.2 New (To Be Implemented)

- `tools/hermes_core/receiver_adapter.py` (generic protocol)
- `tools/hermes_core/receiver_registry.py` (receiver registry)
- `tools/hermes_core/opencode_adapter.py` (OpenCode adapter)
- `tools/hermes_core/kilo_adapter.py` (Kilo adapter)

### 9.3 Extended (Minimal Changes)

- `tools/hermes_core/worker_router.py` - Add receiver_descriptor_hash to route decision
- `tools/hermes_core/delegated_task.py` - Add receiver_binding to envelope (optional)

## 10. Qualification Requirements

Each new receiver must be independently qualified:

### 10.1 Non-Live Qualification

- Binary pinning verification
- CLI contract qualification
- Fake-process qualification
- JSONL/schema parsing qualification
- Timeout/cancellation/start-state qualification
- No live model invocation

### 10.2 Live Qualification

- One-shot live proof under separate authorization
- Harmless deterministic read-only fixture
- Complete result return path
- Replay/duplicate prevention
- Post-live regression green

## 11. Explicit Non-Goals

- Production activation
- Default receiver activation
- Scheduler activation
- Generic agent orchestration before each receiver is proven
- Dynamic agent self-registration
- Agent-selected authority expansion
- `app.py` integration
- Studio Bible / image-pipeline changes
- Regional Hand Repair

## 12. Design Disposition

EA-4E MULTI-RECEIVER DESIGN: COMPLETE / FROZEN

IMPLEMENTATION: NOT AUTHORIZED

NEXT: separate implementation authorization packet
