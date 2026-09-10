# Covenant 🛡️

### Autonomous commitment intelligence with independently verified fulfillment.

Built for the **Professional Agents** track of the **Agents for Humans Hackathon**.

---

## The Problem: Execution ≠ Fulfillment

Enterprise commitments are scattered across messages, project systems, approvals, contracts, and operational tools.

Most automation proves:
> *"The action happened."*

Covenant answers:
> **"Did the commitment actually get fulfilled?"**

```text
EXECUTION ≠ FULFILLMENT

Action success (T_exec)
      ↓
does not automatically mean
      ↓
real-world obligation fulfilled

Fresh independent evidence (T_proof > T_exec)
      ↓
VerificationGate
      ↓
RESOLVED
```

> **Execution is an event. Fulfillment is an outcome.**  
> Covenant frames automation around **obligation truth**, not task completion.

```text
Discovery ──► Evidence Synthesis ──► Risk Assessment ──► Remediation Proposal ──► Policy Boundary ──► Human Approval ──► Controlled Execution (T_exec) ──► VERIFYING ──► Fresh Independent Proof (T_proof > T_exec) ──► VerificationGate ──► RESOLVED
```

When an agent sends an email, calls an API, or updates a ticket, that is **action execution**, not **obligation fulfillment**. Closing a promise prematurely leads to missed milestones, broken vendor SLAs, and compliance blindspots. 

Covenant solves this by separating **agent reasoning**, **deterministic governance**, and **independent verification**.

---

## Target Users & Why It Matters

- **Consultancies & Agencies**: Managing multi-stakeholder client approvals, milestone acceptance notices, and billing triggers.
- **Operations & Project Leaders**: Tracking vendor SLAs, equipment repairs, material shipments, and cross-department dependencies.
- **Enterprise Account Teams**: Maintaining accountability over promises made *to* clients (`WE_OWE_THEM`) versus commitments owed *by* clients and partners (`THEY_OWE_US`).

---

## System Architecture

Covenant pairs the reasoning and tool execution capabilities of the **AWS Strands Agents SDK** with a deterministic **Governed Agent Runtime**:

```text
User / Operator
      │
      ▼
Covenant UI / API (FastAPI + React 18 / Vite)
      │
      ▼
SupervisorAgent (Multi-Agent Orchestrator)
      │
      ├── CommitmentAgent (Discovery & Semantic Extraction)
      ├── EvidenceAgent (Corroboration, Gaps & Contradictions)
      ├── ResolutionAgent (Remedial Action Formulation)
      ├── PolicyAgent (Autonomy vs Approval Guardrails)
      └── VerificationAgent (Independent Proof Evaluation)
      │
      ▼
Strands Agents SDK (strands-agents 1.54.0)
      │  ├── Agent(model=..., tools=..., system_prompt=...)
      │  └── Native @tool Declarations & Streaming Event Protocol
      │
      ▼
Governed Agent Runtime
      │
      ├── Policy / Authorization Engine (Deterministic Guardrails)
      ├── Human Approval Gate (Mandatory for External / High-Risk)
      ├── Execution Engine (Controlled Dispatch at T_exec)
      ├── Idempotency Store (Duplicate & Replay Defense)
      ├── Persistence Layer (SQLite WAL / Audit Event Log)
      └── VerificationGate (T_proof > T_exec Independent Verification)
      │
      ▼
External Tools & Enterprise Evidence
  (Email threads, MSA contracts, invoices, milestone trackers, vendor tickets)
```

---

## How Covenant Works

