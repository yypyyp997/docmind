"""MCP server 单测：工具函数级验证（不经 stdio，直接调注册的函数）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import pytest

from storage.document_store import save_document
from chunking.splitter import Chunk
from storage.db import init_tables

@pytest.fixture(scope="module", autouse=True)
def _seed(tmp_path_factory):
    """模块级：建表+灌一个测试文档（测完清理）"""
    init_tables()
    chunks = [
        Chunk(content="健身基础 > 安全要点\n膝盖对准脚尖", doc_name="mcp测试.md", page=1,
              heading_path="健身基础 > 安全要点", chunk_index=0),
    ]
    save_document("mcp测试.md", chunks)
    yield
    from storage.document_store import delete_document
    delete_document("mcp测试.md")

def test_search_tool():
    """search_docs 工具：语义检索返回结果"""
    # 直接 import server 模块里注册的函数（FastMCP 装饰器保留原函数）
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "docmind_server", r"D:\docmind\mcp_servers\docmind_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    results = mod.search_docs("深蹲安全", top_k=3)
    assert len(results) >= 1
    assert "安全要点" in results[0].get("heading_path", "")

def test_stats_tool():
    """get_stats 工具：统计数字与实际一致"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "docmind_server", r"D:\docmind\mcp_servers\docmind_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stats = mod.get_stats()
    assert stats["documents"] >= 1
    assert stats["chunks"] >= 1

def test_list_documents_tool():
    """list_documents 工具：返回列表且含 mcp测试文档"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "docmind_server", r"D:\docmind\mcp_servers\docmind_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    docs = mod.list_documents()
    names = [d.get("doc_name") for d in docs]
    assert "mcp测试.md" in names
