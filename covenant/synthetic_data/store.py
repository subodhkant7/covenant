"""Query Store for Northstar Studio Synthetic Workspace with Context-Local Isolation Support."""

import contextvars
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from covenant.synthetic_data.dataset import (
    SYNTHETIC_CALENDAR,
    SYNTHETIC_CONTRACTS,
    SYNTHETIC_EMAILS,
    SYNTHETIC_INVOICES,
    SYNTHETIC_PROJECTS,
)


class SyntheticWorkspaceStore:
    """In-memory searchable store of synthetic workspace artifacts."""

    def __init__(self):
        self.emails = list(SYNTHETIC_EMAILS)
        self.contracts = list(SYNTHETIC_CONTRACTS)
        self.projects = list(SYNTHETIC_PROJECTS)
        self.invoices = list(SYNTHETIC_INVOICES)
        self.calendar = list(SYNTHETIC_CALENDAR)
        self.escalations: List[Dict[str, Any]] = []

    def search_emails(self, query: str) -> List[Dict[str, Any]]:
        """Search email subject, sender, and body."""
        q = query.lower()
        return [
            e for e in self.emails
            if q in e["subject"].lower()
            or q in e["body"].lower()
            or q in e["from"].lower()
            or any(q in t.lower() for t in e["to"])
        ]

    def get_email_by_id(self, email_id: str) -> Optional[Dict[str, Any]]:
        """Get single email record."""
        return next((e for e in self.emails if e["id"].lower() == email_id.lower()), None)

    def search_contracts(self, query: str) -> List[Dict[str, Any]]:
        """Search contract titles, parties, and clauses."""
        q = query.lower()
        results = []
        for c in self.contracts:
            match = (
                q in c["title"].lower()
                or any(q in p.lower() for p in c["parties"])
                or any(q in cl["text"].lower() or q in cl["title"].lower() for cl in c.get("key_clauses", []))
            )
            if match:
                results.append(c)
        return results

    def get_contract_by_id(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Get single contract record."""
        return next((c for c in self.contracts if c["id"].lower() == contract_id.lower()), None)

    def search_projects(self, query: str) -> List[Dict[str, Any]]:
        """Search projects and milestones."""
        q = query.lower()
        results = []
        for p in self.projects:
            match = (
                q in p["name"].lower()
                or q in p.get("client", "").lower()
                or q in p.get("status", "").lower()
                or any(q in m["title"].lower() for m in p.get("milestones", []))
            )
            if match:
                results.append(p)
        return results

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get single project record."""
        return next((p for p in self.projects if p["id"].lower() == project_id.lower()), None)

    def search_invoices(self, query: str) -> List[Dict[str, Any]]:
        """Search invoices by client, vendor, or ID."""
        q = query.lower()
        return [
            inv for inv in self.invoices
            if q in inv.get("client", "").lower()
            or q in inv.get("vendor", "").lower()
            or q in inv["id"].lower()
            or q in inv.get("status", "").lower()
        ]

    def get_calendar_events(self) -> List[Dict[str, Any]]:
        """List all calendar events."""
        return list(self.calendar)

    def send_email(
        self,
        from_addr: str,
        to_addrs: List[str],
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Actually write an outbound email into the synthetic workspace."""
        new_id = f"EML-OUT-{len(self.emails) + 100}"
        record = {
            "id": new_id,
            "thread_id": thread_id or "TH-FOLLOWUP",
            "date": datetime.now(timezone.utc).isoformat(),
            "from": from_addr,
            "to": to_addrs,
            "subject": subject,
            "body": body,
            "attachments": [],
        }
        self.emails.append(record)
        return record

    def record_escalation(self, commitment_id: str, title: str, rationale: str) -> Dict[str, Any]:
        """Record formal dispute escalation in workspace."""
        if not hasattr(self, "escalations"):
            self.escalations = []
        esc = {
            "id": f"ESC-{len(self.escalations) + 1}",
            "commitment_id": commitment_id,
            "title": title,
            "rationale": rationale,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.escalations.append(esc)
        return esc

    def simulate_client_reply(self, commitment_id: str) -> Optional[Dict[str, Any]]:
        """
        'World Changes' Demo Mechanism:
        Simulates an external party observing the follow-up and sending a reply.
        """
        if "atlas" in commitment_id.lower():
            reply_id = f"EML-REPLY-{len(self.emails) + 1}"
            reply = {
                "id": reply_id,
                "thread_id": "TH-ATLAS-APPROVAL",
                "date": datetime.now(timezone.utc).isoformat(),
                "from": "Sarah Jenkins <sjenkins@meridianglobal.com>",
                "to": ["Alex North <alex@northstarstudio.com>"],
                "subject": "Re: Friendly Follow-up: Project Atlas Phase 2 Formal Approval",
                "body": (
                    "Hi Alex,\n\n"
                    "Apologies for the brief delay—our steering committee completed the review this morning. "
                    "We formally APPROVE the Phase 2 High-Fidelity UI System deliverables per MSA Section 4.2. "
                    "Please proceed immediately with Phase 3 frontend implementation.\n\n"
                    "Best regards,\nSarah Jenkins\nVP of Digital, Meridian Global"
                ),
                "attachments": ["Signed_Atlas_Phase2_Signoff.pdf"],
            }
            self.emails.append(reply)

            # Update project milestone status
            atlas_prj = self.get_project_by_id("PRJ-ATLAS")
            if atlas_prj:
                for m in atlas_prj.get("milestones", []):
                    if m["id"] == "M2":
                        m["status"] = "APPROVED_BY_CLIENT"
                        m["approved_at"] = datetime.now(timezone.utc).isoformat()
                    if m["id"] == "M3":
                        m["status"] = "UNBLOCKED_IN_PROGRESS"
            return reply

        elif "apex" in commitment_id.lower():
            reply_id = f"EML-REPLY-{len(self.emails) + 1}"
            reply = {
                "id": reply_id,
                "thread_id": "TH-APEX-REPAIR",
                "date": datetime.now(timezone.utc).isoformat(),
                "from": "Marcus Vance <m.vance@apexindustrialrepairs.com>",
                "to": ["Alex North <alex@northstarstudio.com>"],
                "subject": "Re: URGENT: Laser Cutter Calibration Incomplete — Repair Request SR-8841",
                "body": (
                    "Alex,\n\n"
                    "Understood. Dave is en route now with the replacement sensor module. Calibration will be completed "
                    "and signed off by 2 PM today.\n\n"
                    "Marcus Vance"
                ),
                "attachments": [],
            }
            self.emails.append(reply)
            return reply

        return None

    def reset(self):
        """Restore initial synthetic workspace data with deep copies."""
        import copy
        self.emails = copy.deepcopy(SYNTHETIC_EMAILS)
        self.contracts = copy.deepcopy(SYNTHETIC_CONTRACTS)
        self.projects = copy.deepcopy(SYNTHETIC_PROJECTS)
        self.invoices = copy.deepcopy(SYNTHETIC_INVOICES)
        self.calendar = copy.deepcopy(SYNTHETIC_CALENDAR)
        self.escalations = []


# Context-local isolation boundary for concurrent shadow execution
_current_workspace_store: contextvars.ContextVar[Optional[SyntheticWorkspaceStore]] = contextvars.ContextVar(
    "_current_workspace_store", default=None
)
_default_workspace_store = SyntheticWorkspaceStore()


class _WorkspaceStoreProxy:
    """
    Transparent proxy delegating to a context-local SyntheticWorkspaceStore if active,
    or falling back to the process-global default instance.
    Guarantees thread and async-coroutine isolation without monkey-patching globals.
    """

    def _get_active_store(self) -> SyntheticWorkspaceStore:
        store = _current_workspace_store.get()
        return store if store is not None else _default_workspace_store

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_active_store(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_active_store(), name, value)

    def __repr__(self) -> str:
        return repr(self._get_active_store())


# Global singleton instance (backed by proxy for shadow isolation)
workspace_store = _WorkspaceStoreProxy()