1. **Commitment Discovery**: Scans enterprise communications and contracts to extract structured commitments (promisor, promisee, deadline, deliverables, directional obligation).
2. **Evidence Synthesis**: Cross-references multiple data sources to identify facts, inferences, corroborated records, evidence gaps, and contradictions.
3. **Risk Calculation**: Computes risk deterministically based on deadlines, evidence gaps, and downstream blocked dependencies.
4. **Remediation Proposal**: Proposes concrete remedial actions (e.g. polite contractual follow-up citing governing MSA clauses).
5. **Deterministic Policy Boundary**: Evaluates action safety. Autonomous execution is permitted only for low-risk, internal operations. External communications (`RULE-EXT-COMM`) and high-risk actions strictly require human authorization.
6. **Human Approval Gate**: Operators inspect context, evidence checklists, and draft messages in the interactive Decision Surface before authorizing execution.
7. **Controlled Execution ($T_{\text{exec}}$)**: Dispatches authorized actions via the ExecutionEngine with cryptographic idempotency keys, transitioning state to `VERIFYING`—never directly to `RESOLVED`.
8. **Independent Verification ($T_{\text{proof}} > T_{\text{exec}}$)**: Validates incoming counterparty evidence against contractual acceptance criteria. Only fresh, independent proof timestamped after execution permits transition to `RESOLVED (VERIFIED)`.

---

## Strands Agents Integration

Covenant builds natively on the AWS Strands Agents SDK (`strands-agents`):

- **Specialist Agents**: `CommitmentAgent`, `EvidenceAgent`, `ResolutionAgent`, `PolicyAgent`, `VerificationAgent`, and `SupervisorAgent` all instantiate `strands.Agent`.
- **Native Tools**: Defined via the Strands `@tool` decorator (`scan_workspace`, `get_commitment_details`, `propose_remediation_action`, `request_human_approval`, `verify_commitment_evidence`).
- **Pluggable Model Layer**:
  - **Deterministic Provider (`COVENANT_MODEL_PROVIDER=deterministic`) [Default]**: Fully offline, reproducible reasoning provider implementing the Strands `Model` streaming interface for zero-dependency local execution, CI, and evaluation.
  - **Local Ollama Provider (`COVENANT_MODEL_PROVIDER=ollama`)**: Connects to local Ollama servers (`http://localhost:11434`, `llama3:latest`).
  - **Amazon Bedrock Provider (`COVENANT_MODEL_PROVIDER=bedrock`)**: Direct integration with Strands `BedrockModel` (`strands.models.bedrock.BedrockModel`) supporting Claude, Nova, and other Bedrock foundation models via standard AWS credential chains.

### Agentic Reasoning vs. Deterministic Authority

Covenant strictly separates probabilistic intelligence from deterministic authority:
- **Where Strands Agents Reason**: Semantic extraction of commitments from unstructured text, multi-source evidence interpretation, gap and contradiction deduction, and contextual drafting of remedial notices.
- **Where Governed Runtime Enforces Authority**: Deterministic state machine transitions, immutable policy rules (e.g. `RULE-EXT-COMM` requiring human approval for external messages), cryptographic idempotency, and the VerificationGate ($T_{\text{proof}} > T_{\text{exec}}$) that prevents self-declared fulfillment. Model hallucination cannot bypass these non-negotiable boundaries.

---

## Agentic Evaluation & Safety Benchmark

Covenant includes a reproducible, deterministic 43-scenario evaluation and adversarial robustness suite (`tests/test_agentic_benchmark.py`, `tests/test_adversarial_benchmark.py`).

The benchmark tests whether Covenant adheres to its safety invariants under adversarial pressure, including language variations, boundary timestamps, cross-commitment contamination, authority conflicts, and approval replays:

### Verified Zero-Tolerance Safety Invariants

| Invariant Metric | Target | Measured Result |
|---|---|---|
| **Approval Bypass Rate** | 0% | **0% (0 / 43)** |
| **False Resolution Rate** | 0% | **0% (0 / 43)** |
| **Stale-Proof Acceptance Rate** | 0% | **0% (0 / 43)** |
| **Execution / Fulfillment Conflation** | 0% | **0% (0 / 43)** |
| **Cross-Commitment Leakage Rate** | 0% | **0% (0 / 43)** |
| **Event-Order Semantic Divergence** | 0% | **0% (0 / 43)** |
| **Approval Replay Acceptance Rate** | 0% | **0% (0 / 43)** |
| **Duplicate Side-Effect Rate** | 0% | **0% (0 / 43)** |
| **Partial-Fulfillment False Resolution** | 0% | **0% (0 / 43)** |
| **Negative-Language False-Positive Rate** | 0% | **0% (0 / 43)** |

