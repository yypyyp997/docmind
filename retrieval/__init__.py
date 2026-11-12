"""检索层（retrieval）：语义检索入口。查询 → 向量化 → pgvector 距离排序 → top-k。

对外提供：
- search 语义检索（支持 metadata filter：按文档名过滤）

目录里的文件：
- searcher.py   检索主逻辑（rerank 两阶段将在 Phase 4 挂在此层之后）
"""
from retrieval.searcher import search

__all__ = ["search"]
