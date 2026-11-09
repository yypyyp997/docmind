# ADR 001 · 技术栈选型

日期：2026-11-09 ｜ 状态：已接受

## 背景
前作 fitness_rag_agent（单域 RAG/Agent，SQLite+Chroma+FastAPI）验证了工程方法论：双层 LangGraph 编排、五层降级防线、评估驱动迭代、提示词防注入。本项目为新领域（企业文档问答）从零立项，目标是对齐生产端技术栈。v1 的已知教训：ChatTongyi.stream 聚合导致双路径（应在模型层修）、SQLite 向量/关系库分离（企业文档场景关系+向量应合库）、无引用溯源（企业落地硬需求）、解析层缺失（markdown 知识库避开了文档解析的全部难度）。

## 决策
- 编排：LangGraph（方法论沿用，代码重写；双层图 → 本项目简化为路由+检索问答+溯源组装）
- 模型接入：DashScope 直连（qwen-max / text-embedding-v4 / gte-rerank）；流式在模型包装层第一天做对（v1 教训前置）
- 存储：PostgreSQL 一库两用（关系元数据 + pgvector 向量，cosine）——数据量级在十万块以内，独立向量库（Milvus）运维成本不划算；抽象 VectorStore 接口保留后路
- 解析：统一接入层（Parser 协议 → 统一 Block 产物），首期 PDF/DOCX/MD，多模态（图片视觉描述/ASR）按期扩展
- 溯源：块级元数据（文档/页码/位置）贯穿到回答引用
- 缓存/限流：Redis（Phase 5，三用途一次落地）
- 工具协议：MCP（Phase 7，工具进程化终点形态）
- 部署：Docker compose（app+postgres，+redis 后期）；单机规模克制选型，不上 K8s
- 开发环境：Windows + PyCharm，运行侧 WSL2/Docker（Linux 肌肉）

## 代价
- 不做 K8s：牺牲「多机编排经验」的简历词，换取不过度镀金（compose 概念与 K8s 一一对应，迁移认知可面谈）
- 不上 Dify 本体：牺牲低代码平台实操，以「Dify vs 代码版」对比认知替代
- 首版只支持文档：多模态延后到 Phase 6，接受「多模态经验优先」类 JD 暂时接不住
- PostgreSQL 强绑定：放弃 SQLite 零运维，换取企业级数据库经验（CI 用 SQLite 档兼容跑测）
