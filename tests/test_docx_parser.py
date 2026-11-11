"""docx_parser 单测：标题层级、内容/结构分离、异常契约。

依赖 python-docx 的 Document 对象动态构造测试文档（不依赖手造的样例文件，
测试自包含、可在任何机器跑）。
"""
import pytest
from docx import Document

from ingest.base import ParsingError
from ingest.docx_parser import DocxParser

def _make_docx(tmp_path, paragraphs_spec):
    """辅助：按 [(text, style_name), ...] 构造临时 docx 文件，返回路径。"""
    doc = Document()
    for text, style in paragraphs_spec:
        if style is None:
            doc.add_paragraph(text)
        else:
            doc.add_paragraph(text, style=style)
    path = tmp_path / "测试文档.docx"
    doc.save(str(path))
    return path

def test_heading_levels_parsed(tmp_path):
    """多级标题：Heading 1/2 正确解析 level，正文归入当前标题块"""
    path = _make_docx(tmp_path, [
        ("健身基础", "Heading 1"),
        ("深蹲是王者", "Normal"),
        ("安全要点", "Heading 2"),
        ("膝盖对准脚尖", "Normal"),
    ])
    blocks = DocxParser().parse(path)
    assert len(blocks) == 2
    assert blocks[0].kind == "heading" and blocks[0].extra["level"] == 1
    assert "深蹲是王者" in blocks[0].content
    assert blocks[1].extra["level"] == 2
    assert "膝盖对准脚尖" in blocks[1].content

def test_title_style_maps_to_level1(tmp_path):
    """Title 样式 → level 1（isdigit 保险分支）"""
    path = _make_docx(tmp_path, [("训练手册", "Title"), ("正文内容", "Normal")])
    blocks = DocxParser().parse(path)
    assert blocks[0].kind == "heading" and blocks[0].extra["level"] == 1

def test_content_never_decides_structure(tmp_path):
    """内容 vs 结构分离（9.22 同源原则）：正文以"标题"开头也不会误判为标题"""
    path = _make_docx(tmp_path, [
        ("标题党是什么意思", "Normal"),   # 内容以"标题"开头，但样式是 Normal
    ])
    blocks = DocxParser().parse(path)
    assert len(blocks) == 1
    assert blocks[0].kind == "text"       # 结构判断只认样式

def test_plain_text_without_heading(tmp_path):
    """无标题纯文本 → 单个 text 块"""
    path = _make_docx(tmp_path, [("只有正文", None), ("没有标题", None)])
    blocks = DocxParser().parse(path)
    assert len(blocks) == 1 and blocks[0].kind == "text"
    assert "只有正文" in blocks[0].content and "没有标题" in blocks[0].content

def test_missing_file_raises(tmp_path):
    """文件不存在 → ParsingError"""
    with pytest.raises(ParsingError):
        DocxParser().parse(tmp_path / "不存在.docx")

def test_corrupted_file_raises(tmp_path):
    """损坏文件（文本冒充 docx）→ ParsingError 而不是裸异常"""
    fake = tmp_path / "fake.docx"
    fake.write_text("这不是一个真正的 docx 文件", encoding="utf-8")
    with pytest.raises(ParsingError):
        DocxParser().parse(fake)
