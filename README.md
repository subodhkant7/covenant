# Covenant 🛡️

> **Autonomous commitment-resolution agent system that remembers what people and organizations have promised, continuously monitors whether those commitments are on track, investigates when they drift, takes authorized actions, and verifies resolution.**

Built for the **Professional Agents** track of the **Agents for Humans Hackathon**.

---

## Key Differentiators

- **Commitments, Not Tasks**: Tasks tell you what to do. Commitments tell you what the world expects to happen. Covenant watches whether that expectation is actually fulfilled.
- **Deterministic State Machine**: Strict lifecycle guards validate every transition; LLMs cannot freely mutate system state.
- **Human-in-the-Loop Decision Surface**: Clear policy boundary that surfaces high-risk or external actions to humans with corroborating evidence checklists.
- **Independent Verification**: Commitments are only closed when verified by post-action corroborating evidence.
- **Directional Clarity**: Distinct segmentation between *What Others Owe Us* (`THEY_OWE_US`) and *What We Owe Others* (`WE_OWE_THEM`).
- **Local-First & Cloud-Ready**: Built on SQLite WAL and local model provider abstractions (Ollama / Local LLM), designed for zero-rewrite swap to AWS Bedrock / DynamoDB / EventBridge.

---

## Core Architecture & Governance Boundary

Covenant treats LLM agents strictly as bounded reasoning tools. A model recommendation is **never** system authority.

```
ENTERPRISE EVIDENCE
       │
       ▼
COMMITMENT DISCOVERY ──► EVIDENCE CORROBORATION / GAP / CONTRADICTION
                               │
                               ▼
                        RISK ASSESSMENT
                               │
                               ▼
                     REMEDIATION PROPOSAL
                               │
                               ▼
                      DETERMINISTIC POLICY
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
        [LOW RISK INTERNAL]          [EXTERNAL / HIGH RISK]
                │                             │
                │                     HUMAN APPROVAL GATE
                │                             │
                └──────────────┬──────────────┘
                               ▼
                      CONTROLLED EXECUTION (T_exec)
                               │
                               ▼
                       VERIFYING STATE
                               │
                               ▼
               INDEPENDENT EXTERNAL EVIDENCE (T_proof > T_exec)
                               │
                               ▼
                       VERIFICATION GATE
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
        [CORROBORATED]               [REJECTED / UNMET]
                │                             │
                ▼                             ▼
        RESOLVED (VERIFIED)                 FAILED
```

### Evidence Classification Semantics
Evidence assessments strictly distinguish ontological categories:
- **`FACT`**: Direct documentary observations from authoritative enterprise systems (e.g. deliverable submitted, milestone date).
- **`INFERENCE`**: Plausible deductions from observed facts (e.g. downstream Phase 3 kickoff blocked).
- **`CORROBORATION`**: Multiple independent records supporting the same conclusion.
- **`EVIDENCE GAP`**: Expected documentary proof is absent; penalizes certainty rather than hallucinating confidence.
- **`CONTRADICTION`**: Opposing statuses or conflicting signals across independent sources.

### Dual-Verification Gate
A successful tool invocation or email dispatch is merely **Action Execution**, NOT **Commitment Fulfillment**:
1. **Execution Proof**: Confirms the runtime tool executed cleanly at timestamp $T_{\text{exec}}$.
2. **Outcome Verification Gate**: Evaluates independent counterparty evidence strictly satisfying $T_{\text{proof}} > T_{\text{exec}}$. Pre-action records and stale evidence are rejected. A negative counterparty response transitions the commitment to `FAILED`, never `RESOLVED`.


---

## Project Architecture

```
covenant/
├── covenant/
│   ├── domain/               # Pydantic v2 typed models & enums
│   ├── state_machine/        # Deterministic transition validator & guards
│   ├── persistence/          # Abstract repo interfaces & SQLite WAL repository
│   ├── llm/                  # Abstract ModelProvider (Ollama / Local / Bedrock ready)
│   ├── synthetic_data/       # Northstar Studio workspace (emails, contracts, invoices, milestones)
│   ├── tools/                # Structured tool registry & implementations
│   ├── agents/               # Specialist agents (Supervisor, Commitment, Evidence, Resolution, Policy, Verification)
│   └── api/                  # FastAPI REST backend
├── frontend/                 # Distinctive Commitment Map GUI (React + Vite + Tailwind)
├── tests/                    # Pytest test suite (15 unit & e2e lifecycle tests)
└── docs/                     # Architecture & Demo Scenarios
```

---

## Model Providers

Covenant integrates with language models through the native **Strands Agents SDK**, providing a pluggable, bounded reasoning layer with strict offline safety:

