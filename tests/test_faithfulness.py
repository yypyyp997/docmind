"""faithfulness 轻量版单测：真实 LLM 判定 + Key 缺失契约。真实调用消耗少量额度。"""
import os

import pytest

from evaluation.faithfulness import judge_faithfulness

def test_faithful_answer():
    """忠实回答：断言被 context 支持 → faithful=True"""
    result = judge_faithfulness(
        question="深蹲要注意什么",
        context="深蹲时膝盖要对准脚尖方向，避免内扣，循序渐进加重。",
        answer="深蹲要注意膝盖对准脚尖，避免内扣，重量循序渐进增加。",
    )
    assert result["faithful"] is True

def test_hallucinated_answer():
    """幻觉回答：编造数据 → faithful=False"""
    result = judge_faithfulness(
        question="深蹲要注意什么",
        context="深蹲时膝盖要对准脚尖方向，避免内扣，循序渐进加重。",
        answer="深蹲每组要做30次，负重必须达到体重的2倍，否则无效。",
    )
    assert result["faithful"] is False
    assert len(result["unsupported_claims"]) >= 1

def test_missing_key_contract():
    """Key 缺失 → faithful=None（评估器故障不污染结果）"""
    old = os.environ.get("DASHSCOPE_API_KEY")
    if old:
        del os.environ["DASHSCOPE_API_KEY"]
    try:
        result = judge_faithfulness("q", "c", "a")
        assert result["faithful"] is None
    finally:
        if old:
            os.environ["DASHSCOPE_API_KEY"] = old
