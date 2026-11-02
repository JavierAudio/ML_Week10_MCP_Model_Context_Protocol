"""Run the lesson server as a local MCP subprocess over stdio."""

from support.mcp_lesson import build_operations_server

if __name__ == "__main__":
    build_operations_server().run(transport="stdio")
