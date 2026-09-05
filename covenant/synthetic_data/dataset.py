"""Coherent Synthetic Workspace Dataset for Northstar Studio."""

from datetime import datetime, timezone
from typing import Any, Dict, List


def parse_dt(dt_str: str) -> datetime:
    """Helper to parse ISO datetime string with UTC timezone."""
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


SYNTHETIC_EMAILS: List[Dict[str, Any]] = [
    {
        "id": "EML-101",
        "thread_id": "TH-ATLAS-APPROVAL",
        "date": "2026-09-03T10:15:00",
        "from": "Alex North <alex@northstarstudio.com>",
        "to": ["Sarah Jenkins <sjenkins@meridianglobal.com>"],
        "subject": "Project Atlas — Phase 2 UI Deliverables for Approval",
        "body": (
            "Hi Sarah,\n\n"
            "We have finalized all high-fidelity screens and interaction specs for Project Atlas Phase 2. "
            "Please find the deliverable package attached. As per Section 4.2 of our Master Services Agreement, "
            "please review and send over formal approval so we can begin the Phase 3 frontend implementation.\n\n"
            "Best regards,\nAlex North\nDesign Director, Northstar Studio"
        ),
        "attachments": ["Atlas_Phase2_Design_System_v2.1.pdf"],
    },
    {
        "id": "EML-102",
        "thread_id": "TH-ATLAS-APPROVAL",
        "date": "2026-09-03T14:30:00",
        "from": "Sarah Jenkins <sjenkins@meridianglobal.com>",
        "to": ["Alex North <alex@northstarstudio.com>"],
        "subject": "Re: Project Atlas — Phase 2 UI Deliverables for Approval",
        "body": (
            "Hi Alex,\n\n"
            "Received, looks thorough! I will review this with our executive steering committee "
            "and promise to provide our formal written sign-off by Friday, September 5th at 5 PM EST.\n\n"
            "Thank you,\nSarah Jenkins\nVP of Digital, Meridian Global"
        ),
        "attachments": [],
    },
    {
        "id": "EML-201",
        "thread_id": "TH-APEX-REPAIR",
        "date": "2026-08-29T09:00:00",
        "from": "Marcus Vance <m.vance@apexindustrialrepairs.com>",
        "to": ["Alex North <alex@northstarstudio.com>"],
        "subject": "Precision CNC Laser Calibration & Repair Confirmation",
        "body": (
            "Alex,\n\n"
            "We have scheduled your repair request SR-8841. Our field technician Dave will be on-site "
            "Tuesday Sep 1st and we guarantee the laser head calibration and mirror repair will be 100% complete "
            "and tested by Wednesday, September 2nd EOD.\n\n"
            "Marcus Vance\nService Operations, Apex Industrial Repairs"
        ),
        "attachments": ["Work_Order_SR8841.pdf"],
    },
    {
        "id": "EML-301",
        "thread_id": "TH-LUMINA-PO9410",
        "date": "2026-08-26T11:20:00",
        "from": "Rachel Cole <rachel.cole@luminamaterials.com>",
        "to": ["Alex North <alex@northstarstudio.com>"],
        "subject": "Order Confirmation PO-9410 — High-Grade Acrylic Panels",
        "body": (
            "Hello Alex,\n\n"
            "Thank you for order PO-9410 (50 units matte acrylic panels). We confirm guaranteed dispatch "
            "on September 1st, with delivery to your studio by September 4th.\n\n"
            "Rachel Cole\nLumina Materials Logistics"
        ),
        "attachments": ["PO-9410_Invoice.pdf"],
    },
    {
        "id": "EML-302",
        "thread_id": "TH-LUMINA-PO9410",
        "date": "2026-09-02T16:45:00",
        "from": "Lumina Tracking System <notifications@luminamaterials.com>",
        "to": ["Alex North <alex@northstarstudio.com>"],
        "subject": "Shipment Tracking Update: PO-9410 (Customs Notice)",
        "body": (
            "Shipment Update for Tracking #LUM-882194:\n"
            "Status: Regional Customs Inspection Hold.\n"
            "Estimated delay: 3-5 business days beyond original Sep 4 arrival date.\n"
            "Carrier: FreightLink Express"
        ),
        "attachments": [],
    },
    {
        "id": "EML-401",
        "thread_id": "TH-HORIZON-BRAND",
        "date": "2026-09-01T15:00:00",
        "from": "Alex North <alex@northstarstudio.com>",
        "to": ["David Kroll <dkroll@horizonhealth.org>"],
        "subject": "Horizon Health Brand Identity Kit Timeline",
        "body": (
            "Hi David,\n\n"
            "Confirming our milestone discussion from this morning. Northstar Studio will deliver the complete "
            "Horizon Health Brand Identity Guidelines and asset kit by September 10th, 2026.\n\n"
            "Best,\nAlex North"
        ),
        "attachments": [],
    },
]

