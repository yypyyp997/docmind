"""工厂单测：扩展名路由、大小写容错、未命中契约。"""
import pytest

from ingest.base import ParsingError
from ingest.factory import get_parser
from ingest.md_parser import MdParser
from ingest.pdf_parser import PdfParser
from ingest.docx_parser import DocxParser

def test_routes_by_extension():
    """按扩展名返回对应解析器实例"""
    assert isinstance(get_parser("a.md"), MdParser)
    assert isinstance(get_parser("b.pdf"), PdfParser)
    assert isinstance(get_parser("c.docx"), DocxParser)

def test_extension_case_insensitive():
    """大写扩展名也能命中（suffix.lower() 生效）"""
    assert isinstance(get_parser("报告.PDF"), PdfParser)
    assert isinstance(get_parser("笔记.MD"), MdParser)

def test_unsupported_extension_raises():
    """不支持的格式 → ParsingError 且信息含支持列表"""
    with pytest.raises(ParsingError) as exc_info:
        get_parser("data.txt")
    assert ".md" in str(exc_info.value)   # 报错信息里有支持格式提示
