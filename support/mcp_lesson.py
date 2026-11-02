"""Deterministic MCP lesson helpers built on the official Python SDK."""

import json
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


class EscalationResult(BaseModel):
    """Structured result returned by the MCP tool."""

    ticket_id: str
    policy_id: str
    external_system: str
    next_action: str
    requires_human_approval: bool


def _read_json(relative_path: str) -> list[dict[str, Any]]:
    return json.loads((DATA_ROOT / relative_path).read_text(encoding="utf-8"))


def load_operations_data() -> dict[str, list[dict[str, Any]]]:
    """Load local fixtures that stand in for external systems."""

    return {
        "tickets": _read_json("operations/tickets.json"),
        "policies": _read_json("operations/policies.json"),
        "systems": _read_json("operations/systems.json"),
    }


def _find_row(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    for row in rows:
        if row[key] == value:
            return row
    raise ValueError(f"No row found for {key}={value}")


def build_operations_server() -> MCPServer:
    """Register one tool, one resource, and one prompt on an MCP server."""

    data = load_operations_data()
    server = MCPServer(
        name="northstar-ops",
        title="Northstar Operations MCP",
        description="A local teaching server for MCP tools, resources, and prompts.",
        version="0.1.0",
    )

    @server.tool(description="Create an escalation plan for a support ticket.")
    def create_escalation(ticket_id: str) -> EscalationResult:
        try:
            ticket = _find_row(data["tickets"], "ticket_id", ticket_id)
        except ValueError as error:
            raise ToolError(str(error)) from error
        policy = _find_row(data["policies"], "topic", str(ticket["topic"]))
        return EscalationResult(
            ticket_id=str(ticket["ticket_id"]),
            policy_id=str(policy["policy_id"]),
            external_system=str(ticket["external_system"]),
            next_action=(
                f"Use {ticket['external_system']} and follow {policy['text']}"
            ),
            requires_human_approval=ticket["priority"] == "critical",
        )

    @server.resource(
        "northstar://systems",
        name="northstar_systems",
        description="Approved external systems and the scopes each system needs.",
        mime_type="application/json",
    )
    def northstar_systems() -> str:
        return json.dumps(data["systems"], indent=2)

    @server.prompt(description="Reusable incident-update prompt.")
    def incident_update(ticket_id: str) -> str:
        return (
            "Draft an incident update for the customer. "
            f"Use ticket {ticket_id}, cite policy evidence, and request human "
            "approval before promising remediation timing."
        )

    return server


async def discover_server(server: MCPServer) -> dict[str, list[str]]:
    """Return discoverable MCP primitive names."""

    tools = await server.list_tools()
    resources = await server.list_resources()
    prompts = await server.list_prompts()
    return {
        "tools": [tool.name for tool in tools],
        "resources": [str(resource.uri) for resource in resources],
        "prompts": [prompt.name for prompt in prompts],
    }


async def invoke_tool(
    server: MCPServer, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Call a server tool and return structured content."""

    result = await server.call_tool(name, arguments)
    if getattr(result, "is_error", False):
        raise ValueError(f"Tool call failed: {getattr(result, 'content', '')}")
    structured_content = getattr(result, "structured_content", None)
    if structured_content is None:
        raise ValueError(f"Tool call did not return structured content: {result}")
    return dict(structured_content)


async def validate_tool_schema(
    server: MCPServer, tool_name: str, required_fields: set[str]
) -> dict[str, Any]:
    """Check whether a tool schema exposes required input fields."""

    tools = await server.list_tools()
    tool = next((tool for tool in tools if tool.name == tool_name), None)
    if tool is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    required = set(tool.input_schema.get("required", []))
    return {
        "tool": tool.name,
        "required": sorted(required),
        "has_required_fields": required_fields.issubset(required),
    }
