"""解析层协议与统一数据结构（ingest 层的地基）。
设计契约：
- 所有解析器（pdf/docx/md/未来多模态）实现 Parser 协议，输出统一的 Block 列表
- 下游（chunking/storage）只认识 Block，不知道原始格式是什么——加新格式零改动
- 解析失败统一抛 ParsingError，由调用方决定怎么处理（协议本身不吞异常）
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class Block:
    """解析产物的统一单元：一段带来源信息的内容。
    引用溯源的灵魂字段是 doc_name + page——回答时能说"出自某文档第几页"。
    """
    content: str                      # 本块的文本内容（表格已转 markdown 保留结构）
    doc_name: str                     # 来源文档名（如 "产品手册.pdf"）
    page: int | None = None           # 页码；PDF 从 1 起，DOCX/MD 无页码概念为 None
    kind: str = "text"                # 块类型："text" / "table" / "heading"
    extra: dict[str, Any] = field(default_factory=dict)  # 可扩展元数据（标题层级、表格规格等）

class ParsingError(Exception):
    """解析失败的统一异常：所有解析器失败都抛它，调用方按类型捕获处理。"""

class Parser:
    """解析器协议：所有格式解析器的行为合同（鸭子类型基座）。
    契约：
    - parse(path) 成功 → 返回 Block 列表（顺序 = 文档阅读顺序）
    - parse(path) 失败 → 抛 ParsingError（带原因），绝不返回半成品列表
    - 协议本身不捕获 ParsingError——那是对它"继续抛出"的循环捕获；
      异常由调用方（ingest 流程）捕获并决定降级策略
    - 无资源管理方法：解析器是无状态的一次性对象，用完即弃，
      文件句柄在实现内部用 with 保证关闭（调用方无感知）
    """
    def parse(self, path: str | Path) -> list[Block]:
        """解析指定文档，返回按阅读顺序排列的 Block 列表。
        :param path: 文档路径（str 或 Path 均可）
        :raises ParsingError: 文件不存在 / 格式损坏 / 内容无法提取
        :return: Block 列表，可能为空（空文档），但绝不返回 None
        """
        raise NotImplementedError("Parser 是协议：由具体格式解析器实现（md_parser/pdf_parser）")