SYNTHETIC_CONTRACTS: List[Dict[str, Any]] = [
    {
        "id": "CTR-2026-081",
        "title": "Master Services Agreement — Meridian Global & Northstar Studio",
        "parties": ["Northstar Studio LLC", "Meridian Global Corp"],
        "effective_date": "2026-06-01",
        "key_clauses": [
            {
                "section": "4.2",
                "title": "Milestone Review and Sign-off",
                "text": (
                    "Client shall review each submitted Phase Deliverable within two (2) business days of receipt. "
                    "Client shall provide written approval or specific itemized feedback. If no response is received, "
                    "Contractor may issue a formal reminder notice."
                ),
            },
            {
                "section": "7.1",
                "title": "Payment Terms",
                "text": "Milestone billing shall be invoiced upon Phase sign-off, net 15 days.",
            },
        ],
    },
    {
        "id": "CTR-2026-092",
        "title": "Design Retainer Agreement — Horizon Health",
        "parties": ["Northstar Studio LLC", "Horizon Health Foundation"],
        "effective_date": "2026-08-15",
        "key_clauses": [
            {
                "section": "2.1",
                "title": "Brand Assets Delivery",
                "text": "Complete visual identity package due on or before September 10, 2026.",
            }
        ],
    },
]

SYNTHETIC_PROJECTS: List[Dict[str, Any]] = [
    {
        "id": "PRJ-ATLAS",
        "name": "Project Atlas Mobile & Web Experience",
        "client": "Meridian Global Corp",
        "status": "IN_PROGRESS",
        "milestones": [
            {
                "id": "M1",
                "title": "Phase 1 UX Research & Wireframes",
                "status": "COMPLETED",
                "completed_date": "2026-08-10",
            },
            {
                "id": "M2",
                "title": "Phase 2 High-Fidelity UI System",
                "status": "SUBMITTED_AWAITING_APPROVAL",
                "submitted_date": "2026-09-03",
                "approval_promised_date": "2026-09-05",
                "current_status_notes": "Deliverables delivered Sep 3. Approval overdue as of Sep 6.",
            },
            {
                "id": "M3",
                "title": "Phase 3 Frontend Implementation",
                "status": "BLOCKED_ON_APPROVAL",
                "target_date": "2026-10-01",
            },
        ],
    },
    {
        "id": "PRJ-STUDIO-OPS",
        "name": "Northstar Studio Fabrication Lab Maintenance",
        "status": "DEGRADED",
        "notes": "CNC Laser cutter head uncalibrated. Awaiting technician repair completion by Apex Industrial.",
    },
    {
        "id": "PRJ-HORIZON",
        "name": "Horizon Health Brand Identity",
        "client": "Horizon Health Foundation",
        "status": "ON_TRACK",
        "progress_percent": 85,
        "due_date": "2026-09-10",
    },
]

SYNTHETIC_INVOICES: List[Dict[str, Any]] = [
    {
        "id": "INV-2026-044",
        "client": "Veloce Labs Inc",
        "amount": 18500.00,
        "issue_date": "2026-08-15",
        "due_date": "2026-09-14",
        "status": "PENDING",
        "terms": "Net 30",
    },
    {
        "id": "INV-APEX-992",
        "vendor": "Apex Industrial Repairs",
        "amount": 450.00,
        "issue_date": "2026-09-01",
        "due_date": "2026-09-15",
        "status": "HELD_PENDING_COMPLETION",
        "notes": "Invoice diagnostic fee held until Dave completes calibration on SR-8841.",
    },
]

SYNTHETIC_CALENDAR: List[Dict[str, Any]] = [
    {
        "id": "CAL-301",
        "title": "On-Site Repair: Dave (Apex Industrial)",
        "start": "2026-09-01T09:00:00",
        "end": "2026-09-01T12:00:00",
        "attendees": ["alex@northstarstudio.com", "dave@apexindustrialrepairs.com"],
        "status": "COMPLETED",
    },
    {
        "id": "CAL-402",
        "title": "Expected Delivery: Acrylic Panels (Lumina PO-9410)",
        "start": "2026-09-04T10:00:00",
        "end": "2026-09-04T11:00:00",
        "status": "MISSED_DELAYED",
    },
]
