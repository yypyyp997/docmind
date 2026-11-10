"""md_parser 单测：切分规则、边界形态、异常契约。"""
import os
import tempfile

import pytest

from ingest.base import ParsingError
from ingest.md_parser import MdParser

def test_multi_heading_document():
    """多标题文档：标题开新块，正文归入当前标题块"""
    content = "# 健身基础\n深蹲是王者。\n## 安全要点\n膝盖对准脚尖。"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        path = f.name
    blocks = MdParser().parse(path)
    os.unlink(path)
    assert len(blocks) == 2
    assert blocks[0].kind == "heading" and blocks[0].extra["level"] == 1
    assert "深蹲是王者" in blocks[0].content
    assert blocks[1].extra["level"] == 2
    assert "膝盖对准脚尖" in blocks[1].content

def test_empty_file_returns_empty_list():
    """空文件 → 空列表（契约：绝不返回 None）"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        path = f.name
    assert MdParser().parse(path) == []
    os.unlink(path)

def test_missing_file_raises_parsing_error():
    """文件不存在 → ParsingError（协议契约：失败必抛统一异常）"""
    with pytest.raises(ParsingError):
        MdParser().parse("不存在的文件.md")

def test_plain_text_without_heading():
    """无标题纯文本 → 单个 text 块"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("只有正文没有标题。")
        path = f.name
    blocks = MdParser().parse(path)
    os.unlink(path)
    assert len(blocks) == 1 and blocks[0].kind == "text"
    assert "只有正文" in blocks[0].content
