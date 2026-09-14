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

Covenant strictly separates probabilistic intelligence from deterministic authority:

- **Strands Agents reason and propose**: Semantic extraction, multi-source evidence corroboration, gap detection, and remedy drafting.
- **The deterministic runtime governs**: State machine transitions, immutable policy rules (e.g. `RULE-EXT-COMM` requiring human approval), and cryptographic idempotency.
- **Authorized tools execute**: Controlled dispatch of emails, calendar checks, and ticket queries ($T_{\text{exec}}$) through deterministic interfaces.
- **Fresh external evidence verifies**: The non-bypassable `VerificationGate` ($T_{\text{proof}} > T_{\text{exec}}$) prevents self-declared fulfillment.

```text
React 18 / Vite (Interactive Surface)
        │
        ▼
FastAPI (REST API & Control Plane)
        │
        ▼
Strands Agents (strands-agents 1.54.0)
(CommitmentAgent, EvidenceAgent, ResolutionAgent, PolicyAgent, VerificationAgent)
        │
        ▼
Covenant Deterministic Runtime
(Policy Engine, Human Approval Gate, Idempotency Store, State Machine)
        │
        ▼
Authorized Tools (Controlled Dispatch at T_exec)
(Email, contracts, Jira tickets, calendar, vendor milestones)
        │
        ▼
External Evidence (Multi-source independent proof)
        │
        ▼
VerificationGate (T_proof > T_exec Independent Verification)
        │
        ▼
RESOLVED (VERIFIED)
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
  - **Google Gemini Provider (`COVENANT_MODEL_PROVIDER=gemini`) [CURRENT LIVE AWS PRODUCTION MODEL]**: Ultra-low-latency (~0.4s) model provider using `gemini-2.5-flash-lite` via Google Generative Language REST API with native Strands streaming and function-calling support. Configured strictly server-side with zero credentials in frontend or source control.
  - **Deterministic Provider (`COVENANT_MODEL_PROVIDER=deterministic`) [DEFAULT / OFFLINE / CI EVALUATION]**: Fully offline, reproducible reasoning provider implementing the Strands `Model` streaming interface for zero-dependency local execution, CI, and evaluation benchmark.
  - **Local Ollama Provider (`COVENANT_MODEL_PROVIDER=ollama`) [LOCAL DEVELOPMENT]**: Connects to local Ollama servers (`http://localhost:11434`, `minimax-m3:cloud`, `llama3:latest`) for offline local experimentation.
  - **Amazon Bedrock Provider (`COVENANT_MODEL_PROVIDER=bedrock`) [OPTIONAL AWS INTEGRATION PATH]**: Direct integration with Strands `BedrockModel` (`strands.models.bedrock.BedrockModel`) supporting Claude, Nova, and other Bedrock foundation models via standard AWS credential chains.

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

# Run full automated regression and evaluation suite
pytest -o asyncio_mode=auto -q

# Run the 43-scenario Agentic Evaluation Benchmark
pytest -o asyncio_mode=auto -q tests/test_agentic_benchmark.py tests/test_adversarial_benchmark.py

# Start FastAPI backend server (port 8000)
uvicorn covenant.api.main:app --host 0.0.0.0 --port 8000 --reload
```

> **Verified Test Status**: At the time of this submission, the regression suite reports **161 passed, 0 failures** (including 43 evaluation/adversarial benchmark scenarios, private reasoning safety tests, Gemini provider integration, and container readiness verification).


### 4. Frontend Setup
In a separate terminal:
```bash
cd frontend
npm install
npm run build    # Validates production bundle
npm run dev      # Starts local dev server (port 5173)
```

Open `http://localhost:5173` in your browser.

### 5. Docker Container Deployment

Covenant can be packaged and run locally as a self-contained container serving both the React frontend and FastAPI backend.

**Build Image**:
```bash
docker build -t covenant:local .
```

**Run Container (Default Port 8000)**:
```bash
docker run --rm -p 8000:8000 covenant:local
```

- **Health Check**: `curl http://127.0.0.1:8000/api/health`
- **Web UI**: Open `http://127.0.0.1:8000/` in your browser.

**Optional Port Override**:
```bash
docker run --rm \
  -e PORT=8899 \
  -p 8899:8899 \
  covenant:local
```

