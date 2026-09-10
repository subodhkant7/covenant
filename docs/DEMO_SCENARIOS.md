# Covenant — 5-Minute Hackathon Demo Scenarios

These three coherent scenarios demonstrate real agentic behavior: discovery, multi-source corroboration, policy boundaries, human-in-the-loop decision making, and independent verification.

---

## Scenario 1: Autonomous Discovery & Drift Investigation

**Story**: Project Atlas Phase 2 Deliverable Formal Sign-Off
1. **The Promise**: Sarah Jenkins (VP of Digital, Meridian Global) promised formal written approval for Phase 2 UI deliverables by Friday, Sep 5 (Email `EML-102`).
2. **Contract Clause**: Master Services Agreement `CTR-2026-081` Section 4.2 requires Client review within 2 business days.
3. **Drift Detection**: The agent kernel detects that the deadline has elapsed without signed confirmation. Downstream Phase 3 is blocked.
4. **Agent Action**:
   - `CommitmentAgent` extracts structured promise and participants.
   - `EvidenceAgent` searches email threads and project milestone `PRJ-ATLAS`.
   - `ResolutionAgent` drafts a polite, legally grounded follow-up citing Section 4.2.
   - `PolicyAgent` enforces that external emails require human sign-off.
   - The commitment transitions to `AWAITING_APPROVAL`.

---

## Scenario 2: Decision Surface & Human Approval

**Story**: Authorizing the Follow-Up Dispatch
1. **User Action**: The user opens the **Decision Surface** tab.
2. **Inspection**:
   - Promisor: Sarah Jenkins (Meridian Global Corp)
   - Status: Overdue by 3 days
   - Evidence Checklist: Milestone submitted Sep 3, contract clause 4.2 identified, zero approval emails received.
   - Risk: HIGH (Downstream Phase 3 frontend blocked) | Confidence: 96%
   - Proposed Draft Message: Pre-composed with dates and references.
3. **Human Decision**: The user clicks **[Approve & Dispatch]** (or modifies the draft).
4. **Agent Execution**:
   - State machine validates human approval.
   - Transitions to `EXECUTING` -> `VERIFYING`.
   - Action history is permanently recorded in the event log.

---

## Scenario 3: Independent Verification & Closure

**Story**: Verifying Completion Before Resolving
1. **The Rule**: A commitment is never marked `RESOLVED` just because a follow-up was sent or someone claims it is done.
2. **Verification Agent Run**:
   - `VerificationAgent` runs an independent verification pass against workspace evidence.
   - If signed approval email is verified: The state machine executes legal transition from `VERIFYING` to `RESOLVED`, sets `resolution_timestamp`, and updates the operational map.
   - If no approval is found: The commitment remains in `INVESTIGATING` / `VERIFYING` state.
