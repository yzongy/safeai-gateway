from __future__ import annotations

import sys
from typing import List, Optional

from .codex import mcp_doctor_payload, mcp_prepare_payload, mcp_restore_payload, mcp_scan_payload


def run_mcp_server(default_policy: str = "strict-ai") -> int:
    if sys.version_info < (3, 10):
        print("safeai mcp requires Python 3.10+. Run `safeai codex install --python auto`.", file=sys.stderr)
        return 2
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("safeai mcp requires the MCP SDK. Install with `python -m pip install 'safeai-gateway[codex]'`.", file=sys.stderr)
        return 2

    server = FastMCP("safeai")

    @server.tool()
    def safeai_doctor(root: Optional[str] = None) -> dict:
        return mcp_doctor_payload(root=root)

    @server.tool()
    def safeai_scan(paths: List[str], policy: str = default_policy, root: Optional[str] = None) -> dict:
        return mcp_scan_payload(paths, policy=policy, root=root)

    @server.tool()
    def safeai_prepare(
        paths: List[str],
        policy: str = default_policy,
        out: Optional[str] = None,
        root: Optional[str] = None,
    ) -> dict:
        return mcp_prepare_payload(paths, policy=policy, out=out, root=root)

    @server.tool()
    def safeai_restore(sanitized_file: str, run_id: str, out: Optional[str] = None, root: Optional[str] = None) -> dict:
        return mcp_restore_payload(sanitized_file, run_id=run_id, out=out, root=root)

    server.run(transport="stdio")
    return 0
