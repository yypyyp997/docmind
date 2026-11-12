"""storage 层单测：原子入库/覆盖/级联删除/异常翻译（跑在专用测试库，不碰开发数据）。

环境要求：PostgreSQL 运行中，且已手动创建测试库：
    docker exec docmind-postgres-1 psql -U docmind -c "CREATE DATABASE docmind_test"
测试结束自动清空测试库数据（TRUNCATE），不影响开发库。
"""
import os

import psycopg
import pytest

# 测试库连接串（独立于开发库）
TEST_URL = "postgresql://docmind:docmind123@localhost:15432/docmind_test"

# 在 import storage 之前设置环境变量（storage 从环境读连接串）
os.environ["DATABASE_URL"] = TEST_URL

from storage.document_store import (
    delete_document,
    get_document_chunks,
    list_documents,
    save_document,
)
from storage.db import init_tables
from chunking.splitter import Chunk

@pytest.fixture(scope="module", autouse=True)
def _setup_test_db():
    with psycopg.connect("postgresql://docmind:docmind123@localhost:15432/docmind", autocommit=True) as conn:
        try:
            conn.execute("CREATE DATABASE docmind_test")
        except psycopg.errors.DuplicateDatabase:
            pass                          # 已存在就复用
    init_tables()
    yield
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE chunks, documents CASCADE")

def _mk(name, idx, path, body):
    return Chunk(content=f"{path}\n{body}", doc_name=name, page=1,
                 heading_path=path, chunk_index=idx)

def test_save_and_get_roundtrip():
    chunks = [
        _mk("测试文档A", 0, "健身基础", "深蹲是王者"),
        _mk("测试文档A", 0, "健身基础 > 安全要点", "膝盖对准脚尖"),
    ]
    save_document("测试文档A", chunks)
    got = get_document_chunks("测试文档A")
    assert len(got) == 2
    assert got[0]["heading_path"] == "健身基础"
    assert "深蹲是王者" in got[0]["content"]

def test_overwrite_no_duplicates():
    """同名文档重复入库 = 覆盖，不产生双份数据"""
    save_document("测试文档B", [_mk("测试文档B", 0, "章节X", "内容X")])
    save_document("测试文档B", [_mk("测试文档B", 0, "章节X", "内容X新版")])
    got = get_document_chunks("测试文档B")
    assert len(got) == 1
    assert "新版" in got[0]["content"]

def test_cascade_delete():
    """删除文档 → chunks 级联消失"""
    save_document("测试文档C", [_mk("测试文档C", 0, "章节Y", "内容Y")])
    n = delete_document("测试文档C")
    assert n == 1
    assert get_document_chunks("测试文档C") == []

def test_empty_chunks_rejected():
    """空 Chunk 列表 → StorageError（契约）"""
    from utils.exceptions import StorageError
    with pytest.raises(StorageError):
        save_document("空文档", [])

def test_missing_doc_returns_zero():
    """删除不存在的文档 → 返回 0，不抛异常"""
    assert delete_document("不存在的文档XYZ") == 0
