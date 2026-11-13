"""embedding 向量化：调 DashScope text-embedding-v4，文本 → 1024 维向量。

批量规则：DashScope 单次请求最多 25 条文本，超过自动分批。
失败契约：API 异常/状态码非 200/维度不符 → EmbeddingError（带原因）。
"""
import os
import dashscope

EMBED_DIM=1024
MODEL="text-embedding-v4"
BATCH_LIMIT=10
API_KEY=os.getenv("DASHSCOPE_API_KEY")

class EmbeddingError(Exception):
    """向量化失败的统一异常：Key 缺失/接口失败/维度不符都用它。"""

def embed_texts(texts:list[str])->list[list[float]]:
    """批量向量化文本。
    :param texts: 文本列表（每条建议 ≤ 1000 字，超长会被 API 截断）
    :return: 与 texts 等长的向量列表，每个向量是 1024 个浮点数
    :raises EmbeddingError: API Key 缺失 / 请求失败 / 返回维度不符
    """
    if not texts:
        return []
    api_key=os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise EmbeddingError("环境变量 DASHSCOPE_API_KEY 未设置，无法向量化")
    batches=[texts[i:i+BATCH_LIMIT] for i in range(0,len(texts),BATCH_LIMIT)]
    vectors:list[list[float]]=[]
    for batch_no,batch in enumerate(batches,start=1):
        resp=dashscope.TextEmbedding.call(
            model=MODEL,
            input=batch,
            dimension=EMBED_DIM,
            api_key=api_key
        )
        if resp.status_code!=200:
            raise EmbeddingError(
                f"向量化失败(批次{batch_no}/{len(batches)}):"
                f"code={resp.code} message={resp.message}"
            )
        items=sorted(resp.output["embeddings"],key=lambda e:e["text_index"])
        batch_vectors=[item["embedding"] for item in items]
        for v in batch_vectors:
            if len(v)!=EMBED_DIM:
                raise EmbeddingError(
                    f"返回的向量维度异常:期望{EMBED_DIM}维,实际{len(v)}维"
                )
        vectors.extend(batch_vectors)
    if len(vectors)!=len(texts):
        raise EmbeddingError(
            f"向量数量与输入不一致: 传入{len(texts)}条，返回{len(vectors)}条"
        )
    return vectors

