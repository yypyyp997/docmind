"""API 层测试：TestClient 全端点覆盖（认证/业务/异常路径）。

依赖：storage 测试隔离已就位（docmind_test 库）+ config.settings（API_KEY 开发模式为空 = 跳过认证）。
注意：API_KEY 非空时需要带 X-API-Key 头——测试通过 monkeypatch 控制 API_KEY 状态。
"""
import os

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

# ---------- 无认证端点 ----------

def test_health():
    """存活探针：无认证 200"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

# ---------- 认证依赖的两种模式 ----------

def test_search_dev_mode_no_auth_required():
    """开发模式（API_KEY 空）：search 无需认证头"""
    resp = client.post("/api/search", json={"query": "深蹲", "top_k": 3})
    assert resp.status_code == 200          # 开发模式放行（真实检索消耗额度）

def test_search_auth_mode_missing_key(monkeypatch):
    """认证模式（API_KEY 非空）：无认证头 → 401"""
    monkeypatch.setattr("api.main.API_KEY", "secret-key-123")
    resp = client.post("/api/search", json={"query": "深蹲"})
    assert resp.status_code == 401

def test_search_auth_mode_wrong_key(monkeypatch):
    """认证模式：错误 Key → 401"""
    monkeypatch.setattr("api.main.API_KEY", "secret-key-123")
    resp = client.post("/api/search", json={"query": "深蹲"},
                       headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401

def test_search_auth_mode_correct_key(monkeypatch):
    """认证模式：正确 Key → 放行"""
    monkeypatch.setattr("api.main.API_KEY", "secret-key-123")
    resp = client.post("/api/search", json={"query": "深蹲"},
                       headers={"X-API-Key": "secret-key-123"})
    assert resp.status_code == 200

# ---------- 校验与异常路径 ----------

def test_search_validation_empty_query():
    """空 query → 422（pydantic 校验）"""
    resp = client.post("/api/search", json={"query": "", "top_k": 3})
    assert resp.status_code == 422

def test_ingest_file_not_found():
    """入库文件不存在 → 404"""
    resp = client.post("/api/ingest", json={"path": r"D:\不存在\fake.md"})
    assert resp.status_code == 404

def test_delete_nonexistent_document():
    """删除不存在的文档 → 404"""
    resp = client.delete("/api/documents/不存在的文档XYZ")
    assert resp.status_code == 404

def test_documents_list_returns_list():
    """文档清单 → 返回列表"""
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------- 问答端点（agent 层接入） ----------

from unittest.mock import patch, MagicMock


class TestAskEndpoint:
    @patch("agent.graph._generate")
    @patch("retrieval.searcher.search_with_rerank")
    def test_ask_ok(self, mock_search, mock_gen):
        """问答成功：answer + sources 结构完整（LLM 与检索全 mock，零成本）。"""
        mock_search.return_value = [
            {"heading_path": "依赖注入", "content": "FastAPI 依赖注入系统", "page": None,
             "doc_name": "features.md", "distance": 0.2}
        ]
        mock_gen.return_value = {"context_text": "[1] ...", "answer": "依赖注入是 [1]。",
                                 "llm_error": ""}
        resp = client.post("/api/ask", json={"question": "什么是依赖注入？"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["answer"] == "依赖注入是 [1]。"
        assert body["sources"][0]["doc_name"] == "features.md"
        assert body["contexts"][0]["heading_path"] == "依赖注入"

    @patch("agent.graph._generate")
    @patch("retrieval.searcher.search_with_rerank")
    def test_ask_llm_failure_degrades(self, mock_search, mock_gen):
        """LLM 失败 → status=degraded + 返回检索切片（降级契约）。"""
        mock_search.return_value = [
            {"heading_path": "中间件", "content": "middleware 内容", "page": None,
             "doc_name": "features.md", "distance": 0.3}
        ]
        mock_gen.return_value = {"context_text": "[1] ...", "answer": "",
                                 "llm_error": "API InternalError: boom"}
        resp = client.post("/api/ask", json={"question": "中间件怎么写？"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert "InternalError" in body["detail"]
        assert body["results"][0]["content"] == "middleware 内容"

    def test_ask_validation_empty_question(self):
        """空问题 → 422（pydantic 校验）"""
        resp = client.post("/api/ask", json={"question": ""})
        assert resp.status_code == 422
