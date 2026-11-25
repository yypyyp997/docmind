"""Agent 层测试：图的编排正确性（mock LLM，不烧钱）。

测试策略：
- mock retrieval.searcher.search_with_rerank（检索层已被 searcher 测试覆盖）
- mock dashscope.Generation.call（生成层不在本层测真实调用）
- 只测 LangGraph 的编排契约：节点串联、状态传递、引用解析、降级路径
"""
import re
from unittest.mock import patch, MagicMock

import pytest

### --- 夹具：构造可控的检索结果与 LLM 响应 ---

CTX = [
    {"heading_path": "安全要点", "content": "深蹲时膝盖与脚尖方向一致，避免内扣。", "page": 12,
     "doc_name": "fastapi_index.md", "distance": 0.18},
    {"heading_path": "训练频率", "content": "同一肌群训练间隔 48 小时以上。", "page": 15,
     "doc_name": "fastapi_index.md", "distance": 0.22},
]

def _mock_llm(text: str):
    """构造 dashscope 响应替身。"""
    resp = MagicMock()
    resp.status_code = 200
    resp.output.text = text
    return resp

### --- 用例 ---

class TestGraphBuild:
    def test_build_graph_compiles(self):
        """图能构建并编译（节点/边契约正确）。"""
        from agent.graph import build_graph
        graph = build_graph()
        assert graph is not None

class TestAskFlow:
    @patch("dashscope.Generation.call")
    @patch("retrieval.searcher.search_with_rerank")
    def test_ask_full_flow(self, mock_search, mock_llm_call):
        """完整链路：检索 2 条 → LLM 带引用回答 → sources 解析正确。"""
        mock_search.return_value = CTX
        mock_llm_call.return_value = _mock_llm(
            "深蹲时膝盖应与脚尖方向一致 [1]。同一肌群训练间隔 48 小时以上 [2]。\n来源: [1] [2]"
        )
        from agent.graph import ask
        result = ask("深蹲要注意什么？")
        assert result["answer"].startswith("深蹲")
        assert result["llm_error"] == ""
        assert [s["ref"] for s in result["sources"]] == [1, 2]
        assert result["sources"][0]["doc_name"] == "fastapi_index.md"
        assert result["sources"][0]["page"] == 12

    @patch("dashscope.Generation.call")
    @patch("retrieval.searcher.search_with_rerank")
    def test_ask_empty_retrieval_skips_llm(self, mock_search, mock_llm_call):
        """检索 0 条 → 不调 LLM，直接"知识库中没有相关内容。"（省钱+零幻觉）。"""
        mock_search.return_value = []
        from agent.graph import ask
        result = ask("完全无关的问题")
        assert result["answer"] == "知识库中没有相关内容。"
        assert result["sources"] == []
        mock_llm_call.assert_not_called()

    @patch("dashscope.Generation.call")
    @patch("retrieval.searcher.search_with_rerank")
    def test_ask_llm_failure_sets_error(self, mock_search, mock_llm_call):
        """LLM 失败 → llm_error 非空，answer 为空（调用方决定降级）。"""
        mock_search.return_value = CTX
        mock_llm_call.return_value = MagicMock(status_code=500, code="InternalError", message="boom")
        from agent.graph import ask
        result = ask("深蹲要注意什么？")
        assert result["answer"] == ""
        assert "InternalError" in result["llm_error"]
        assert result["sources"] == []

class TestMultiTurn:
    @patch("dashscope.Generation.call")
    @patch("retrieval.searcher.search_with_rerank")
    def test_ask_history_enters_prompt(self, mock_search, mock_llm_call):
        """多轮：装配好的历史进入提示词（模型能看见上文）"""
        mock_search.return_value = CTX
        mock_llm_call.return_value = _mock_llm("好的 [1]。\n来源: [1]")
        history = [
            {"role": "user", "content": "深蹲要注意什么？"},
            {"role": "assistant", "content": "膝盖对准脚尖，循序渐进 [1]。"},
        ]
        from agent.graph import ask
        ask("第二点展开说说", history=history)
        prompt = mock_llm_call.call_args.kwargs["prompt"]
        assert "深蹲要注意什么？" in prompt        # 上文的问题在
        assert "循序渐进" in prompt                # 上文的回答在

    @patch("dashscope.Generation.call")
    @patch("retrieval.searcher.search_with_rerank")
    def test_ask_no_history_prompt_has_placeholder(self, mock_search, mock_llm_call):
        """单轮：无历史 → 历史段为占位文本（向后兼容契约）"""
        mock_search.return_value = CTX
        mock_llm_call.return_value = _mock_llm("好的 [1]。\n来源: [1]")
        from agent.graph import ask
        ask("深蹲要注意什么？")
        assert "（无，本轮为会话首轮）" in mock_llm_call.call_args.kwargs["prompt"]
