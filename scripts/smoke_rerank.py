"""两阶段检索冒烟：召回 → 精排全链路（Phase 4 收官验证）。用完可删。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from storage.db import init_tables
from storage.document_store import save_document
from storage.embedder import embed_texts
from chunking.splitter import Chunk
from retrieval.searcher import search_with_rerank

init_tables()

# 1. 灌数据（覆盖式，跑多次也无害）
chunks = [
    Chunk(content="健身基础\n深蹲是力量训练之王", doc_name="rerank冒烟.md", page=1,
          heading_path="健身基础", chunk_index=0),
    Chunk(content="健身基础 > 安全要点\n膝盖对准脚尖，避免内扣", doc_name="rerank冒烟.md", page=1,
          heading_path="健身基础 > 安全要点", chunk_index=0),
    Chunk(content="营养饮食\n增肌需要热量盈余和充足蛋白质", doc_name="rerank冒烟.md", page=2,
          heading_path="营养饮食", chunk_index=0),
    Chunk(content="恢复休息\n睡眠是最便宜的恢复手段", doc_name="rerank冒烟.md", page=2,
          heading_path="恢复休息", chunk_index=0),
]
save_document("rerank冒烟.md", chunks)
print("[1] 灌数据 OK（4 个 Chunk）")

# 2. 两阶段检索：查询会先 embedding 召回 4 条（库小，recall_k 上限即库大小），再精排取 2
results = search_with_rerank("深蹲安全注意事项", recall_k=20, top_n=2)
print(f"[2] 两阶段检索返回 {len(results)} 条:")
for r in results:
    score = r.get("rerank_score")
    print(f"    score={score} | {r.get('heading_path')} | {r['content'][:30]}")

# 3. 断言：第一名的 content 含"膝盖"或"脚尖"（语义最相关的安全要点域）
assert "膝盖" in results[0]["content"] or "脚尖" in results[0]["content"], \
    f"精排第一名不是安全要点相关: {results[0]['content'][:50]}"
print("[3] 精排排序正确：第一名是安全要点相关内容")

print("\n=== Phase 4 冒烟全过：两阶段检索可用 ===")
