"""reranker 单测：真实调用/空列表/单条直通。真实调用消耗少量额度。"""
import pytest

from retrieval.reranker import RerankError, rerank

def test_real_rerank_semantic_order():
    """真实调用：语义排序——安全要点 应排在 营养饮食 前面"""
    docs = [
        {"content": "营养饮食\n增肌需要热量盈余和充足蛋白质", "page": 1},
        {"content": "健身基础 > 安全要点\n深蹲时膝盖对准脚尖，避免内扣", "page": 1},
        {"content": "恢复休息\n睡眠是最便宜的恢复手段", "page": 2},
    ]
    ranked = rerank("深蹲安全注意事项", docs, top_n=3)
    assert len(ranked) == 3
    assert "安全要点" in ranked[0]["content"]       # 最相关的排第一
    assert ranked[0]["rerank_score"] >= ranked[1]["rerank_score"]   # 分数降序

def test_empty_docs_returns_empty():
    """空列表 → 空返回（不发请求）"""
    assert rerank("任意查询", [], top_n=3) == []

def test_single_doc_pass_through():
    """单条直通：不打分，原样返回加 None 占位"""
    docs = [{"content": "唯一的一条", "page": 1}]
    ranked = rerank("任意", docs, top_n=3)
    assert len(ranked) == 1
    assert ranked[0]["rerank_score"] is None
    assert ranked[0]["content"] == "唯一的一条"
