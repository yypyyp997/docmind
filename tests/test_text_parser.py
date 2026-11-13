"""txt_parser 单测：分段/空文件/异常契约。"""
import pytest

from ingest.base import ParsingError
from ingest.txt_parser import TxtParser

def _write(tmp_path, content):
    p = tmp_path / "笔记.txt"
    p.write_text(content, encoding="utf-8")
    return p

def test_paragraphs_split_by_blank_line(tmp_path):
    """空行分段：连续非空行合成一段"""
    p = _write(tmp_path, "第一段第一行\n第一段第二行\n\n第二段内容")
    blocks = TxtParser().parse(p)
    assert len(blocks) == 2
    assert blocks[0].content == "第一段第一行\n第一段第二行"
    assert blocks[1].content == "第二段内容"
    assert all(b.kind == "text" and b.page is None for b in blocks)

def test_empty_file_returns_empty(tmp_path):
    """空文件 → 空列表"""
    p = _write(tmp_path, "")
    assert TxtParser().parse(p) == []

def test_missing_file_raises(tmp_path):
    """文件不存在 → ParsingError"""
    with pytest.raises(ParsingError):
        TxtParser().parse(tmp_path / "不存在.txt")
