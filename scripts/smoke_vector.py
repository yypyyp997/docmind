"""向量入库+检索全链路冒烟（Phase 3 收官验证）。用完可删。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from chunking.splitter import Chunk
from storage.db import init_tables
from storage.document_store import save_document
from storage.embedder import embed_texts

init_tables()

# 1. 造三个语义不同的 Chunk
chunks = [
    Chunk(content="健身基础\n深蹲是力量训练之王", doc_name="向量冒烟.md", page=1,
          heading_path="健身基础", chunk_index=0),
    Chunk(content="健身基础 > 安全要点\n膝盖对准脚尖，避免内扣", doc_name="向量冒烟.md", page=1,
          heading_path="健身基础 > 安全要点", chunk_index=0),
    Chunk(content="营养饮食\n增肌需要热量盈余和充足蛋白质", doc_name="向量冒烟.md", page=2,
          heading_path="营养饮食", chunk_index=0),
]
save_document("向量冒烟.md", chunks)
print("[1] 带向量入库 OK（3 个 Chunk）")

# 2. 向量化一个查询
q = embed_texts(["深蹲安全注意事项"])
qvec = q[0]

# 3. 向量检索：pgvector 的 cosine 距离运算符 <=>，取最近 2 条
import psycopg, os
url = os.getenv("DATABASE_URL")
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.heading_path,
                      c.content,
                      c.embedding <=> %s::vector AS distance
               FROM chunks c
                   JOIN documents d
               ON c.doc_id = d.id
               WHERE d.doc_name = '向量冒烟.md'
               ORDER BY c.embedding <=> %s::vector
                   LIMIT 2""",
            (str(qvec), str(qvec)),
        )

        rows = cur.fetchall()

print("[2] 向量检索 top2:")
for r in rows:
    print(f"    距离={r[2]:.4f} | {r[0]} | {r[1][:30]}")

# 4. 断言：安全要点的距离 < 营养饮食的距离（语义相关性验证）
d_safe = next(r[2] for r in rows if "安全要点" in r[0])
d_nutr = next((r[2] for r in rows if "营养" in r[0]), None)
assert d_nutr is None or d_safe < d_nutr, "语义检索排序错误！"
print("[3] 语义排序正确：安全要点 距离 < 营养饮食 距离")
print("\n=== Phase 3 冒烟全过：向量入库+语义检索可用 ===")
