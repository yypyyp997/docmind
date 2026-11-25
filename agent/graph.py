"""Agent 层：LangGraph 问答图（检索 → 生成 → 组装），引用溯源输出。

图结构（agent/__init__.py 的设计契约：双层图简化为单层线性）：
    START → retrieve → generate → build_answer → END

为什么线性起步：
- 当前场景（个人知识库问答）不需要路由分支——所有问题都走检索问答
- __init__.py 契约里的"路由"（先判断问题是否需要检索）等真实需求出现再加节点
- LangGraph 的价值在节点编排与状态传递，线性图同样是它的标准用法
"""
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from agent.prompts.qa_prompt import QA_SYSTEM_PROMPT
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

def _generate(state: QAState) -> dict:
    """生成节点：dashscope qwen-max，检索内容 + 问题 → 答案。"""
    import dashscope

    context_text = _format_context(state["contexts"])

    # 检索为空：跳过 LLM 调用（省钱+省延迟），直接诚实说不知道
    if not state["contexts"]:
        return {
            "context_text": context_text,
            "answer": "知识库中没有相关内容。",
            "llm_error": "",
        }

    prompt = QA_SYSTEM_PROMPT.format(
        history=_format_history(state.get("history", [])),
        context=context_text[:6000],  # 防超长（约 4-5 个切片的安全余量）
        question=state["question"],
    )
    try:
        resp = dashscope.Generation.call(
            model="qwen-max",
            prompt=prompt,
            api_key=settings.DASHSCOPE_API_KEY.get_secret_value(),
        )
        if resp.status_code != 200:
            logger.warning("LLM 调用失败: %s %s", resp.code, resp.message)
            return {"context_text": context_text,
                    "llm_error": f"API {resp.code}: {resp.message}"}
        return {
            "context_text": context_text,
            "answer": resp.output.text.strip(),
            "llm_error": "",
        }
    except Exception as e:
        logger.warning("LLM 异常: %s", e)
        return {"context_text": context_text, "llm_error": str(e)[:200]}

def _build_answer(state: QAState) -> dict:
    """组装节点：解析答案中的 [n] 引用 → 结构化 sources（引用溯源）。"""
    import re

    answer = state.get("answer", "")
    contexts = state["contexts"]

    # 找出答案里实际引用的编号（去重保序）
    cited = []
    for m in re.finditer(r"\[(\d+)\]", answer):
        n = int(m.group(1))
        if 1 <= n <= len(contexts) and n not in cited:
            cited.append(n)

    sources = [
        {
            "ref": n,
            "doc_name": contexts[n - 1]["doc_name"],
            "heading_path": contexts[n - 1]["heading_path"],
            "page": contexts[n - 1].get("page"),
            "snippet": contexts[n - 1]["content"][:120],
        }
        for n in cited
    ]
    logger.info("答案组装完成: 引用 %s 个来源", len(sources),
                extra={"cited": cited})
    return {"sources": sources}

def build_graph():
    """构建并编译问答图。返回 CompiledGraph（invoke 接口）。"""
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
    """问答入口：一次调用走完整图，返回终态（含 answer + sources）。

    :param question: 用户问题
    :param doc_name: 可选，限定在某文档内问答
    :param top_k: 返回切片数（默认 settings.SEARCH_TOP_K）
    :param query_vector: 可选，预计算的问题向量（API 层算一次，检索与历史召回复用）
    :param history: 可选，装配好的对话历史（API 层从 chat_store 分层装配）
    """
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
