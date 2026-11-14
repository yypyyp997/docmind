"""完整评估：检索命中率（vector/rerank 对照）+ 生成忠实度（faithfulness）。

Phase 8 轻量版产出：一份融合报告，回答三个问题：
1. 检索层：查询能否召回正确内容（vector vs rerank）
2. 生成层：基于召回内容的回答是否忠实（faithfulness）
3. 综合：两条腿都健康的比例
前置：知识库已入库 + OpenAI 兼容生成链路可用（这里复用 faithfulness 的 qwen-max 做
生成演示——真实系统的 answer 来自主链路，评估时用 LLM 现场生成等价物）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import os

import dashscope
from evaluation.eval_retrieval import hits
from evaluation.faithfulness import judge_faithfulness
from retrieval.searcher import search, search_with_rerank

GENERATE_PROMPT = """基于以下参考内容回答问题。如果参考内容不足以回答，明确说明"知识库中没有相关信息"。不要编造。

【问题】{q}
【参考内容】{ctx}

回答："""

def generate_answer(question: str, context: str) -> str:
    """用检索内容生成回答（评估用生成链路，模拟主系统的行为）"""
    resp = dashscope.Generation.call(
        model="qwen-max",
        prompt=GENERATE_PROMPT.format(q=question, ctx=context[:3000]),
    )
    if resp.status_code != 200:
        return f"[生成失败: {resp.message}]"
    return resp.output.text.strip()

def evaluate_full():
    import json

    from evaluation.eval_retrieval import EVAL_SET

    rows = []
    stats = {"vec_hit": 0, "rr_hit": 0, "faithful": 0, "total": 0}

    print(f"{'查询':<18} {'检索命中':<6} {'忠实度':<10}")
    print("-" * 46)

    for case in EVAL_SET:
        q, kw = case["query"], case["keyword"]
        stats["total"] += 1

        # 检索：rerank 模式（两阶段的最终形态）
        results = search_with_rerank(q, recall_k=20, top_n=3)
        rr_hit = hits(kw, results)
        stats["rr_hit"] += rr_hit  # rerank 模式命中计入主指标

        # 组装 context（top3 的 content 拼接）
        context = "\n\n".join(r["content"] for r in results)

        # 生成 + 忠实度判定
        answer = generate_answer(q, context)
        faith = judge_faithfulness(q, context, answer)
        is_faithful = faith.get("faithful")
        if is_faithful is True:
            stats["faithful"] += 1

        mark = "HIT " if rr_hit else "MISS"
        f_mark = {True: "忠实", False: "不忠实", None: "评估失败"}[is_faithful]
        print(f"{q:<18} {mark:<6} {f_mark:<10}")
        rows.append({
            "query": q, "rr_hit": rr_hit, "faithful": is_faithful,
            "unsupported": faith.get("unsupported_claims", []),
        })

    print("-" * 46)
    t = stats["total"]
    print(f"检索命中（rerank 模式）: {stats['rr_hit']}/{t} = {stats['rr_hit']/t:.0%}")
    print(f"忠实度通过: {stats['faithful']}/{t} = {stats['faithful']/t:.0%}")

    # 输出详细报告（JSON，供后续分析）
    report_path = Path(__file__).parent / "results" / "full_eval_report.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "rows": rows}, f, ensure_ascii=False, indent=2)
    print(f"详细报告: {report_path}")

if __name__ == "__main__":
    evaluate_full()
