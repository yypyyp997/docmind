"""DocMind API 服务层：文档知识库的对外 REST 接口。

生产级清单（对齐 v1 api/main.py 的经验）：
- API Key 认证（X-API-Key 头，简单可靠的守护方案）
- 结构化日志（请求耗时/状态码）
- 健康检查（应用存活 + PG/Redis 连通探针）
- 错误语义分层（422 校验 / 401 认证 / 404 不存在 / 500 内部）

端点设计：
- GET    /health                        存活探针（无认证）
- GET    /health/deep                   深度健康（PG/Redis 连通，需认证）
- POST   /api/search                    语义检索（rerank 可选开关）
- POST   /api/ingest                    文档入库（增量，哈希跳过）
- GET    /api/documents                 文档清单
- DELETE /api/documents/{doc_name}      删除文档（级联）
"""
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------- 配置（.env 驱动） ----------
API_KEY = os.getenv("API_KEY", "")          # 空 = 开发模式（跳过认证）

logger = logging.getLogger("docmind.api")

app = FastAPI(
    title="DocMind API",
    description="企业文档知识库：语义检索 + 入库管理",
    version="0.2.0",
)


def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """API Key 认证依赖。未配置 API_KEY 时跳过认证（开发模式）。"""
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
        )


@app.get("/health")
def health():
    """存活探针（无认证——负载均衡/容器编排用）"""
    return {"status": "ok"}


@app.get("/health/deep", dependencies=[Depends(verify_api_key)])
def health_deep():
    """深度健康：PG 与 Redis 连通探针"""
    pg_ok, redis_ok = False, False
    try:
        from storage.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                pg_ok = True
    except Exception as e:
        logger.warning("PG 探针失败: %s", e)
    try:
        from storage.cache import _get_client
        redis_ok = _get_client() is not None
    except Exception as e:
        logger.warning("Redis 探针失败: %s", e)
    return {
        "status": "ok" if pg_ok else "degraded",
        "postgres": pg_ok,
        "redis": redis_ok,
    }


# ---------- 请求/响应模型 ----------

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(3, ge=1, le=20)
    doc_name: str = ""
    use_rerank: bool = True


class IngestRequest(BaseModel):
    path: str = Field(..., description="文档绝对路径（服务与解析同机的部署形态）")


@app.post("/api/search", dependencies=[Depends(verify_api_key)])
def api_search(req: SearchRequest):
    """语义检索（rerank 可选开关）"""
    started = time.time()
    from retrieval.searcher import search, search_with_rerank

    if req.use_rerank:
        results = search_with_rerank(req.query, recall_k=20, top_n=req.top_k,
                                     doc_name=req.doc_name or None)
    else:
        results = search(req.query, top_k=req.top_k, doc_name=req.doc_name or None)

    return {
        "query": req.query,
        "results": results,
        "latency_ms": round((time.time() - started) * 1000),
    }


@app.post("/api/ingest", dependencies=[Depends(verify_api_key)])
def api_ingest(req: IngestRequest):
    """文档入库：解析 → 切分 → 向量化 → 存储（增量，哈希相同跳过）"""
    from ingest.factory import get_parser
    from chunking.splitter import split_blocks
    from storage.document_store import save_document, compute_hash

    path = Path(req.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {req.path}")

    try:
        blocks = get_parser(str(path)).parse(str(path))
        chunks = split_blocks(blocks)
        file_hash = compute_hash(path.read_text(encoding="utf-8", errors="ignore"))
        saved = save_document(path.name, chunks, content_hash=file_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入库失败: {e}")

    if saved == 0:
        return {"status": "skipped", "doc_name": path.name, "detail": "内容未变（哈希相同）"}
    return {"status": "ingested", "doc_name": path.name,
            "blocks": len(blocks), "chunks": len(chunks)}


@app.get("/api/documents", dependencies=[Depends(verify_api_key)])
def api_documents():
    """文档清单"""
    return list_documents_safe()


def list_documents_safe():
    from storage.document_store import list_documents
    return list_documents()


@app.delete("/api/documents/{doc_name}", dependencies=[Depends(verify_api_key)])
def api_delete_document(doc_name: str):
    """删除文档（级联删除 Chunk）"""
    from storage.document_store import delete_document, get_document_chunks
    existing = get_document_chunks(doc_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_name}")
    deleted = delete_document(doc_name)
    return {"status": "deleted", "doc_name": doc_name, "chunks_removed": deleted}
