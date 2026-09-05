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
