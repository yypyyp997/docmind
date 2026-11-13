# -*- coding: utf-8 -*-
"""MCP 客户端演示：以外部客户端身份连接 DocMind server，全协议调用三工具。

流程 = Claude Desktop 等客户端接入的真实机制：
进程拉起 server -> initialize 握手 -> list_tools 发现 -> call_tool 调用
"""
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = r"D:\docmind\mcp_servers\docmind_server.py"
VENV_PY = r"D:\docmind\.venv\Scripts\python.exe"


async def main():
    params = StdioServerParameters(command=VENV_PY, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[1] MCP 握手 + initialize OK")

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"[2] 发现工具 {len(names)} 个: {names}")

            result = await session.call_tool(
                "search_docs",
                {"query": "深蹲安全注意事项", "top_k": 2},
            )
            print("[3] search_docs(深蹲安全注意事项):")
            for c in result.content:
                text = getattr(c, "text", str(c))
                print("   ", text[:300])

            stats = await session.call_tool("get_stats", {})
            print("[4] get_stats:")
            for c in stats.content:
                text = getattr(c, "text", str(c))
                print("   ", text[:200])


if __name__ == "__main__":
    asyncio.run(main())
