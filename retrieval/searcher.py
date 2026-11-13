"""检索层：语义检索入口（查询向量化 → pgvector 余弦距离 → top-k）。

metadata filter 顺路支持：doc_name 参数可按文档过滤（企业 RAG 标准能力）。
检索返回带 distance（越小越相似），调用方自己决定取多少。
"""
from dotenv import load_dotenv
load_dotenv()

import os

from storage.db import get_connection
from storage.embedder import embed_texts

def search(query: str, top_k: int = 5, doc_name: str | None = None) -> list[dict]:
    """语义检索：返回与 query 语义最近的 top_k 个 Chunk。

    :param query: 自然语言查询
    :param top_k: 返回条数
    :param doc_name: 可选，只在该文档内检索（metadata filter）
    :return: 字典列表，含 heading_path/content/page/doc_name/distance
    :raises EmbeddingError: 查询向量化失败
    """
    if not query or not query.strip():
        return []

    qvec = embed_texts([query.strip()])[0]

    # 查询向量出现两次（WHERE 前缀判断占位不需要，ORDER BY 和 SELECT 各一次）
    sql = """SELECT c.heading_path, c.content, c.page, d.doc_name,
                    c.embedding <=> %s::vector AS distance
             FROM chunks c
             JOIN documents d ON c.doc_id = d.id"""
    params: list = [str(qvec)]

    if doc_name:
        sql += " WHERE d.doc_name = %s"
        params.append(doc_name)

    sql += " ORDER BY c.embedding <=> %s::vector LIMIT %s"
    params.extend([str(qvec), top_k])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "heading_path": r[0],
            "content": r[1],
            "page": r[2],
            "doc_name": r[3],
            "distance": float(r[4]),
        }
        for r in rows
    ]

def search_with_rerank(query: str, recall_k: int = 20, top_n: int = 3,
                       doc_name: str | None = None) -> list[dict]:
    """两阶段检索：先召回 recall_k 条，再精排取 top_n。

    reranker 在函数体内 import（避免 searcher↔reranker 循环导入风险）。
    精排失败时降级返回召回结果（不因精排挂而丢掉整个检索）。
    """
    recall = search(query, top_k=recall_k, doc_name=doc_name)
    from retrieval.reranker import rerank
    try:
        return rerank(query, recall, top_n=top_n)
    except Exception:
        # 降级：精排失败返回召回结果的前 top_n（向量序），检索不因精排挂而失败
        return recall[:top_n]
