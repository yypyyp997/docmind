# 知识库文档目录（不入 Git）

此目录存放知识库的原始文档。文档版权归各自项目所有，为避免归属混淆，本目录不入 Git 仓库。

## 当前内容

| 子目录/文件 | 来源 | 语言 |
|---|---|---|
| fastapi_docs_cn/ | FastAPI 官方中文文档（GitHub fastapi/fastapi 仓库 docs/zh/docs/ 下载） | 中文 |
| langgraph_docs_en/ | LangGraph 官方文档（langchain-ai/langgraph 仓库 docs/docs/ 下载） | 英文 |
| DashScope 百炼 PDF ×3 | 阿里云百炼帮助中心页面打印为 PDF | 中文 |

## 更新方式

文档不需要实时同步，月级重新下载覆盖即可：

1. FastAPI：GitHub fastapi/fastapi 仓库网页进入 docs/zh/docs/ 目录 -> Code -> Download ZIP -> 解压覆盖 fastapi_docs_cn/
2. LangGraph：同上，仓库 langchain-ai/langgraph 的 docs/docs/ 目录
3. DashScope：百炼帮助中心对应页面重新打印为 PDF

## 为什么不入库

- 文档版权归 FastAPI / LangGraph / 阿里云各自项目所有，整包收录会造成归属混淆
- 保持本仓库只包含原创代码与文档
- 重建方式简单（下载覆盖），不影响系统可用性
