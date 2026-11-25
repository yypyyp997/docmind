"""会话历史存储：多轮对话消息的持久化与语义召回（PG + pgvector）。

设计（分层记忆）：
- 持久化：全部对话消息进 PG（chat_messages 表，alembic 迁移）——
  重启/跨天/审计/导出有据可查，不随进程消失
- 分层装配（assemble_history）：
  ① 短窗必进——最近几条原文无条件入提示词（保近因 + 支撑指代消解）
  ② 语义召回——用本轮问题向量在本会话更早的消息里捞主题相关的旧消息
  ③ 预算控制——按 CHAT_CONTEXT_BUDGET_CHARS 从新到旧装配，超了即停
- 向量复用：user 消息的向量 = 知识库检索已算好的问题向量（零额外调用）；
  assistant 消息入库时单独向量化（用户可能引用回答原文追问）
- 会话隔离：召回范围严格限定 session_id 内——跨会话是隐私边界
"""
from config.settings import settings
from storage.db import get_connection
from storage.embedder import embed_texts, EmbeddingError
from utils.logger import get_logger

logger = get_logger("storage.chat_store")

_ANSWER_EMBED_MAX_CHARS = 2000    # 回答向量化的截断上限
_CONTENT_MAX_CHARS = 2000         # 消息正文的入库截断上限

def new_session_id() -> str:
    """生成会话 ID（服务端生成，客户端回传即可续会话）。"""
    import uuid
    return uuid.uuid4().hex

def save_exchange(session_id: str, question: str, answer: str,
                  query_vector: list[float] | None) -> bool:
    """持久化一轮对话（user 行 + assistant 行，同一事务）。

    向量策略：
    - user 行的 embedding 直接复用检索已算好的问题向量（None → 存 NULL，不可召回）
    - assistant 行入库时单独向量化；向量化失败 → 存 NULL（内容不丢，仅不可召回）
    持久化失败返回 False、不抛异常——会话记忆缺失不炸问答主链路。
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO chat_messages (session_id, role, content, embedding)
                       VALUES (%s, 'user', %s, %s::vector)""",
                    (session_id, question[:_CONTENT_MAX_CHARS],
                     str(query_vector) if query_vector is not None else None),
                )
                answer_vec = None
                try:
                    answer_vec = embed_texts([answer[:_ANSWER_EMBED_MAX_CHARS]])[0]
                except EmbeddingError:
                    logger.warning("回答向量化失败，该轮 assistant 消息不可语义召回")
                cur.execute(
                    """INSERT INTO chat_messages (session_id, role, content, embedding)
                       VALUES (%s, 'assistant', %s, %s::vector)""",
                    (session_id, (answer or "（本轮生成失败）")[:_CONTENT_MAX_CHARS],
                     str(answer_vec) if answer_vec is not None else None),
                )
        return True
    except Exception as e:
        logger.warning("会话历史持久化失败: %s", e)
        return False

def get_recent(session_id: str, limit: int) -> list[dict]:
    """最近的 limit 条消息（新→旧返回）。读取失败静默降级为空（不炸主链路）。"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, role, content, created_at
                       FROM chat_messages
                       WHERE session_id = %s
                       ORDER BY created_at DESC, id DESC
                       LIMIT %s""",
                    (session_id, limit),
                )
                rows = cur.fetchall()
    except Exception as e:
        logger.warning("会话历史读取失败: %s", e)
        return []
    return [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]

def recall_messages(session_id: str, query_vector: list[float],
                    exclude_ids: list[int], top_k: int) -> list[dict]:
    """语义召回：本会话内、排除短窗后的消息中，与当前问题向量最近的 top_k 条。"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, role, content, created_at
                       FROM chat_messages
                       WHERE session_id = %s
                         AND embedding IS NOT NULL
                         AND id != ALL(%s)
                       ORDER BY embedding <=> %s::vector
                       LIMIT %s""",
                    (session_id, exclude_ids, str(query_vector), top_k),
                )
                rows = cur.fetchall()
    except Exception as e:
        logger.warning("会话历史召回失败: %s", e)
        return []
    return [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]

def assemble_history(session_id: str, query_vector: list[float] | None) -> list[dict]:
    """分层装配：短窗 + 语义召回 + 字符预算，按时间升序返回 [{"role","content"}]。

    graph 层只管渲染（_format_history），不关心装配细节——分层解耦。
    """
    recent = get_recent(session_id, limit=settings.CHAT_RECENT_TURNS * 2)
    exclude_ids = [m["id"] for m in recent]
    recalled = []
    if query_vector is not None:
        recalled = recall_messages(session_id, query_vector, exclude_ids,
                                   settings.CHAT_RECALL_TOP_K)

    seen = set(exclude_ids)
    merged = list(recent)
    for m in recalled:
        if m["id"] not in seen:
            merged.append(m)
            seen.add(m["id"])
    merged.sort(key=lambda m: (m["created_at"], m["id"]))   # 时间升序

    budget = settings.CHAT_CONTEXT_BUDGET_CHARS
    picked: list[dict] = []
    used = 0
    for m in reversed(merged):               # 从新到旧装，至少保一条
        cost = len(m["content"])
        if picked and used + cost > budget:
            break
        picked.append(m)
        used += cost
    picked.reverse()
    return [{"role": m["role"], "content": m["content"]} for m in picked]