**Container Deployment Notes**:
- **Deterministic Provider**: Defaults to `COVENANT_MODEL_PROVIDER=deterministic` (offline, zero external credentials or cloud keys required).
- **Persistence Architecture**: SQLite with Write-Ahead Logging (WAL) is intentionally utilized for this single-task demo deployment. State initializes automatically on container startup.
- **Ephemeral State**: Container storage is ephemeral; replacing or restarting the container reinitializes the database from the synthetic workspace seed.
- **Production Scaling**: Multi-task / multi-replica production deployments behind a load balancer require migrating persistence to Amazon RDS PostgreSQL or a shared database layer.
- **Scope**: This container configuration prepares Covenant for single-task AWS ECS/Fargate deployment; live AWS cloud infrastructure deployment is handled separately.

### 6. Live AWS Cloud Deployment (Hackathon Judge Environment)

Covenant is actively deployed and publicly accessible in AWS `us-east-1` for live evaluation:

- **Public Web Application (SPA)**: [http://44.194.255.110/](http://44.194.255.110/)
- **Public DNS**: [http://ec2-44-194-255-110.compute-1.amazonaws.com](http://ec2-44-194-255-110.compute-1.amazonaws.com)
- **API Health**: `curl http://44.194.255.110/api/health`
- **Model Health**: `curl http://44.194.255.110/api/health/model`

**Architecture & Security Highlights**:
- **Instance**: AWS EC2 `t3.small` (Ubuntu 24.04 LTS, 2 GiB RAM, 30 GB gp3 EBS) in `us-east-1a`.
- **Model Backend**: Google Gemini API (`gemini-2.5-flash-lite`) providing ultra-low-latency (~0.4s) reasoning and tool selection.
- **Reverse Proxy**: Nginx proxying port 80 to internal FastAPI runtime on `127.0.0.1:8000` with strict HTTP security headers (`X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`).
- **Persistence**: SQLite with Write-Ahead Logging (WAL) providing atomic ACID transaction safety and immutable event auditing.
- **Network Ingress Protection**: Public access is restricted strictly to HTTP/HTTPS ports (80/443). Port 22 (SSH) is locked to the operator's IP; internal application port 8000 is never exposed.
- **Credential Hygiene**: API keys are isolated on the server in `/etc/covenant/covenant.env` (permissions `600`, owned by system user `covenant`). Zero credentials exist in the client bundle, logs, or repository.
- **Architectural Non-Dependencies**: Covenant intentionally does **NOT** use Firestore, Pub/Sub, Firebase, or Cloud Run. It does **NOT** run Ollama on EC2, and does **NOT** use Bedrock as the live production model.
- **Invariant Enforcement**: Execution success $\neq$ fulfillment. Action execution ($T_{\text{exec}}$) dispatches through authorized tools into `VERIFYING`, and only fresh post-dispatch external evidence ($T_{\text{proof}} > T_{\text{exec}}$) evaluated by the `VerificationGate` can transition state to `RESOLVED (VERIFIED)`.



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

- [SECURITY.md](SECURITY.md): Security policy, vulnerability reporting workflow, and synthetic data guarantees.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Comprehensive architecture, state machine specification, and runtime contracts.
- [docs/hackathon-readiness.md](docs/hackathon-readiness.md): Submission compliance matrix mapped to official hackathon rules.
- [docs/demo-script.md](docs/demo-script.md): 5-minute video walkthrough script with positive and negative verification flows.
- [docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md): Detailed walkthrough of Northstar Studio demo scenarios.
- [.env.example](.env.example): Exhaustive environment variable reference.

---

## Disclosures & Known Limitations

- **Deterministic Benchmark**: The 43-scenario evaluation suite is a deterministic engineering and governance regression benchmark over synthetic enterprise scenarios, not an open-ended scientific evaluation of unrestricted frontier LLMs.
- **Domain Scope**: The scenarios cover core enterprise commitments (consulting deliverables, vendor equipment repair, material shipments, invoices). Extending to novel domains requires configuring domain-specific verifiers and policy rules.
- **AWS Bedrock Availability**: The Amazon Bedrock Strands provider is fully implemented and tested. In environments where AWS account-level model access is restricted, the runtime operates safely offline via the deterministic or Ollama providers without loss of governance invariants.
- **Simulation Endpoint Security**: Synthetic counterparty injection routes (`/api/simulate/*`) used for demo and adversarial evaluation are protected by a dedicated server-side secret (`COVENANT_SIMULATION_TOKEN` via `X-Simulation-Token` header) with constant-time verification. Normal read/demo APIs remain unauthenticated, and production secrets must never be committed.


---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
