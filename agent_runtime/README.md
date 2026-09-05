# Agent Organization Runtime Kernel (V1 Pure Core)

An isolated, domain-agnostic execution runtime for multi-agent organizations with deterministic execution authority, granular authorization, policy gating, human approval, and independent outcome verification.

---

## Architecture & Module Ownership

The kernel follows a strict unidirectional dependency graph:
```
contracts
   ↑
interfaces
   ↑
state / authorization / policy / telemetry
   ↑
engine / verification
   ↑
adapters
```

### 1. `agent_runtime/core/contracts/`
- **Owns**: Typed, immutable or strongly-validated data structures (`Task`, `TaskScope`, `TaskContext`, `AgentDefinition`, `AgentRun`, `Turn`, `AgentRunHistory`, `ToolSpec`, `ToolRequest`, `ToolExecution`, `Observation`, `PolicyEvaluationContext`, `PolicyDecision`, `HumanApprovalRequest`, `Evidence`, `VerificationRequest`, `VerificationResult`, `Event`).
- **Must Not Own**: Execution logic, network I/O, database access, or domain entities.
- **Rule**: `TaskContext` is strictly frozen and immutable; iterative conversational turns live in append-only `AgentRunHistory`.

### 2. `agent_runtime/core/interfaces/`
- **Owns**: Abstract interfaces (`IAgent`, `ITool`, `ITaskRouter`, `IPolicyEngine`, `IPolicyRule`, `IVerifier`, `IEventSink`, `IModelProvider`).
- **Must Not Own**: Concrete implementations or provider-specific SDK bindings.

### 3. `agent_runtime/core/state/`
- **Owns**: Finite state enums (`TaskState`, `AgentRunState`, `ToolExecutionState`, `ApprovalState`, `PolicyDecisionType`) and deterministic transition validators (`DeterministicTransitionValidator`).
- **Must Not Own**: Task routing or agent execution. Rejects illegal lifecycle transitions deterministically.

### 4. `agent_runtime/core/authorization/`
- **Owns**: `ToolPermissionMatrix` implementing $O(1)$ set-intersection access control `(organization_id, agent_id) -> Set[ToolName]`, plus a protected system tool whitelist.
- **Must Not Own**: Policy evaluation, risk classification, or enterprise RBAC/IAM hierarchies.

### 5. `agent_runtime/core/policy/`
- **Owns**: `DefaultPolicyEngine` evaluating dynamic rules against `PolicyEvaluationContext`. Emits `ALLOW`, `DENY`, or `REQUIRE_HUMAN_APPROVAL`.
- **Must Not Own**: Tool execution, human communication channels, or agent scheduling.

### 6. `agent_runtime/core/telemetry/`
- **Owns**: Append-only event telemetry (`InMemoryEventSink`) correlating causal traces via `trace_id` and `parent_event_id`.
- **Must Not Own**: Message bus, pub/sub infrastructure, or persistence storage.

### 7. `agent_runtime/core/engine/`
- **Owns**:
  - `ToolRegistry` and `AgentRegistry`: In-memory capability discovery.
  - `DeterministicTaskRouter`: Role and capability matching.
  - `ObservationSanitizer`: Secret masking and output length clamping.
  - `IdempotencyStore`: Side-effect execution caching.
  - `ExecutionEngine`: **The single execution authority**. Resolves tools, validates schemas, asserts permissions, evaluates policy, creates human approvals, checks idempotency, runs tool implementations, and produces sanitized observations.
  - `AgentRunExecutor`: Owns the turn-by-turn reasoning loop. Invokes `IAgent.step()` and drives execution turns until completion, failure, or approval blocks.
- **Must Not Own**: Agent decision reasoning or domain entity state.

### 8. `agent_runtime/core/verification/`
- **Owns**: `VerificationGate` evaluating real-world outcome proofs (`Evidence`) and corroborating task completion independently from tool dispatch success.
- **Must Not Own**: Agent reasoning or tool execution.

---

## Canonical Execution Flow

```text
Task(PENDING)
   ↓
DeterministicTaskRouter matches required_role -> AgentDefinition
   ↓ Task(ROUTED) -> Task(RUNNING)
AgentRunExecutor starts AgentRun(INITIALIZING) -> AgentRun(EXECUTING)
   ↓
Builds immutable TaskContext + empty AgentRunHistory
   ↓
Loop:
   IAgent.step(context, history)
      ↓
   AgentStepToolRequest(tool_name, arguments)
      ↓
   ExecutionEngine (Sole Authority):
      1. Resolve tool in ToolRegistry
      2. Validate arguments against ToolSpec.parameters_schema
      3. Verify permission in ToolPermissionMatrix
      4. Evaluate policy in DefaultPolicyEngine
         - If REQUIRE_HUMAN_APPROVAL:
           Create HumanApprovalRequest -> Task(BLOCKED) -> Await human sign-off
         - If DENY: Return error Observation
         - If ALLOW or APPROVED:
           Check IdempotencyStore -> Execute ITool -> Sanitize -> Return Observation
      5. Append Turn(thought, request, observation) to AgentRunHistory
   ↓
IAgent.step() yields AgentStepComplete
   ↓
VerificationGate:
   - If Task.requires_verification:
     Task(VERIFYING) -> IVerifier.verify() -> VerificationResult(verified=True)
   ↓
Task(COMPLETED)
```

---

## Zero Domain Coupling Guarantee

The runtime kernel imports zero domain code (`covenant.domain`, `covenant.agents`, `covenant.persistence`). It compiles and passes 100% of unit and integration tests completely independently.
