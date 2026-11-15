"""音频解析器：调用 DashScope ASR（ParaHandler）转写音频为文本（Phase 6 多模态第二块）。

架构契约（与其他解析器一致）：
- 产出的 Block：content = 转写文本（可含时间戳段落）
  kind = "audio"，extra 记录音频时长、模型名等
- 支持格式：mp3 / wav / m4a / aac / flac / opus
- 失败契约：文件不存在 / 格式不支持 / API 失败 → TranscribeError（同族异常）

前置：DASHSCOPE_API_KEY 已配置（.env），paraformer-v2 模型可用。
"""
import os
import time
from pathlib import Path

from ingest.base import Block, ParsingError ,Parser

SUPPORTED_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".opus"}
ASR_MODEL = "paraformer-v2"

class TranscribeError(Exception):
    """音频转写失败的统一异常。"""

def _poll_task(api_key: str, task_id: str, max_wait: int = 300) -> dict:
    """轮询异步转写任务直到完成（Paraformer 是异步任务型 API）。

    :raises TranscribeError: 超时或任务失败
    """
    import dashscope
    deadline = time.time() + max_wait
    while time.time() < deadline:
        result = dashscope.AsyncTask.fetch(task=task_id, api_key=api_key)
        if result.status_code != 200:
            raise TranscribeError(f"任务查询失败 code={result.status_code}: {result.message}")
        task = result.output.task
        if task == "FAILED":
            msg = getattr(result.output, "message", "") or "未知原因"
            raise TranscribeError(f"转写任务失败: {msg}")
        if task == "SUCCEEDED":
            return result.output
        time.sleep(3)
    raise TranscribeError(f"转写超时（>{max_wait}s）")

class AudioParser(Parser):
    """音频解析器：ASR 转写音频为文本，产出统一的转写 Block。"""

    def parse(self, path: str | Path) -> list[Block]:
        p = Path(path)
        if not p.exists():
            raise ParsingError(f"文件不存在: {p}")
        if p.suffix.lower() not in SUPPORTED_EXTS:
            raise ParsingError(f"不支持的音频格式: {p.suffix}（支持: {sorted(SUPPORTED_EXTS)}）")
        if p.stat().st_size > 2 * 1024 * 1024 * 1024:
            raise ParsingError(f"音频文件过大（>2GB）: {p}")

        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ParsingError("环境变量 DASHSCOPE_API_KEY 未设置，无法转写音频")

        file_url = f"file://{p.resolve()}"
        try:
            import dashscope
            resp = dashscope.audio.asr.Transcription.call(
                model=ASR_MODEL,
                file_urls=[file_url],
                language_hints=["zh"],
            )
            if resp.status_code != 200:
                raise TranscribeError(f"提交转写任务失败 code={resp.status_code}: {resp.message}")
            task_id = resp.output.task_id
        except TranscribeError:
            raise
        except Exception as e:
            raise ParsingError(f"ASR 提交失败: {e}") from e

        output = _poll_task(api_key, task_id)

        # 提取转写文本：results[0]["transcription"]["text"]
        try:
            info = output["results"][0]["transcription"]
            full_text = info["text"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise ParsingError(f"转写结果结构异常: {e}") from e

        if not full_text:
            raise ParsingError("转写结果为空（音频可能无有效语音内容）")

        return [
            Block(
                content=full_text,
                doc_name=p.name,
                page=None,
                kind="audio",
                extra={
                    "source_path": str(p),
                    "asr_model": ASR_MODEL,
                    "duration_seconds": info.get("duration_seconds"),
                },
            )
        ]
