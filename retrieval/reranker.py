"""rerank 精排：gte-rerank 对召回结果重排序（Phase 4 两阶段检索的第二阶段）。

两阶段检索：
- 第一阶段召回（searcher.search）：向量快筛，从库里捞回语义可能相关的 top20
- 第二阶段精排（本模块）：交叉编码器逐对细算 query 与每条的相关度，取 top3

为什么分两阶段：召回快但粗（双编码器分别编码，精度有限），
精排准但慢（逐对计算，条数多了耗时线性涨）——20→3 是精度/成本平衡点。
"""
import os

import dashscope

EMBED_MODEL_PLACEHOLDER = None   # 本模块不涉及 embedding
class RerankError(Exception):
    """精排失败的统一异常：Key 缺失/接口失败/响应结构异常都用它。"""

def rerank(query: str, docs: list[dict], top_n: int = 3) -> list[dict]:
    """精排召回结果，返回按相关度降序的 top_n（原 dict + rerank_score）。

    :param query: 用户查询
    :param docs: searcher 产出的结果列表（必须含 "content" 键）
    :param top_n: 返回条数（不超过 len(docs)）
    :return: 按相关度降序排列的字典列表，每个在原字段外新增 "rerank_score"
    :raises RerankError: API Key 缺失 / 请求失败 / 响应结构异常
    """
    if not docs:
        return []
    if len(docs) == 1:
        # 单条无需精排：直通返回，省一次 API 调用
        out = dict(docs[0])
        out["rerank_score"] = None
        return [out]

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RerankError("环境变量 DASHSCOPE_API_KEY 未设置，无法精排")

    resp = dashscope.TextReRank.call(
        model="gte-rerank-v2",
        query=query,
        documents=[d["content"] for d in docs],
        top_n=min(top_n, len(docs)),
        return_documents=False,
        api_key=api_key
    )
    if resp.status_code != 200:
        raise RerankError(
            f"精排失败: code={resp.code} message={resp.message}"
        )

    results = resp.output["results"]       # [{"index": 2, "relevance_score": 0.95}, ...]
    ranked: list[dict] = []
    for item in results:
        idx = item["index"]
        doc = dict(docs[idx])              # 浅拷贝：不动原 dict
        doc["rerank_score"] = item["relevance_score"]
        ranked.append(doc)
    return ranked
