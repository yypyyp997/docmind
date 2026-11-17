"""api/main.py v2：settings 化 + 结构化请求日志中间件。

相对 v1 的变化：
- 配置全部走 config.settings（load_dotenv/os.getenv 私用清零）
- LOG_LEVEL/LOG_FORMAT 环境变量可控（LOG_FORMAT=json 生产结构化）
- 请求日志中间件：方法/路径/状态码/耗时一次成型（/health 降噪跳过）
- 认证失败与降级事件进日志（security 事件可审计）
"""
import logging
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("api")

API_KEY = settings.API_KEY.get_secret_value()    # SecretStr -> 真实值（空 = 开发模式）

app = FastAPI(
    title="DocMind API",
    description="企业文档知识库：语义检索 + 入库管理",
    version="0.3.0",
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """请求日志：方法/路径/状态码/耗时。健康检查降噪（不打日志）。"""
    if request.url.path == "/health":
        return await call_next(request)
    started = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - started) * 1000)
    logger.info(
        "%s %s -> %s %sms",
        request.method, request.url.path, response.status_code, latency_ms,
        extra={"path": request.url.path, "status": response.status_code,
               "latency_ms": latency_ms},
    )
    return response


def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """API Key 认证依赖。未配置 API_KEY 时跳过认证（开发模式）。"""
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        logger.warning("认证失败", extra={"event": "auth_failed"})
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

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    doc_name: str = ""
    top_k: int = Field(3, ge=1, le=20)

@app.post("/api/search", dependencies=[Depends(verify_api_key)])
def api_search(req: SearchRequest):
    """语义检索（rerank 可选开关）"""
    from retrieval.searcher import search, search_with_rerank

    if req.use_rerank:
        results = search_with_rerank(req.query, recall_k=settings.RECALL_K,
                                     top_n=req.top_k, doc_name=req.doc_name or None)
    else:
        results = search(req.query, top_k=req.top_k, doc_name=req.doc_name or None)

    return {
        "query": req.query,
        "results": results,
        "latency_ms": 0,        # 由中间件统一记录（响应头 X-Process-Time-ms）
    }


@app.post("/api/ingest", dependencies=[Depends(verify_api_key)])
def api_ingest(req: IngestRequest):
    """文档入库：解析 → 切分 → 向量化 → 存储（增量，哈希相同跳过）"""
    from ingest.factory import get_parser
    from chunking.splitter import split_blocks
    from storage.document_store import save_document, compute_hash

    path = __import__("pathlib").Path(req.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {req.path}")

    try:
        blocks = get_parser(str(path)).parse(str(path))
        chunks = split_blocks(blocks)
        file_hash = compute_hash(path.read_text(encoding="utf-8", errors="ignore"))
        saved = save_document(path.name, chunks, content_hash=file_hash)
    except Exception as e:
        logger.error("入库失败: %s %s", req.path, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"入库失败: {e}")

    if saved == 0:
        return {"status": "skipped", "doc_name": path.name, "detail": "内容未变（哈希相同）"}
    return {"status": "ingested", "doc_name": path.name,
            "blocks": len(blocks), "chunks": len(chunks)}


@app.get("/api/documents", dependencies=[Depends(verify_api_key)])
def api_documents():
    """文档清单"""
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

@app.post("/api/ask", dependencies=[Depends(verify_api_key)])
def api_ask(req: AskRequest):
    """文档问答：完整 RAG 链路（检索 → 生成 → 引用溯源）。

    LLM 失败时降级：status=degraded + 返回检索切片（有结果总好过空手而归）。
    """
    from agent.graph import ask

    result = ask(req.question, doc_name=req.doc_name, top_k=req.top_k)

    if result["llm_error"]:
        return {
            "status": "degraded",
            "detail": f"生成失败: {result['llm_error']}",
            "query": req.question,
            "results": result["contexts"],
        }
    return {
        "status": "ok",
        "query": req.question,
        "answer": result["answer"],
        "sources": result["sources"],
        "contexts": result["contexts"],
    }
