"""storage 层冒烟测试：建表 → 存 → 查 → 删 全链路（用完可删）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from chunking.splitter import Chunk
from storage.db import init_tables
from storage.document_store import (
    delete_document,
    get_document_chunks,
    list_documents,
    save_document,
)

# 1. 建表（幂等）
init_tables()
print("[1] 建表 OK")

# 2. 手造两个 Chunk（模拟切分器产出）
chunks = [
    Chunk(content="健身基础\n深蹲是力量训练之王",
          doc_name="smoke手册.md", page=1,
          heading_path="健身基础", chunk_index=0),
    Chunk(content="健身基础 > 安全要点\n膝盖对准脚尖",
          doc_name="smoke手册.md", page=1,
          heading_path="健身基础 > 安全要点", chunk_index=0),
]

# 3. 存
doc_id = save_document("smoke手册.md", chunks)
print(f"[2] save_document OK, chunks 数: {doc_id}")

# 4. 查
docs = list_documents()
print(f"[3] list_documents: {docs}")

got = get_document_chunks("smoke手册.md")
print(f"[4] get_document_chunks: {len(got)} 条")
assert got[0]["heading_path"] == "健身基础"
assert "深蹲" in got[0]["content"]

# 5. 重复入库（覆盖式更新验证）
save_document("smoke手册.md", chunks)
got2 = get_document_chunks("smoke手册.md")
assert len(got2) == 2, f"覆盖式入库后不应翻倍: {len(got2)}"
print("[5] 覆盖式入库 OK（没有产生重复数据）")

# 6. 删
n = delete_document("smoke手册.md")
print(f"[6] delete_document 删了 {n} 条 Chunk")
assert get_document_chunks("smoke手册.md") == []

print("\n=== 冒烟全过：storage 层可用 ===")
