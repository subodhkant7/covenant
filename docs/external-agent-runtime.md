# External Agent Adapter & Runtime Authority Architecture

## Overview & Core Purpose

The **Agent Organization Runtime** is strictly model-independent. It governs external, arbitrary reasoning agents without ever conferring direct execution authority, raw environment access, or cryptographic/credential secrets to those agents.

```text
RAW RUNTIME CONTEXT & OBSERVATIONS
        │
        ▼
ExternalAgentSanitizer (Redacts secrets, strips execution handles)
        │
        ▼
EXTERNAL AGENT / HOST (Untrusted Reasoning Host)
(e.g., AntigravityExternalAgentHost / UnixSocketExternalAgentTransport)
        │
        │ ExternalAgentRequest (Sanitized task facts, tool schemas, safe observations)
        ▼
   ExternalAgentAdapter (IAgent Contract)
        │
        │ AgentStepToolRequest (ToolRequest proposal only, with rationale)
        ▼
AgentRunExecutor (Turn coordinator)
        │
        ▼
ExecutionEngine (Sole Execution Authority)
        │
 ┌──────┼──────────────┐
 ▼      ▼              ▼
Auth   Policy       Verification (VerificationGate)
 │      │              │
 └──────┼──────────────┘
        ▼
     Tool Execution (Registry)
        │
        ▼
   Covenant Domain Sandbox
```

---

## Boundary Guarantees & Architectural Invariants

### 1. External Agent is an Untrusted Reasoning Component
An external agent is treated as completely untrusted. It receives **only sanitized facts, tool schemas, and read-only observations**. It never receives raw execution handles, database connections, filesystem access, credentials, or administrative interfaces. If an object cannot be safely serialized into JSON, the runtime fails closed.

### 2. Sanitized External Context & Recursive Secret Redaction
All data passing into the external agent is processed by `ExternalAgentSanitizer`:
- **Recursive Redaction**: Deep-traverses nested dictionaries, lists, tuples, sets, and strings to redact sensitive patterns (passwords, tokens, API keys, bearer tokens, private keys, connection strings, auth cookies).
- **Business Identifier Preservation**: Ordinary business identifiers (such as `PRJ-ATLAS`, `com_atlas_approval`, `invoice-123`) are preserved without over-redaction.
- **Fail-Closed on Unsafe Handles**: Smuggled callables, system resources (`io.IOBase`), classes/modules, database connections, and runtime engines immediately raise `UnsafeContextError` and emit a `SECURITY_VIOLATION` event.

### 3. Runtime is Sole Execution Authority
No tool or side effect can be invoked directly by the external agent or host. The external entity can only formulate an `ExternalAgentToolProposal`. All execution is mediated and dispatched by the runtime's authoritative `ExecutionEngine`.

### 4. ToolRequest is the Immutable Security Boundary
The boundary between reasoning and execution is the typed `ToolRequest`. The adapter converts external proposals into `AgentStepToolRequest`. The runtime validates the schema, sanitizes arguments, checks permissions, checks policies, and reserves idempotency keys before invoking any tool.

### 5. Removal of Private Chain-of-Thought
Private chain-of-thought (`thought`) has been completely removed from the external protocol and runtime contracts:
- Replaced conceptually with public `rationale` explaining why an action was proposed.
- Private chain-of-thought is not accepted, not logged, not persisted, and not transmitted to external agents.

### 6. Authoritative Approval Service (`RuntimeApprovalService`)
The external agent has zero authority to approve its own proposals or mutate approval state.
- Forged approval payloads in tool proposals or completions are rejected and logged as `SECURITY_VIOLATION`.
- Transition from `PENDING` to `APPROVED` can only be performed by `RuntimeApprovalService.approve_human_request(...)`.
- The service enforces 9 verification conditions:
  1. Approval request exists.
  2. Request is in `PENDING` state.
  3. Task ID matches.
  4. Agent Run ID matches.
  5. Tool Request ID matches.
  6. Organization ID matches.
  7. Reviewer identity is explicitly supplied.
  8. Request has not expired.
  9. Request has not already been executed.

### 7. Verification Gate Authority (`VerificationGate`)
An external agent claiming `verified=true`, `task_status=COMPLETED`, or `skip_verification=true` has zero authority over task outcome verification:
- Task state machine transitions are strictly enforced: `PENDING -> ROUTED -> RUNNING -> VERIFYING -> COMPLETED`.
- A task requiring verification cannot transition to `COMPLETED` unless `VerificationGate` corroborates the result via independent `IVerifier` and `Evidence`.

### 8. Provider and Model Independence
The runtime core depends only on the generic `IAgent` contract. The `ExternalAgentAdapter` maps any external reasoning worker conforming to `IExternalAgent` into this contract:
- The runtime contract is provider-neutral.
- Generic host abstraction `IExternalAgentHost` can be substituted without altering core runtime logic.
- Test doubles demonstrate multi-provider compatibility without claiming unverified live provider integrations.

### 9. Host Status & Antigravity Connector Specification (Step 6.3)
- **`IExternalAgentHost`**: Transport-neutral host abstraction defining session start, request/response exchange, session termination, and host identity reporting.
- **`AntigravityExternalAgentHost`**: Connector adapter implementing `IExternalAgentHost` that bridges to Antigravity reasoning hosts.
- **`HostExternalAgentTransport`**: Pluggable transport adapter wrapping an `IExternalAgentHost` into the runtime's existing `IExternalAgentTransport` protocol.
- **Live Antigravity Status**: The programmatic Python SDK (`google.antigravity`) is not installed in the local environment. The integration seam is implemented and verified against sandbox test doubles; live host invocation remains unimplemented until the official SDK is installed.

---

## Protocol Specification

### Request Payload (`ExternalAgentRequest`)
Delivered to the external agent each turn:
- `task`: `ExternalAgentTaskFacts` (intent, organization ID, task ID, role, scope dictionary, sanitized input data).
- `allowed_tools`: List of `ExternalAgentToolDescription` (name, description, schema, safety level).
- `history`: List of `ExternalAgentTurn` (turn index, tool name, arguments, sanitized observation, rationale).
- `current_turn`: Current 1-indexed turn count.
- `max_turns`: Maximum allowable turns.
- `run_state`: Current execution state.

### Response Payload (`ExternalAgentResponse`)
Strictly validated with `extra="forbid"`:
- `response_type`: Enum (`TOOL_PROPOSAL`, `COMPLETE`, `FAILURE`).
- `tool_proposal`: Optional `ExternalAgentToolProposal` (`tool_name`, `arguments`, `rationale`).
- `completion_summary`: Optional string summarizing final outcome.
- `output_payload`: Optional dictionary of output data.
- `error_message`: Optional error message if failed.
- `rationale`: Optional explanation of why the action was taken.

### Serialization Boundary & Fail-Closed Semantics
- Strict JSON serialization and deserialization round-trip is guaranteed.
- Hard 1 MiB message bound (`MAX_EXTERNAL_AGENT_MESSAGE_BYTES`) enforced on all framing headers before parsing.
- No `pickle`, `eval`, or arbitrary object deserialization.
- Any attempt to inject `__class__`, `__reduce__`, callables, execution handles, or forged authority fields fails closed into an `AgentStepFailure` and logs a `SECURITY_VIOLATION` event.
