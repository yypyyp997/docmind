"""chat_store 单测：会话持久化、语义召回、分层装配与降级契约（真实 PG + 真实 embedding）。"""
import pytest

from storage import chat_store
from storage.embedder import EmbeddingError, embed_texts


def _embed(text):
    return embed_texts([text])[0]

def test_save_exchange_and_get_recent_roundtrip():
    sid = chat_store.new_session_id()
    assert chat_store.save_exchange(sid, "第一问", "第一答", _embed("第一问")) is True
    recent = chat_store.get_recent(sid, limit=10)
    assert len(recent) == 2
    assert recent[0]["role"] == "assistant"       # 最新在前
    assert recent[1]["content"] == "第一问"

def test_recall_finds_older_topic():
    """语义召回：排除短窗后，命中更早轮次的主题（素食 vs 深蹲）"""
    sid = chat_store.new_session_id()
    chat_store.save_exchange(sid, "素食者怎么增肌", "素食增肌注重豆类蛋白和热量盈余",
                             _embed("素食者怎么增肌"))
    chat_store.save_exchange(sid, "深蹲要注意什么", "膝盖对准脚尖", _embed("深蹲要注意什么"))
    recent = chat_store.get_recent(sid, limit=2)   # 短窗 = 第二轮的问+答
    exclude = [m["id"] for m in recent]
    recalled = chat_store.recall_messages(sid, _embed("饮食营养方面有什么建议"), exclude, top_k=2)
    assert len(recalled) >= 1
    assert all("素食" in m["content"] for m in recalled)   # 语义命中第一轮素食话题

def test_assemble_history_window_and_recall():
    """分层装配：短窗 4 条必进 + 召回补 4 条，时间升序，最新一条在末尾"""
    sid = chat_store.new_session_id()
    for i in range(6):
        chat_store.save_exchange(sid, f"问题{i}关于训练", f"回答{i}",
                                 _embed(f"问题{i}关于训练"))
    history = chat_store.assemble_history(sid, _embed("问题5关于训练"))
    assert len(history) == 8                       # 短窗 4 + 召回 4
    assert history[-1]["content"] == "回答5"        # 最新一条必在（短窗保近因）
    assert history[-2]["content"] == "问题5关于训练"

def test_session_isolation():
    """会话隔离：A 会话的记忆绝不进入 B 会话的装配结果"""
    sid_a = chat_store.new_session_id()
    sid_b = chat_store.new_session_id()
    chat_store.save_exchange(sid_a, "A会话的问题", "A会话的回答", _embed("A会话的问题"))
    chat_store.save_exchange(sid_b, "B会话的问题", "B会话的回答", _embed("B会话的问题"))
    assert all("A会话" not in m["content"]
               for m in chat_store.assemble_history(sid_b, _embed("B会话的问题")))
    assert all("B会话" not in m["content"]
               for m in chat_store.assemble_history(sid_a, _embed("A会话的问题")))

def test_persistence_failure_returns_false(monkeypatch):
    """持久化失败 → False，不抛异常（不炸问答主链路）"""
    from utils.exceptions import StorageError

    def broken():
        raise StorageError("db down")

    monkeypatch.setattr(chat_store, "get_connection", broken)
    assert chat_store.save_exchange("sid", "问", "答", None) is False
    assert chat_store.get_recent("sid", limit=4) == []

def test_answer_embed_failure_still_persists(monkeypatch):
    """回答向量化失败 → 行照存（embedding 为 NULL，不可召回），内容不丢"""
    sid = chat_store.new_session_id()

    def broken(texts):
        raise EmbeddingError("api down")

    monkeypatch.setattr(chat_store, "embed_texts", broken)
    assert chat_store.save_exchange(sid, "问", "答", None) is True
    assert len(chat_store.get_recent(sid, limit=2)) == 2
