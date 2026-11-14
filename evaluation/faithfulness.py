"""忠实度评估（轻量版）：LLM-as-judge 判定回答是否被检索内容支持。

这是 RAGAS faithfulness 指标的简化实现（整体判定而非逐断言拆解）。
配合 9.22 的反幻觉行为契约使用：契约保证"格式上的不编造"，
faithfulness 量化"语义上的支持度"。
"""
import json
import os

import dashscope

FAITHFULNESS_PROMPT = """你是评估专家。判断【回答】是否被【参考内容】支持。

判定规则：
1. 回答中的每个事实性断言，必须在参考内容中有依据
2. 回答超出参考内容的编造内容（数据、事实、结论）= 不忠实
3. 回答中的通用建议（如"循序渐进训练"）不算编造
4. 只输出 JSON，格式：{{"faithful": true/false, "unsupported_claims": ["编造点1", ...]}}

【问题】{question}
【参考内容】{context}
【回答】{answer}

只输出 JSON："""

def judge_faithfulness(question: str, context: str, answer: str) -> dict:
    """LLM-as-judge 忠实度判定。返回 {"faithful": bool, "unsupported_claims": [...]}。

    异常契约：LLM 调用失败或 JSON 解析失败 → 返回 {"faithful": None, "error": "..."}
    （None 表示"评估失败"，与 False（确认不忠实）区分——评估器自身故障不能污染评估结果）
    """
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return {"faithful": None, "error": "DASHSCOPE_API_KEY 未设置"}

    prompt = FAITHFULNESS_PROMPT.format(
        question=question, context=context[:3000], answer=answer[:2000]
    )
    try:
        resp = dashscope.Generation.call(
            model="qwen-max",
            prompt=prompt,
            api_key=api_key,
        )
        if resp.status_code != 200:
            return {"faithful": None, "error": f"API {resp.code}: {resp.message}"}
        text = resp.output.text.strip()
        # 提取 JSON（LLM 可能在前后加说明文字，找第一个 { 到最后一个 }）
        start, end = text.find("{"), text.rfind("}") + 1
        parsed = json.loads(text[start:end])
        return {
            "faithful": bool(parsed.get("faithful")),
            "unsupported_claims": parsed.get("unsupported_claims", []),
        }
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return {"faithful": None, "error": f"响应解析失败: {e}"}
    except Exception as e:
        return {"faithful": None, "error": str(e)[:200]}