- **Deterministic Provider (`COVENANT_MODEL_PROVIDER=deterministic`) [Default]**:
  - The default provider for testing, development, and CI environments.
  - Requires zero network access, zero cloud credentials, and zero GPU overhead.
  - Provides deterministic, reproducible reasoning and structured JSON outputs for all Covenant workflows.
- **Ollama / Local Provider (`COVENANT_MODEL_PROVIDER=ollama`)**:
  - Connects to local Ollama servers (e.g. `http://localhost:11434`, `llama3:latest`).
  - Supports local model testing when offline Ollama instances are running.
- **Amazon Bedrock Provider (`COVENANT_MODEL_PROVIDER=bedrock`)**:
  - Utilizes the native Strands `BedrockModel` (`strands.models.bedrock.BedrockModel`) without custom API wrappers.
  - Configurable via environment variables:
    - `COVENANT_MODEL_PROVIDER=bedrock`
    - `COVENANT_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0` (example)
    - `COVENANT_AWS_REGION=us-east-1` (defaults to standard AWS region)
  - Uses the standard AWS credential resolution chain (environment variables, IAM roles, AWS profiles).
  - Never stores credentials in the codebase, tests, or git history.
  - Live Bedrock access is optional: the entire test suite and lifecycle remain offline-safe.
  - Note: In environments where an AWS account-level restriction is present (e.g. AWS Error 002: Access to Bedrock models is not allowed for this account), the runtime gracefully logs the block without compromising offline execution or governance boundaries.

---

## Monitoring Control Plane

Covenant exposes its bounded autonomous monitoring cycle through an explicit operational control plane:

- **`POST /api/monitoring/cycles`**: Triggers a canonical bounded monitoring cycle via `SupervisorAgent.run_monitoring_cycle()`. Enforces atomic persistent cycle reservation (rejecting concurrent runs with `409 Conflict`), records telemetry (`SUPERVISOR_CYCLE_START`, `SUPERVISOR_CYCLE_COMPLETE`), updates commitment drift, proposes remedial actions under policy governance, and independently verifies post-dispatch outcomes.
- **`GET /api/monitoring/cycles/{cycle_id}`**: Retrieves operational metadata and summary metrics for a specific cycle run (`cycle_id`, `status`, `started_at`, `completed_at`, `commitments_scanned`, `commitments_changed`, `actions_proposed`, `approval_requests`, `executions`, `verifications`, `resolved`, `failed`, `errors`).
- **`GET /api/monitoring/cycles`**: Lists recent monitoring cycles.

> **Note**: This control plane provides an explicit, bounded monitoring trigger and operational audit surface. It is deliberately distinct from a continuous background daemon or production scheduler.

---

## Quickstart & Local Setup

### 1. Requirements
- Python 3.11+
- Node.js 18+ and npm

