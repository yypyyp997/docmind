"""pdf_parser 单测：基于真实样例 PDF 的行为测试。

注意：这组测试依赖 sample_docs/ 里的真实 PDF 文件（sample.pdf），
它不在 CI 里跑（文件不入库，.gitignore 排除 sample_docs/），
是本地验证性质的"金丝雀测试"。
"""
from pathlib import Path

import pytest

from ingest.base import ParsingError
from ingest.pdf_parser import PdfParser

SAMPLE = Path(__file__).resolve().parent.parent / "sample_docs" / "sample.pdf"

def test_pdf_extracts_with_page_numbers():
    """正常 PDF：产出带页码的 Block，页码递增"""
    blocks = PdfParser().parse(SAMPLE)
    assert len(blocks) > 0
    pages = [b.page for b in blocks if b.page is not None]
    assert pages == sorted(pages)          # 页码不回退
    assert min(pages) >= 1
    assert all(b.doc_name == "sample.pdf" for b in blocks)

def test_pdf_blocks_have_reasonable_size():
    """单 Block 不会过大（切段逻辑生效）"""
    blocks = PdfParser().parse(SAMPLE)
    for b in blocks:
        assert len(b.content) <= 900       # max_len=800 + 余量

def test_missing_file_raises():
    """文件不存在 → ParsingError"""
    with pytest.raises(ParsingError):
        PdfParser().parse("不存在.pdf")

def test_garbage_file_raises():
    """非 PDF 内容（损坏文件）→ ParsingError 而不是崩溃"""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"this is not a pdf at all")
        path = f.name
    with pytest.raises(ParsingError):
        PdfParser().parse(path)
    os.unlink(path)
