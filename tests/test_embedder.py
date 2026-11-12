"""embedder 单测：真实调用/空列表/Key 缺失。真实调用会消耗少量额度。"""
import pytest

from storage.embedder import EmbeddingError, embed_texts

def test_real_embedding_one_text():
    """真实调用：单文本 → 1024 维向量（消耗少量额度）"""
    vectors = embed_texts(["深蹲训练要点"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 1024
    assert all(isinstance(x, float) for x in vectors[0])

def test_empty_list_returns_empty():
    """空列表 → 空返回（不发 API 请求）"""
    assert embed_texts([]) == []

def test_missing_api_key_raises(monkeypatch):
    """Key 缺失 → EmbeddingError"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(EmbeddingError):
        embed_texts(["任意文本"])
