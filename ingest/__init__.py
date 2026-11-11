"""解析层（ingest）：把各种格式的文档读进来，变成统一格式的内容块（Block）。

这一层回答的问题是："怎么把 PDF / Word / Markdown 变成系统能用的数据？"

对外提供三样东西：
- Block        解析产物的统一格式（一段文字 + 来源信息：哪个文档、第几页、什么类型）
- ParsingError 解析失败的统一异常（文件不存在/格式损坏/编码错误都用它）
- get_parser   工厂函数：给一个文件路径，自动挑对应的解析器

目录里的文件：
- base.py         Block / ParsingError / Parser 协议（解析器的"合同"）
- md_parser.py    Markdown 解析（按 # 标题切分）
- pdf_parser.py   PDF 解析（pypdf，按页提取，带页码）
- docx_parser.py  Word 解析（python-docx，按标题样式切分）
- factory.py      工厂：按扩展名返回对应解析器

使用示例：
    from ingest import get_parser
    blocks = get_parser("手册.pdf").parse("手册.pdf")
    # blocks 里每个 Block 都有 .content / .doc_name / .page / .kind
"""
from ingest.base import Block, Parser, ParsingError
from ingest.factory import get_parser

__all__ = ["Block", "Parser", "ParsingError", "get_parser"]
