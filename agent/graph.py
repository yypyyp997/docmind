"""Agent 层：LangGraph 问答图（检索 → 生成 → 组装），引用溯源输出。

图结构（agent/__init__.py 的设计契约：双层图简化为单层线性）：
    START → retrieve → generate → build_answer → END

两种执行形态共用同一张图（编排单源，入口两个）：
- ask()：graph.invoke —— 阻塞跑完返回终态（/api/ask stream=false）
- ask_stream()：graph.stream(stream_mode=["messages", "updates"]) —— LLM token
  从图内逐段透出（/api/ask stream=true，SSE 真流式）

messages 模式能透传 token 的前提：模型调用走 LangChain ChatModel 抽象
（本模块的 _QwenChatModel 封装直调 dashscope），直调 SDK 的 token 不进图的事件流。
"""
import re
from typing import TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage,AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END

from agent.prompts.qa_prompt import QA_SYSTEM_PROMPT, QA_USER_PROMPT
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("agent.graph")

class QAState(TypedDict):
    """问答图的状态契约：节点间只通过这个字典传递数据。"""
    question: str                    # 用户问题
    doc_name: str                    # 可选文档过滤（"" = 不过滤）
    top_k: int                       # 返回切片数
    contexts: list[dict]             # 检索切片（searcher 返回结构）
    query_vector: list[float] | None  # 问题向量（复用：知识库检索 + 会话召回）
    history: list[dict]              # 装配好的对话历史 [{"role","content"}]
    context_text: str                # 编号后的检索内容文本
    answer: str                      # LLM 生成的答案原文
    sources: list[dict]              # 溯源结构（引用解析结果）
    llm_error: str                   # LLM 调用失败信息（空 = 成功）

def _retrieve(state: QAState) -> dict:
    """检索节点：两阶段检索（召回→精排），失败降级为纯向量。"""
    from retrieval.searcher import search_with_rerank

    results = search_with_rerank(
        state["question"],
        recall_k=settings.RECALL_K,
        top_n=state["top_k"],
        doc_name=state["doc_name"] or None,
        query_vector=state.get("query_vector"),
    )
    logger.info("检索完成: %s 条", len(results),
                extra={"hits": len(results), "question": state["question"][:50]})
    return {"contexts": results}

def _format_context(contexts: list[dict]) -> str:
    """切片编号组装：[1] 标题路径 (文档 p页)\n内容\n\n[2] ..."""
    parts = []
    for i, ctx in enumerate(contexts, 1):
        page = f" p{ctx['page']}" if ctx.get("page") else ""
        parts.append(f"[{i}] {ctx['heading_path']} ({ctx['doc_name']}{page})\n{ctx['content']}")
    return "\n\n".join(parts)

def _format_history(history: list[dict]) -> str:
    """历史消息 → 提示词文本块（带序号，模型能分清时序）。"""
    if not history:
        return "（无，本轮为会话首轮）"
    lines = []
    for i, msg in enumerate(history, 1):
        role = "用户" if msg.get("role") == "user" else "助手"
        lines.append(f"{i}. {role}: {(msg.get('content') or '').strip()[:500]}")
    return "\n".join(lines)

class _QwenChatModel(BaseChatModel):
    """qwen-max 的 LangChain ChatModel 封装：直调 dashscope（阻塞 + 流式）。

    存在的理由：graph 的 messages 流式模式只认 LangChain ChatModel 的
    callback 链——把项目既有的直调 dashscope 封装进这个抽象，
    同一张图就能同时服务 JSON 与流式两种形态（编排单源）。
    不引第三方集成包：依赖面最小，dashscope 调用形态与 93 例基线完全同源。
    """
    model_name: str = "qwen-max"
    api_key: str = ""

    @property
    def _llm_type(self) -> str:
        return "dashscope-generation"

    def _convert(self, messages: list) -> str:
        """System(规则) + Human(内容) 拼回 prompt 文本（dashscope prompt 式接口的输入）。"""
        return "\n\n".join(str(m.content) for m in messages)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        import dashscope
        prompt = self._convert(messages)
        resp = dashscope.Generation.call(
            model=self.model_name,
            prompt=prompt,
            api_key=self.api_key,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"API {resp.code}: {resp.message}")
        text = (resp.output.text or "").strip()
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        import dashscope
        prompt = self._convert(messages)
        responses = dashscope.Generation.call(
            model=self.model_name,
            prompt=prompt,
            api_key=self.api_key,
            stream=True,
            incremental_output=True,
        )
        for resp in responses:
            if resp.status_code != 200:
                raise RuntimeError(f"API {resp.code}: {resp.message}")
            delta = resp.output.text
            if delta:
                yield ChatGenerationChunk(message=AIMessageChunk(content=delta))

def _make_llm() -> _QwenChatModel:
    """构造聊天模型实例（独立函数：测试替换点）。"""
    return _QwenChatModel(
        model_name="qwen-max",
        api_key=settings.DASHSCOPE_API_KEY.get_secret_value(),
    )

