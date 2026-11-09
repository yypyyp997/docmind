# DocMind · 企业文档智能问答

面向企业文档场景的 RAG + Agent 智能问答系统：多格式文档解析 → 结构感知切分 → 向量检索（pgvector）→ 重排 → 引用溯源回答。

技术栈：LangGraph · PostgreSQL + pgvector · Redis（后期） · DashScope（qwen-max / text-embedding-v4 / gte-rerank）· MCP（后期） · Docker

> 前作：[fitness_rag_agent](https://github.com/yypyyp997/fitness_rag_agent)（健身领域 RAG/Agent，22 条踩坑复盘）。本项目沿用其验证过的工程方法论（编排分层 / 降级防线 / 评估驱动 / 提示词防注入），在文档领域从零落地企业级技术栈。

## 路线图
- [x] Phase 0 骨架与立项
- [ ] Phase 1 文档解析层（PDF/DOCX/MD：文本+表格+标题层级）
- [ ] Phase 2 切分 / 向量化 / pgvector 入库
- [ ] Phase 3 检索问答链路（LangGraph 编排 + 引用溯源）
- [ ] Phase 4 rerank 两阶段（gte-rerank）
- [ ] Phase 5 Redis（缓存 / 限流 / 计数器）
- [ ] Phase 6 多模态扩展（图片描述 / ASR 音频）
- [ ] Phase 7 MCP 工具进程化
- [ ] Phase 8 RAGAS 对照评估

## 设计决策（ADR）
见 [docs/adr/](docs/adr/) —— 每个关键选型一份决策记录（背景 / 决策 / 代价）。

## 快速开始
```bash
# Phase 2 后补充：docker compose up → 建库 → ingest 示例文档 → 提问
```

## 评估
见 [evaluation/](evaluation/) —— 评估驱动迭代，每期基线对照（Phase 3 后补充）。
