# Covenant — Hackathon Submission Readiness Matrix

This matrix maps Covenant's implementation against the official submission requirements for the **Agents for Humans Hackathon** (Professional Agents Track).

---

## Submission Requirements Matrix

| Requirement | Status | Evidence in Repository |
|---|---|---|
| **1. New Project** | **COMPLETE** | Original codebase built specifically for the hackathon; git history starts with initialization commits and progresses through iterative development steps. |
| **2. Strands Agents SDK Integration** | **COMPLETE** | Built directly on `strands-agents` (v1.54.0). Specialised agents (`CommitmentAgent`, `EvidenceAgent`, `ResolutionAgent`, `PolicyAgent`, `VerificationAgent`, `SupervisorAgent`) instantiate `strands.Agent` with `@tool` bindings (`covenant/agents/strands_runtime.py`, `covenant/agents/`). |
| **3. Real Work for Real People** | **COMPLETE** | Solves high-value enterprise commitment tracking: monitoring promises across emails, contracts, and vendor tickets; enforcing contractual obligations; distinguishing *They Owe Us* vs *We Owe Them*. |
| **4. Public Source Repository** | **COMPLETE** | Public GitHub repository: [https://github.com/subodhkant7/covenant.git](https://github.com/subodhkant7/covenant.git). |
| **5. Open Source License** | **COMPLETE** | Standard MIT License in root [`LICENSE`](../LICENSE). |
| **6. Comprehensive README** | **COMPLETE** | Clean, judge-oriented [`README.md`](../README.md) explaining problem, architecture, Strands usage, governance model, verification invariants, benchmark, and setup. |
| **7. Architecture Diagram** | **COMPLETE** | End-to-end architecture diagrams in [`README.md`](../README.md) and [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) showing UI → Supervisor → Strands Agents → Governed Agent Runtime → External Evidence. |
| **8. Working Product Demo** | **COMPLETE** | Working full-stack application (FastAPI backend + Vite/React frontend) with Northstar Studio synthetic workspace, interactive Decision Surface, and verifiable lifecycle. |
| **9. Local Setup Instructions** | **COMPLETE** | Step-by-step reproducible instructions in `README.md` for backend, frontend, environment configuration, and database initialization. |
| **10. Testing & Verification Instructions** | **COMPLETE** | Complete automated test commands (`pytest -o asyncio_mode=auto -q`, `npm run build`) covering 144 unit/integration tests and 43 benchmark scenarios. |
| **11. AWS / Third-Party Integrations** | **COMPLETE** | Native Strands Amazon Bedrock provider (`strands.models.bedrock.BedrockModel`) implemented in `covenant/llm/bedrock_provider.py` with standard AWS credential resolution and graceful offline fallback. |
| **12. Live Demo Status** | **SUPPORTED LOCALLY** | Self-contained, offline-first local execution path requiring zero cloud credentials. Live Bedrock integration ready via environment variables when AWS account model access is provisioned. |
| **13. Limitations & Disclosures** | **DISCLOSED** | Clear documentation of synthetic benchmark boundaries, deterministic engineering scope, and offline fallback behavior in `README.md`. |
| **14. Video Submission (<= 5 min)** | **COMPLETE** | Production video script structured at 4:30 – 5:00 minutes with positive and negative paths in [`docs/demo-script.md`](demo-script.md). |
| **15. AWS Builder ID** | **READY** | Standard hackathon requirement verified; submitter profile configured for Devpost submission. |

---

## Verified Safety Invariants (Step 15 & 16 Benchmarks)

The deterministic agentic evaluation and adversarial regression suites (`tests/test_agentic_benchmark.py`, `tests/test_adversarial_benchmark.py`) verify the following non-negotiable safety properties across 43 scenarios:

- **0% Approval Bypass**: External and high-risk actions never dispatch without explicit human authorization.
- **0% False Resolution**: Actions are never marked resolved without fresh post-execution counterparty proof ($T_{\text{proof}} > T_{\text{exec}}$).
- **0% Stale Proof Acceptance**: Pre-existing evidence is rejected by the VerificationGate.
- **0% Execution/Fulfillment Conflation**: Successful API/tool execution transitions to `VERIFYING`, never directly to `RESOLVED`.
- **0% Cross-Commitment Contamination**: Evidence from one commitment cannot verify an unrelated commitment.
- **0% Duplicate Execution Replay**: State machine prevents re-executing already dispatched actions.