def _generate(state: QAState, config: RunnableConfig) -> dict:
    """生成节点：ChatModel 消息式调用。config 必须透传给模型——
    LangGraph 的 messages 流式模式靠 config 里的回调链收到 token。"""
    context_text = _format_context(state["contexts"])

    # 检索为空：跳过 LLM 调用（省钱+省延迟），直接诚实说不知道
    if not state["contexts"]:
        return {
            "context_text": context_text,
            "answer": "知识库中没有相关内容。",
            "llm_error": "",
        }

    llm = _make_llm()
    messages = [
        SystemMessage(content=QA_SYSTEM_PROMPT),
        HumanMessage(content=QA_USER_PROMPT.format(
            history=_format_history(state.get("history", [])),
            context=context_text[:6000],  # 防超长（约 4-5 个切片的安全余量）
            question=state["question"],
        )),
    ]
    try:
        resp = llm.invoke(messages, config=config)
        answer = resp.content if isinstance(resp.content, str) else str(resp.content)
        if not answer.strip():
            return {"context_text": context_text, "llm_error": "LLM 返回了空回答"}
        return {
            "context_text": context_text,
            "answer": answer.strip(),
            "llm_error": "",
        }
    except Exception as e:
        logger.warning("LLM 调用失败: %s", e)
        return {"context_text": context_text, "llm_error": str(e)[:200]}

def _parse_citations(answer: str, contexts: list[dict]) -> list[dict]:
    """解析答案中的 [n] 引用 → 结构化 sources（图与流式路径共用）。"""
    cited = []
    for m in re.finditer(r"\[(\d+)\]", answer):
        n = int(m.group(1))
        if 1 <= n <= len(contexts) and n not in cited:
            cited.append(n)

    return [
        {
            "ref": n,
            "doc_name": contexts[n - 1]["doc_name"],
            "heading_path": contexts[n - 1]["heading_path"],
            "page": contexts[n - 1].get("page"),
            "snippet": contexts[n - 1]["content"][:120],
        }
        for n in cited
    ]

def _build_answer(state: QAState) -> dict:
    """组装节点：解析答案中的 [n] 引用 → 结构化 sources（引用溯源）。"""
    sources = _parse_citations(state.get("answer", ""), state["contexts"])
    logger.info("答案组装完成: 引用 %s 个来源", len(sources),
                extra={"cited": [s["ref"] for s in sources]})
    return {"sources": sources}

def build_graph():
    """构建并编译问答图。返回 CompiledGraph（invoke/stream 双接口）。"""
    g = StateGraph(QAState)
    g.add_node("retrieve", _retrieve)
    g.add_node("generate", _generate)
    g.add_node("build_answer", _build_answer)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "build_answer")
    g.add_edge("build_answer", END)
    return g.compile()

def ask(question: str, doc_name: str = "", top_k: int | None = None,
        query_vector: list[float] | None = None,
        history: list[dict] | None = None) -> QAState:
    """阻塞问答入口：graph.invoke 跑完整图，返回终态（/api/ask stream=false）。"""
    graph = build_graph()
    result = graph.invoke({
        "question": question,
        "doc_name": doc_name,
        "top_k": top_k or settings.SEARCH_TOP_K,
        "query_vector": query_vector,
        "history": history or [],
        "contexts": [],
        "context_text": "",
        "answer": "",
        "sources": [],
        "llm_error": "",
    })
    return result

def ask_stream(question: str, doc_name: str = "", top_k: int | None = None,
               query_vector: list[float] | None = None,
               history: list[dict] | None = None,
               session_id: str = ""):
    """流式问答入口：消费 graph.stream 的多模式事件，逐个产出 api 层事件 dict。

    真流式：LLM token 由 messages 模式从图内透出，到达即 yield。
    事件契约（api 层 SSE 客户端按此消费）：
      session   首个事件，带回 session_id（客户端续会话用）
      retrieved 检索完成，带 contexts（客户端可先渲染引用来源）
      delta     增量答案文本（顺序拼接即全量）
      done      生成结束：全量 answer + sources + session_id
      error     失败（之后不再有事件）
    会话持久化由 api 层在 done 事件后完成（agent 层不碰存储）。
    """
    top_k = top_k or settings.SEARCH_TOP_K
    history = history or []
    yield {"type": "session", "session_id": session_id}

    graph = build_graph()
    stream = graph.stream(
        {
            "question": question,
            "doc_name": doc_name,
            "top_k": top_k,
            "query_vector": query_vector,
            "history": history,
            "contexts": [],
            "context_text": "",
            "answer": "",
            "sources": [],
            "llm_error": "",
        },
        stream_mode=["messages", "updates"],
    )

    contexts: list[dict] = []
    chunks: list[str] = []
    sources: list[dict] = []
    try:
        for mode, payload in stream:
            if mode == "messages":
                msg_chunk, _meta = payload
                text = msg_chunk.content if isinstance(msg_chunk.content, str) else ""
                if text:
                    chunks.append(text)
                    yield {"type": "delta", "text": text}
            elif mode == "updates":
                for node_name, update in payload.items():
                    if node_name == "retrieve":
                        contexts = update.get("contexts", [])
                        yield {"type": "retrieved", "contexts": contexts}
                    elif node_name == "generate":
                        llm_error = update.get("llm_error", "")
                        if llm_error:
                            yield {"type": "error", "detail": llm_error}
                            return
                        if not chunks and update.get("answer"):
                            # 空检索直通：答案不经 LLM 流式生成，从节点更新里取出
                            chunks.append(update["answer"])
                            yield {"type": "delta", "text": update["answer"]}
                    elif node_name == "build_answer":
                        sources = update.get("sources", [])
    except Exception as e:
        logger.warning("流式执行异常: %s", e)
        yield {"type": "error", "detail": str(e)[:200]}
        return

    answer = "".join(chunks).strip()
    logger.info("流式答案组装完成: 引用 %s 个来源", len(sources),
                extra={"cited": [s["ref"] for s in sources]})
    yield {"type": "done", "answer": answer, "sources": sources, "session_id": session_id}
