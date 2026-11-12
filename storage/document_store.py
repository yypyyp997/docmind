"""文档存储：Chunk 入库 / 查询 / 删除（document_store）。

事务保证（对应 v1 防线4 的 PG 升级版）：
- save_document 把「文档登记 + 全部 Chunk 入库」放进同一个事务，
  commit 一次生效——要么全入库，要么全回滚，不存在半截文档
- 用 database-level 真事务实现 v1「工程原子」想要的效果
"""
import json
from storage.embedder import embed_texts
from storage.db import get_connection, init_tables
from utils.exceptions import StorageError

def save_document(doc_name: str, chunks: list) -> int:
    """保存文档 + 全部 Chunk + 向量化（单事务原子化）。
    流程：入库前先批量向量化（API 失败则整体失败，不产生半截数据——
    向量化在事务外完成，事务内只做纯数据库操作）。
    """
    if not chunks:
        raise StorageError("没有任何 Chunk，拒绝入库空文档")

    # ---- 向量化（事务外：API 调用慢且可能失败，不该占着事务）----
    texts = [c.content for c in chunks]
    vectors = embed_texts(texts)          # 失败抛 EmbeddingError，事务还没开始
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE doc_name = %s", (doc_name,))
            cur.execute(
                "INSERT INTO documents (doc_name, total_chunks) VALUES (%s, %s) RETURNING id",
                (doc_name, len(chunks)),
            )
            doc_id = cur.fetchone()[0]
            for c, vec in zip(chunks, vectors):
                cur.execute(
                    """INSERT INTO chunks
                       (doc_id, chunk_index, heading_path, content, page, extra, embedding)
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::vector)""",
                    (doc_id, c.chunk_index, c.heading_path,
                     c.content, c.page,
                     json.dumps(c.extra, ensure_ascii=False),
                     str(vec)),          # pgvector 接受 "[0.1,2.3,...]" 字符串字面量
                )
        conn.commit()
    return len(chunks)

def list_documents() -> list[dict]:
    """列出全部已入库文档（名称、块数、入库时间）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT doc_name, total_chunks, ingested_at FROM documents ORDER BY ingested_at DESC"
            )
            rows = cur.fetchall()
    return [
        {"doc_name": r[0], "total_chunks": r[1], "ingested_at": str(r[2])}
        for r in rows
    ]

def get_document_chunks(doc_name: str) -> list[dict]:
    """取指定文档的全部 Chunk（按章节内序号排序）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.chunk_index, c.heading_path, c.content, c.page
                   FROM chunks c JOIN documents d ON c.doc_id = d.id
                   WHERE d.doc_name = %s ORDER BY c.chunk_index""",
                (doc_name,),
            )
            rows = cur.fetchall()
    return [
        {"chunk_index": r[0], "heading_path": r[1], "content": r[2], "page": r[3]}
        for r in rows
    ]

def delete_document(doc_name: str) -> int:
    """删除文档（chunks 级联删除）。返回删除的 Chunk 数。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE doc_name = %s RETURNING total_chunks", (doc_name,))
            row = cur.fetchone()
            conn.commit()
    return row[0] if row else 0
