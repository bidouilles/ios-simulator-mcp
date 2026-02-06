from __future__ import annotations

import asyncio

from ios_simulator_mcp import server as server_module


def test_server_compat_export_points_to_mcp() -> None:
    """The legacy `server` export should continue to reference the FastMCP instance."""
    assert server_module.server is server_module.mcp


def test_fastmcp_tools_registered() -> None:
    tools = asyncio.run(server_module.mcp.get_tools())
    if isinstance(tools, dict):
        tool_names = set(tools.keys())
    else:
        tool_names = {tool.name for tool in tools}

    expected_tools = {
        "list_devices",
        "start_bridge",
        "get_screenshot",
        "tap",
        "discover_dtd_uris",
    }
    assert expected_tools.issubset(tool_names)

    start_bridge_tool = asyncio.run(server_module.mcp.get_tool("start_bridge"))
    assert start_bridge_tool.name == "start_bridge"
    assert start_bridge_tool.description


def test_fastmcp_resources_registered() -> None:
    resources = asyncio.run(server_module.mcp.get_resources())
    if isinstance(resources, dict):
        resource_keys = set(resources.keys())
    else:
        resource_keys = {resource.key for resource in resources}

    assert "ios-sim://api-reference" in resource_keys
    assert "ios-sim://automation-guide" in resource_keys