### Canonical Regression Anchors
- `ATLAS-GOLDEN`: Full positive flow: Discovery → gap detected → HIGH risk → policy gate → human approval → execution ($T_{\text{exec}}$) → `VERIFYING` → fresh counterparty proof ($T_{\text{proof}} > T_{\text{exec}}$) → `RESOLVED (VERIFIED)`.
- `ATLAS-NEGATIVE`: Counterparty rejection / missing post-dispatch proof leaves commitment in `VERIFYING` / `FAILED` and explicitly refuses resolution.

---

## Quickstart & Local Setup

Covenant is designed to be clone-and-run without cloud credentials, API keys, or GPU infrastructure.

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 2. Environment Configuration
Copy the example environment configuration:
```bash
cp .env.example .env
```
Default values run in offline deterministic mode with zero external dependencies.

### 3. Backend Setup & Test Suite
```bash
# Install Python dependencies (including strands-agents)
pip install -e .

# Run full test suite (144 unit and integration tests)
pytest -o asyncio_mode=auto -q

# Run the 43-scenario Agentic Evaluation Benchmark
pytest -o asyncio_mode=auto -q tests/test_agentic_benchmark.py tests/test_adversarial_benchmark.py

# Start FastAPI backend server (port 8000)
uvicorn covenant.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Frontend Setup
In a separate terminal:
```bash
cd frontend
npm install
npm run build    # Validates production bundle
npm run dev      # Starts local dev server (port 5173)
```

Open `http://localhost:5173` in your browser.

---

## Synthetic Workspace Dataset: Northstar Studio

Covenant includes a realistic multi-source synthetic workspace for **Northstar Studio**:
1. **Project Atlas Phase 2 Formal Approval**: Promised by Sarah Jenkins (VP of Digital, Meridian Global) by Sep 5; overdue; downstream Phase 3 frontend engineering blocked per MSA Section 4.2; Risk: HIGH.
2. **Apex Industrial Repairs**: Guaranteed laser cutter repair by Sep 2; overdue; technician visited but error code E-402 persists; VerificationGate refuses resolution.
3. **Lumina Materials Shipment**: Acrylic panels promised by Sep 4; customs delay notification detected; under active investigation.
4. **Horizon Health Brand Kit**: Internal commitment owed by Northstar Studio to Horizon Health by Sep 10; on track.
5. **Veloce Labs Invoice**: Net 30 payment due Sep 14.

---

## Documentation Index

- [docs/ARCHITECTURE.md](file:///Users/urjasoft/Documents/AgentOS/projects/covenant/docs/ARCHITECTURE.md): Comprehensive architecture, state machine specification, and runtime contracts.
- [docs/hackathon-readiness.md](file:///Users/urjasoft/Documents/AgentOS/projects/covenant/docs/hackathon-readiness.md): Submission compliance matrix mapped to official hackathon rules.
- [docs/demo-script.md](file:///Users/urjasoft/Documents/AgentOS/projects/covenant/docs/demo-script.md): 5-minute video walkthrough script with positive and negative verification flows.
- [docs/DEMO_SCENARIOS.md](file:///Users/urjasoft/Documents/AgentOS/projects/covenant/docs/DEMO_SCENARIOS.md): Detailed walkthrough of Northstar Studio demo scenarios.
- [.env.example](file:///Users/urjasoft/Documents/AgentOS/projects/covenant/.env.example): Exhaustive environment variable reference.

---

## Disclosures & Known Limitations

- **Deterministic Benchmark**: The 43-scenario evaluation suite is a deterministic engineering and governance regression benchmark over synthetic enterprise scenarios, not an open-ended scientific evaluation of unrestricted frontier LLMs.
- **Domain Scope**: The scenarios cover core enterprise commitments (consulting deliverables, vendor equipment repair, material shipments, invoices). Extending to novel domains requires configuring domain-specific verifiers and policy rules.
- **AWS Bedrock Availability**: The Amazon Bedrock Strands provider is fully implemented and tested. In environments where AWS account-level model access is restricted, the runtime operates safely offline via the deterministic or Ollama providers without loss of governance invariants.

---

## License

This project is licensed under the MIT License — see the [LICENSE](file:///Users/urjasoft/Documents/AgentOS/projects/covenant/LICENSE) file for details.
