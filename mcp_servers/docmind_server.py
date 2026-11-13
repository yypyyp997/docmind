"""DocMind MCP Server：把文档知识库的三个能力暴露为 MCP 工具。

架构说明：
- 本文件是独立进程（不 import docmind 主项目代码，只依赖 storage 层），
  通过 stdio 与 MCP 客户端通信
- 三个工具：
  1. search_docs     语义检索（embedder + pgvector）
  2. list_documents  文档清单（元数据）
  3. get_stats       知识库统计（块数/文档数）
- 启动：python mcp_servers/docmind_server.py（stdio 模式）
- 客户端配置（Claude Desktop / 其他 MCP 客户端）：
  {"command": "python", "args": ["绝对路径/mcp_servers/docmind_server.py"]}
"""
import sys
from pathlib import Path

# 项目根加入 sys.path（storage 层的 import 依赖它）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("docmind")

@mcp.tool()
def search_docs(query: str, top_k: int = 3, doc_name: str = "") -> list[dict]:
    """语义检索文档知识库。返回最相关的 chunk 列表（含章节路径和内容）。

    Args:
        query: 自然语言查询，如"深蹲安全注意事项"
        top_k: 返回条数，默认 3
        doc_name: 可选，限定在某个文档内检索（留空检索全部）
    """
    from retrieval.searcher import search
    return search(query, top_k=top_k, doc_name=doc_name or None)

@mcp.tool()
def list_documents() -> list[dict]:
    """列出知识库中全部已入库文档（名称、块数、入库时间）。"""
    from storage.document_store import list_documents
    return list_documents()

@mcp.tool()
def get_stats() -> dict:
    """知识库统计：文档总数、Chunk 总数。"""
    from storage.db import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), COALESCE(SUM(total_chunks),0) FROM documents")
            docs, chunk_total = cur.fetchone()
    return {"documents": docs, "chunks": chunk_total}

if __name__ == "__main__":
    mcp.run()          # 默认 stdio 传输
