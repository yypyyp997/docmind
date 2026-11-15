"""image_parser 单测：真实视觉调用 + 契约边界。真实调用消耗少量额度。"""
import pytest

from ingest.base import ParsingError
from ingest.image_parser import ImageParser

def test_real_image_description(tmp_path):
    """真实视觉调用：生成一个简单测试图片并描述"""
    # 用 PIL 生成一张纯白图片（如果没装 PIL，跳过此测试）
    pytest.importorskip("PIL")
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="white")
    img_path = tmp_path / "test.png"
    img.save(img_path)
    blocks = ImageParser().parse(img_path)
    assert len(blocks) == 1
    assert blocks[0].kind == "image"
    assert blocks[0].content.strip()   #描述非空
    assert blocks[0].extra["source_path"] == str(img_path)

def test_unsupported_format_raises(tmp_path):
    """不支持的格式 → ParsingError"""
    f = tmp_path / "test.gif"       # gif 不在支持列表
    f.write_bytes(b"GIF89a")
    with pytest.raises(ParsingError):
        ImageParser().parse(f)

def test_missing_file_raises(tmp_path):
    """文件不存在 → ParsingError"""
    with pytest.raises(ParsingError):
        ImageParser().parse(tmp_path / "不存在.png")
