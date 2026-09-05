"""Workspace source interrogation tools."""

from typing import Any
from covenant.synthetic_data.store import workspace_store
from covenant.tools.base import BaseTool, ToolResult, global_tool_registry


class SearchEmailTool(BaseTool):
    name = "search_email"
    description = "Search emails by keyword, sender, recipient, or subject."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"}
        },
        "required": ["query"],
    }

    async def execute(self, query: str, **kwargs: Any) -> ToolResult:
        results = workspace_store.search_emails(query)
        return ToolResult(success=True, data={"count": len(results), "emails": results})


class ReadEmailTool(BaseTool):
    name = "read_email"
    description = "Fetch full email message content and metadata by ID."
    parameters_schema = {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "Email ID (e.g. EML-101)"}
        },
        "required": ["email_id"],
    }

    async def execute(self, email_id: str, **kwargs: Any) -> ToolResult:
        email = workspace_store.get_email_by_id(email_id)
        if not email:
            return ToolResult(success=False, error=f"Email '{email_id}' not found.")
        return ToolResult(success=True, data=email)


class SearchContractTool(BaseTool):
    name = "search_contract"
    description = "Search contracts and service agreements for clauses, parties, or terms."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Contract search term"}
        },
        "required": ["query"],
    }

    async def execute(self, query: str, **kwargs: Any) -> ToolResult:
        contracts = workspace_store.search_contracts(query)
        return ToolResult(success=True, data={"count": len(contracts), "contracts": contracts})


class GetProjectStatusTool(BaseTool):
    name = "get_project_status"
    description = "Retrieve current milestones, blockers, and progress for a project."
    parameters_schema = {
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project ID (e.g. PRJ-ATLAS)"}
        },
        "required": ["project_id"],
    }

    async def execute(self, project_id: str, **kwargs: Any) -> ToolResult:
        project = workspace_store.get_project_by_id(project_id)
        if not project:
            return ToolResult(success=False, error=f"Project '{project_id}' not found.")
        return ToolResult(success=True, data=project)


class GetInvoiceStatusTool(BaseTool):
    name = "get_invoice_status"
    description = "Search and check status of client or vendor invoices."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Invoice ID or client name"}
        },
        "required": ["query"],
    }

    async def execute(self, query: str, **kwargs: Any) -> ToolResult:
        invoices = workspace_store.search_invoices(query)
        return ToolResult(success=True, data={"count": len(invoices), "invoices": invoices})


class SearchCalendarTool(BaseTool):
    name = "search_calendar"
    description = "Query calendar events, scheduled repairs, or expected delivery windows."
    parameters_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        events = workspace_store.get_calendar_events()
        return ToolResult(success=True, data={"count": len(events), "events": events})


# Auto-register tools
def register_workspace_tools():
    global_tool_registry.register(SearchEmailTool())
    global_tool_registry.register(ReadEmailTool())
    global_tool_registry.register(SearchContractTool())
    global_tool_registry.register(GetProjectStatusTool())
    global_tool_registry.register(GetInvoiceStatusTool())
    global_tool_registry.register(SearchCalendarTool())
