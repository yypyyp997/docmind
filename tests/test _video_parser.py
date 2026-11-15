"""video_parser 单测：真实视频（ffmpeg 合成）+ 契约边界。"""
import subprocess
from pathlib import Path

import pytest

from ingest.base import ParsingError
from ingest.video_parser import VideoParser

def _make_test_video(tmp_path, duration=6) -> Path:
    """用 ffmpeg 合成测试视频：纯色画面 + 静音音轨（无需外部素材）"""
    out = tmp_path / "test.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={duration}",   # 蓝色画面
        "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono:d={duration}", # 静音音轨
        "-shortest", str(out),
    ], capture_output=True, text=True, timeout=60)
    assert out.exists()
    return out

def test_real_video_parse(tmp_path):
    """真实视频：ffmpeg 合成 → 解析产出音轨转写块（静音则可能无 audio 块）"""
    video = _make_test_video(tmp_path)
    blocks = VideoParser().parse(video)
    assert len(blocks) >= 1                       # 至少有画面帧描述
    kinds = {b.kind for b in blocks}
    assert kinds <= {"audio", "image"}            # 只会产这两类

def test_missing_file_raises(tmp_path):
    with pytest.raises(ParsingError):
        VideoParser().parse(tmp_path / "不存在.mp4")

def test_corrupted_file_raises(tmp_path):
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not a video")
    with pytest.raises(ParsingError):
        VideoParser().parse(fake)
