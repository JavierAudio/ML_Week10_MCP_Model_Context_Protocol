"""Exercise the lesson helpers and a real stdio client without a hosted model."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextContent, TextResourceContents

from support.mcp_lesson import (
    build_operations_server,
    discover_server,
    invoke_tool,
    load_operations_data,
    validate_tool_schema,
)


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_contract(self):
        server = build_operations_server()
        self.assertEqual(
            (await discover_server(server))["tools"], ["create_escalation"]
        )
        result = await invoke_tool(
            server, "create_escalation", {"ticket_id": "MCP-1002"}
        )
        self.assertTrue(result["requires_human_approval"])
        result = await invoke_tool(
            server, "create_escalation", {"ticket_id": "MCP-1001"}
        )
        self.assertFalse(result["requires_human_approval"])

    async def test_stdio_session(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "support"],
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        async with Client(stdio_client(parameters), read_timeout_seconds=10) as client:
            tools = await client.list_tools()
            self.assertEqual([tool.name for tool in tools.tools], ["create_escalation"])
            result = await client.call_tool(
                "create_escalation", {"ticket_id": "MCP-1002"}
            )
            self.assertFalse(result.is_error)
            self.assertTrue(result.structured_content["requires_human_approval"])
            invalid = await client.call_tool("create_escalation", {})
            self.assertTrue(invalid.is_error)
            wrong_type = await client.call_tool("create_escalation", {"ticket_id": 42})
            self.assertTrue(wrong_type.is_error)
            validation_error = wrong_type.content[0]
            assert isinstance(validation_error, TextContent)
            self.assertIn("Input should be a valid string", validation_error.text)
            unknown = await client.call_tool(
                "create_escalation", {"ticket_id": "MCP-9999"}
            )
            self.assertTrue(unknown.is_error)
            resources = await client.read_resource("northstar://systems")
            resource_text = resources.contents[0]
            assert isinstance(resource_text, TextResourceContents)
            self.assertEqual(
                json.loads(resource_text.text),
                load_operations_data()["systems"],
            )
            prompt = await client.get_prompt(
                "incident_update", {"ticket_id": "MCP-1002"}
            )
            prompt_text = prompt.messages[0].content
            assert isinstance(prompt_text, TextContent)
            self.assertIn("MCP-1002", prompt_text.text)

    async def test_unknown_tool_has_an_explicit_schema_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown tool"):
            await validate_tool_schema(
                build_operations_server(), "missing", {"ticket_id"}
            )

    def test_paths_do_not_depend_on_working_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertTrue(load_operations_data()["tickets"])
            finally:
                os.chdir(original)
