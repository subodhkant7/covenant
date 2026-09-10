# Covenant — 5-Minute Product Walkthrough Video Script

**Target Duration**: 4:30 – 5:00 minutes  
**Presenter**: Product / Technical Lead  
**Format**: Screen capture with live voiceover  

---

## The Core Thesis (Spoken Hook)

> **"Most agents stop when the action succeeds. Covenant doesn't. It asks whether the real-world commitment was fulfilled."**

---

## Video Timeline & Stage Directions

### [0:00 – 0:45] Act 1: The Problem — Execution vs. Fulfillment
- **Visual**: Slide / Landing view of Covenant Commitment Map. 
- **Spoken**:
  "People make commitments.
  Those commitments become buried across emails, contracts, project systems, and approvals.
  Most automation stops when the action succeeds.
  Covenant does not.
  It monitors the commitment, collects evidence, proposes remediation, gets approval when required, executes the action, and then asks:
  'Did the commitment actually happen?'
  Only independent fresh evidence can resolve it.

  This is **Covenant**—autonomous commitment intelligence powered by AWS Strands Agents and a strictly governed runtime. Execution is an event; fulfillment is an outcome."

---

### [0:45 – 1:45] Act 2: Discovery, Evidence Reasoning & Risk
- **Visual**: Switch to **Commitment Map** showing Northstar Studio workspace. Click on **Project Atlas Phase 2 Deliverable Formal Sign-Off**.
- **Spoken**:
  "Let's look at a live scenario. Northstar Studio delivered Phase 2 design work for Meridian Global. 
  Covenant's `CommitmentAgent` extracted the obligation: Sarah Jenkins promised written sign-off by September 5th.
  Next, our `EvidenceAgent` investigated across systems:
  - **Fact**: Milestone was delivered September 3rd.
  - **Fact**: Contract clause Section 4.2 requires client review within 2 business days.
  - **Evidence Gap**: Zero sign-off emails or signed documents detected.
  - **Inference**: Downstream Phase 3 frontend engineering is now blocked.
  Because downstream work is blocked and the deadline has elapsed, Covenant computes Risk as **HIGH**.
  Notice: Covenant separates factual records from inferences and penalizes certainty when evidence is missing."

---

### [1:45 – 2:45] Act 3: Policy Boundary & Human-in-the-Loop Decision Surface
- **Visual**: Navigate to **Decision Surface** tab. Focus on the Atlas pending action card.
- **Spoken**:
  "Our `ResolutionAgent` drafted a polite, legally grounded follow-up citing Section 4.2. 
  But can the agent send it autonomously? **No.**
  Covenant's deterministic `PolicyAgent` evaluates rule `RULE-EXT-COMM`: any external client communication or high-risk action strictly requires human authorization.
  The model cannot override this policy. 
  Here in the Decision Surface, the human operator sees:
  - Promisor and context (Sarah Jenkins, Meridian Global)
  - Risk level: **HIGH** (Downstream Phase 3 blocked)
  - Full evidence corroboration checklist
  - The exact draft email
  I click **[Approve & Dispatch]**."

---

### [2:45 – 3:30] Act 4: Execution vs. Verifying State (T_exec)
- **Visual**: Click Approve. Watch status change from `AWAITING_APPROVAL` → `EXECUTING` → `VERIFYING`.
- **Spoken**:
  "The ExecutionEngine records human sign-off, executes the dispatch at timestamp $T_{\text{exec}}$, and writes an immutable audit record.
  Now notice the critical detail: 
  **The commitment is NOT marked RESOLVED.**
  It moves to **VERIFYING**.
  Sending the email was merely the execution. The commitment remains open because the client has not yet provided the promised sign-off."

---

### [3:30 – 4:15] Act 5: The Golden Path — Independent Verification (T_proof > T_exec)
- **Visual**: Trigger incoming evidence check / monitoring cycle. View updated evidence panel showing Sarah's response with signed PDF.
- **Spoken**:
  "Hours later, Sarah Jenkins replies with the signed Phase 2 approval attachment.
  Our `VerificationAgent` evaluates this against Covenant's `VerificationGate`:
  - Is the proof independent of the agent? Yes.
  - Is its timestamp $T_{\text{proof}}$ strictly greater than the dispatch time $T_{\text{exec}}$? Yes.
  - Does the document satisfy the contractual acceptance criteria? Yes.
  Only now does the deterministic state machine transition the commitment to **RESOLVED (VERIFIED)**.
  Every transition is cryptographically traceable in the audit log."

---

### [4:15 – 4:45] Act 6: The Negative Path — Refusing False Resolution
- **Visual**: Click on **Apex Industrial Laser Cutter Repair** commitment.
- **Spoken**:
  "Now consider the negative case: Apex guaranteed our laser cutter would be fixed.
  A technician visit was dispatched. The action succeeded ($T_{\text{exec}}$).
  Traditional tools would close the ticket. 
  Covenant checks the physical sensor telemetry post-visit: diagnostic error code **E-402** is still active. 
  Because fulfillment is absent, the VerificationGate **refuses resolution**. 
  The commitment stays in `INVESTIGATING` / `VERIFYING`, alerts the team, and never allows a false positive.
  Execution is never confused with fulfillment."

---

### [4:45 – 5:00] Act 7: Closing & Open Source
- **Visual**: Full dashboard view showing They Owe / We Owe operational balance.
- **Spoken**:
  "Covenant combines the reasoning flexibility of AWS Strands Agents with the non-negotiable safety of a deterministic governed runtime.
  Validated against a 43-scenario adversarial safety benchmark with zero false resolutions and zero policy bypasses.
  Thank you."