### 2. Backend Setup & Test Suite
```bash
# Clone and enter workspace
cd covenant

# Run automated tests
python3 -m pytest tests/ -v

# Start FastAPI backend server (port 8000)
python3 -m uvicorn covenant.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Synthetic Workspace Dataset: Northstar Studio

Covenant includes a realistic multi-source synthetic workspace for **Northstar Studio**:
1. **Project Atlas**: Client approval promised by Sarah Jenkins (Meridian Global) on Sep 5; overdue; downstream Phase 3 frontend blocked per MSA Section 4.2.
2. **Apex Industrial Repairs**: Guaranteed laser cutter repair completion by Sep 2; overdue; technician visited but error E-402 still active.
3. **Lumina Materials Shipment**: Acrylic panels promised by Sep 4; customs delay notification detected; under active investigation.
4. **Horizon Health Brand Kit**: Internal commitment owed by Northstar Studio to Horizon Health by Sep 10; on track.
5. **Veloce Labs Invoice**: Net 30 payment due Sep 14.

---

## Testing & Quality Bar

All domain invariants, deterministic state transitions, persistence, and multi-agent lifecycle execution are validated with pytest:
```bash
python3 -m pytest tests/ -v
```
- `test_domain_models.py`: Model validations and directional obligation computations
- `test_state_machine.py`: Legal transitions and guard enforcement
- `test_persistence.py`: SQLite upserts and event audit logs
- `test_synthetic_data.py`: Northstar Studio dataset queries
- `test_tools.py`: Tool registry and parameter schemas
- `test_lifecycle_e2e.py`: End-to-end lifecycle from discovery to verification and resolution
- `test_agentic_benchmark.py`: Reproducible Agentic Evaluation & Safety Benchmark (25 baseline scenarios)
- `test_adversarial_benchmark.py`: Adversarial Robustness & Regression Suite (~18 adversarial variants, 43 total)

---

## Agentic Evaluation & Safety Benchmark

Covenant includes a reproducible, deterministic **Agentic Evaluation & Safety Benchmark** (`tests/evaluation/`) designed to objectively measure whether the agent system adheres to its governance invariants and evidence reasoning contracts.

> These are reproducible engineering and governance regression tests over synthetic enterprise scenarios. They are not a claim of general-purpose model accuracy.

### Baseline Benchmark (25 scenarios)

The baseline suite (`tests/test_agentic_benchmark.py`) validates core agent reasoning:

- **Commitment Understanding** (6 cases): Clear commitments, ambiguous statements, questions, polite suggestions, completed actions, directional obligations.
- **Evidence Reasoning** (6 cases): Multi-source corroboration, evidence gaps, stale evidence, duplicated records, incomplete logs, genuine contradictions.
- **Risk Assessment** (4 cases): Low-impact overdue, overdue blockers, external communications, financial liabilities.
- **Action & Policy Enforcement** (4 cases): Safe autonomous operations, outbound communications requiring approval, prohibited tools, forged approvals.
- **Verification & Invariants** (5 cases): Fulfillment absence, fresh post-execution proof (`ATLAS-GOLDEN`), stale proof replay, counterparty rejection (`ATLAS-NEGATIVE`), cross-commitment spoofing.

### Adversarial Robustness Suite (~18 additional scenarios)

The adversarial suite (`tests/test_adversarial_benchmark.py`) answers the harder question: *Can small variations, misleading evidence, reordered events, and cross-commitment contamination cause Covenant to violate its governance invariants?*

- **Language Robustness**: Paraphrased commitments, obligations buried in paragraphs, tentative wording, mixed past/future language, indirect references.
- **Evidence Ordering**: Boundary-exact timestamps (`T_proof == T_exec`), 1-second-before stale rejection, mixed fresh/stale evidence.
- **Evidence Contamination**: Same customer different project, generic approval without project context.
- **Authority Conflict**: Slack approval vs. formal email rejection — cross-source contradiction detection.
- **Duplicate/Replay Attacks**: Execution replay from VERIFYING, same attachment different wrapper text.
- **Partial Fulfillment**: Approval language without signed PDF, zero-evidence obligations.
- **Negative Language**: "Not approved", disclaimer with attachment, approval followed by withdrawal.
- **Event-Order Invariance**: Evidence order permutation produces identical semantic outcomes.
- **Cross-Commitment Isolation**: Atlas evidence verifies Atlas only; never satisfies unrelated commitments.
- **Approval Replay Defense**: State machine blocks VERIFYING→EXECUTING transitions.

### Safety Metrics (Zero-Tolerance Invariants)

| Metric | Target | Result |
|--------|--------|--------|
| Approval Bypass Rate | 0% | **0%** |
| False Resolution Rate | 0% | **0%** |
| Stale-Proof Acceptance Rate | 0% | **0%** |
| Execution/Fulfillment Conflation Rate | 0% | **0%** |
| Cross-Commitment Leakage Rate | 0% | **0%** |
| Event-Order Semantic Divergence | 0% | **0%** |
| Approval Replay Acceptance Rate | 0% | **0%** |
| Duplicate Side-Effect Rate | 0% | **0%** |
| Partial-Fulfillment False Resolution Rate | 0% | **0%** |
| Negative-Language False-Positive Rate | 0% | **0%** |

### Canonical Regression Anchors

- `ATLAS-GOLDEN`: Discovery → corroboration → evidence gap → HIGH risk → remediation proposal → RULE-EXT-COMM → HUMAN_APPROVAL_REQUIRED → human approval → ExecutionEngine dispatch → VERIFYING → fresh signed approval → VerificationGate → **RESOLVED**.
- `ATLAS-NEGATIVE`: Counterparty rejection / missing post-dispatch proof leaves the commitment in **VERIFYING** and explicitly prevents resolution.

### Running the Benchmarks

```bash
# Baseline benchmark (25 scenarios)
python3 -m pytest tests/test_agentic_benchmark.py -v -s

# Adversarial robustness suite (43 total scenarios)
python3 -m pytest tests/test_adversarial_benchmark.py -v -s
```

### Known Limitations

- This is a deterministic engineering benchmark using synthetic scenarios and local providers, not an independent, open-ended scientific evaluation of arbitrary real-world LLMs.
- Test cases represent bounded enterprise scenarios; edge cases outside the defined operational domain require expanded scenario sets.
