"""audio_parser 单测：契约边界为主。真实转写依赖音频文件，标记 skip 机制。"""
from pathlib import Path

import pytest

from ingest.audio_parser import AudioParser, TranscribeError
from ingest.base import ParsingError

def test_unsupported_format_raises(tmp_path):
    f = tmp_path / "test.mid"       # midi 不在支持列表
    f.write_bytes(b"MThd")
    with pytest.raises(ParsingError):
        AudioParser().parse(f)

def test_missing_file_raises(tmp_path):
    with pytest.raises(ParsingError):
        AudioParser().parse(tmp_path / "不存在.mp3")

def test_missing_key_raises(tmp_path, monkeypatch):
    """Key 缺失 → ParsingError（在 API 提交前拦截）"""
    from pydantic import SecretStr
    from config.settings import settings
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", SecretStr(""))
    f = tmp_path / "test.mp3"
    f.write_bytes(b"fake-audio-content")
    with pytest.raises(ParsingError):
        AudioParser().parse(f)

def test_real_transcription():
    """真实转写：需要 sample_docs 里有音频文件，没有则跳过"""
    sample = Path(r"D:\docmind\docs\official\sample_audio.mp3")
    if not sample.exists():
        pytest.skip("无测试音频文件：放一个含中文语音的 mp3 到 docs/official/sample_audio.mp3")
    blocks = AudioParser().parse(sample)
    assert len(blocks) == 1
    assert blocks[0].kind == "audio"
    assert len(blocks[0].content) > 5
