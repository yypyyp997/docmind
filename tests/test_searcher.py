"""searcher 单测：依赖真实 PG + 真实 embedding（消耗少量额度）。

前置：先跑 scripts/smoke_vector.py 造出「向量冒烟.md」的 3 个 Chunk。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from retrieval import search
import pytest

from chunking.splitter import Chunk
from storage.db import init_tables
from storage.document_store import save_document,delete_document

@pytest.fixture(scope="module", autouse=True)
def _seed_test_data():
    """模块级：建表 + 灌测试数据 + 结束后清理（自包含，不依赖外部数据）"""
    init_tables()
    chunks = [
        Chunk(content="健身基础\n深蹲是力量训练之王", doc_name="向量冒烟.md", page=1,
              heading_path="健身基础", chunk_index=0),
        Chunk(content="健身基础 > 安全要点\n膝盖对准脚尖，避免内扣", doc_name="向量冒烟.md", page=1,
              heading_path="健身基础 > 安全要点", chunk_index=0),
        Chunk(content="营养饮食\n增肌需要热量盈余和充足蛋白质", doc_name="向量冒烟.md", page=2,
              heading_path="营养饮食", chunk_index=0),
    ]
    save_document("向量冒烟.md", chunks)
    yield
    delete_document("向量冒烟.md")     # 收尾清理（测试库自净）


def test_search_finds_semantic_match():
    """语义检索：查"深蹲安全"应命中安全要点域"""
    results = search("深蹲安全注意事项", top_k=3)
    assert len(results) >= 1
    assert any("安全要点" in r["heading_path"] for r in results)
    # distance 越小越相似：结果按距离升序
    dists = [r["distance"] for r in results]
    assert dists == sorted(dists)

def test_metadata_filter_by_doc():
    """metadata filter：限定文档名后只返回该文档的块"""
    results = search("深蹲", top_k=5, doc_name="向量冒烟.md")
    assert all(r["doc_name"] == "向量冒烟.md" for r in results)

def test_empty_query_returns_empty():
    """空查询 → 空结果（不发请求）"""
    assert search("") == []
    assert search("   ") == []
