"""检索质量评估：纯向量 vs 向量+rerank 两阶段对照（Phase 4.5 核心产出）。

评估集结构：每个用例 = (查询, 预期命中的关键词, 预期所属章节路径片段)
三种模式对照：
- vector_only:  search() 纯向量 top3
- rerank:       search_with_rerank() 召回20 + 精排3
指标：
- hit@3: top3 中是否含预期关键词（命中即 1 分）
- 输出每种模式的命中率 + 逐例明细
前置：知识库已入库（先跑入库命令），且评估查询针对已入库内容设计。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from retrieval.searcher import search, search_with_rerank

# 评估集：10 个查询（覆盖知识库的主要主题域，每个标注预期关键词）
# 关键词判定标准：top3 结果的 content 或 heading_path 中包含该词即命中
EVAL_SET = [
    {"query": "深蹲时膝盖要注意什么", "keyword": "膝盖"},
    {"query": "硬拉怎么做才安全", "keyword": "硬拉"},
    {"query": "增肌期间怎么吃", "keyword": "蛋白质"},
    {"query": "减脂的热量缺口要多少", "keyword": "热量"},
    {"query": "卧推肩部疼怎么办", "keyword": "肩"},
    {"query": "训练后肌肉酸痛正常吗", "keyword": "酸痛"},
    {"query": "新手一周练几次", "keyword": "周"},
    {"query": "有氧和无氧怎么安排", "keyword": "有氧"},
    {"query": "蛋白质每天摄入多少", "keyword": "蛋白"},
    {"query": "训练前要热身吗", "keyword": "热身"},
    {"query": "练完第二天胳膊抬不起来", "keyword": "酸痛"},        # 字面无"酸痛"以外的重合词
    {"query": "怎么吃才能长肌肉", "keyword": "蛋白"},              # "长肌肉"→增肌→蛋白质，考同义转换
    {"query": "体重一直不掉怎么办", "keyword": "热量"},            # 减脂的字面变体
    {"query": "卧推手腕压力很大", "keyword": "腕"},                # 关联部位词（需要知识库里有腕部内容，先验证）
    {"query": "groups分组训练是什么", "keyword": "分化"},          # 术语映射考题
]

def hits(keyword: str, results: list[dict]) -> bool:
    """判定：top 结果里是否包含预期关键词"""
    for r in results:
        blob = r.get("content", "") + r.get("heading_path", "")
        if keyword in blob:
            return True
    return False

def evaluate():
    stats = {"vector_only": {"hit": 0, "total": 0}, "rerank": {"hit": 0, "total": 0}}
    print(f"{'查询':<18} {'关键词':<8} {'向量命中':<8} {'rerank命中':<10}")
    print("-" * 50)
    for case in EVAL_SET:
        q, kw = case["query"], case["keyword"]

        vec_results = search(q, top_k=3)
        vec_hit = hits(kw, vec_results)

        rr_results = search_with_rerank(q, recall_k=20, top_n=3)
        rr_hit = hits(kw, rr_results)

        stats["vector_only"]["total"] += 1
        stats["rerank"]["total"] += 1
        if vec_hit:
            stats["vector_only"]["hit"] += 1
        if rr_hit:
            stats["rerank"]["hit"] += 1

        mark_v = "HIT " if vec_hit else "MISS"
        mark_r = "HIT " if rr_hit else "MISS"
        print(f"{q:<18} {kw:<8} {mark_v:<8} {mark_r:<10}")

    print("-" * 50)
    v = stats["vector_only"]
    r = stats["rerank"]
    print(f"纯向量命中: {v['hit']}/{v['total']} = {v['hit']/v['total']:.0%}")
    print(f"rerank命中: {r['hit']}/{r['total']} = {r['hit']/r['total']:.0%}")

if __name__ == "__main__":
    evaluate()
