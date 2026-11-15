"""视频解析器：分轨提取（音轨转写 + 关键帧视觉描述）再合并（Phase 6 多模态第三块）。

架构：复合模态 = 两个单模态子解析器的组合（复用 AudioParser 和 ImageParser）
- 音轨：ffmpeg 抽取音轨为临时 mp3 → AudioParser 转写
- 画面：ffmpeg 按固定间隔抽帧为临时 png → ImageParser 描述（限制最多 N 帧，控成本）
- 合并：audio Block（转写全文）+ N 个 image Block（关键帧描述，带时间戳）

前置依赖：系统已安装 ffmpeg（PATH 可用）。
已知限制：关键帧时间戳为抽取间隔估算，非精确字幕对齐（精确对齐需 ASR 时间戳，
Paraformer 支持但当前 AudioParser 只取全文——记录为 Phase 6+ 升级项）。
"""
import tempfile
from pathlib import Path

from ingest.base import Block, ParsingError ,Parser
from ingest.audio_parser import AudioParser
from ingest.image_parser import ImageParser

SUPPORTED_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
FRAME_INTERVAL_SECONDS = 30     # 每 30 秒抽一帧（可调：密了准但贵，疏了便宜但糙）
MAX_FRAMES = 10                 # 最多抽 10 帧（控 API 成本）

def _run_ffmpeg(args: list[str]) -> None:
    """执行 ffmpeg 命令，失败抛 ParsingError。"""
    import subprocess
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args,
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            raise ParsingError(f"ffmpeg 执行失败: {r.stderr[-300:]}")
    except FileNotFoundError:
        raise ParsingError("系统未安装 ffmpeg（PATH 不可用）——视频解析需要 ffmpeg")

class VideoParser(Parser):
    """视频解析器：音轨转写 + 关键帧描述的组合解析。"""

    def __init__(self, frame_interval: int = FRAME_INTERVAL_SECONDS,
                 max_frames: int = MAX_FRAMES):
        self.frame_interval = frame_interval
        self.max_frames = max_frames

    def parse(self, path: str | Path) -> list[Block]:
        p = Path(path)
        if not p.exists():
            raise ParsingError(f"文件不存在: {p}")
        if p.suffix.lower() not in SUPPORTED_EXTS:
            raise ParsingError(f"不支持的视频格式: {p.suffix}（支持: {sorted(SUPPORTED_EXTS)}）")

        # 检测视频时长（决定抽帧数）
        duration = self._probe_duration(p)

        # ---- 分轨处理（临时目录，用完自动清理）----
        blocks: list[Block] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            # 音轨 → mp3 → AudioParser
            audio_path = tmp_dir / "audio_track.mp3"
            _run_ffmpeg(["-i", str(p), "-vn", "-acodec", "libmp3lame", "-q:a", "4",
                         str(audio_path)])
            if audio_path.exists() and audio_path.stat().st_size > 0:
                try:
                    blocks.extend(AudioParser().parse(audio_path))
                except Exception:
                    # 静音音轨转写为空：跳过音轨，继续画面帧（鲁棒性）
                    pass

            # 画面 → 按间隔抽帧 → ImageParser（0 帧时保底抽 3 帧：首/中/尾）
            n_frames = min(self.max_frames, max(1, int(duration // self.frame_interval) + 1))
            frame_pattern = tmp_dir / "frame_%03d.png"
            _run_ffmpeg([
                "-i", str(p),
                "-vf", f"fps=1/{self.frame_interval}",
                "-frames:v", str(n_frames),
                str(frame_pattern),
            ])
            frame_files = sorted(tmp_dir.glob("frame_*.png"))
            if not frame_files and duration > 0:
                # 保底策略：短视频按间隔抽不出帧时，抽首/中/尾 3 帧
                for seek in (0, duration / 2, max(duration - 0.1, 0)):
                    fallback = tmp_dir / f"fallback_{int(seek * 10)}.png"
                    _run_ffmpeg(["-ss", f"{seek:.1f}", "-i", str(p), "-frames:v", "1",
                                 str(fallback)])
                frame_files = sorted(tmp_dir.glob("fallback_*.png"))

            img_parser = ImageParser()
            for i, frame in enumerate(frame_files[: self.max_frames]):
                timestamp = i * self.frame_interval
                try:
                    frame_blocks = img_parser.parse(frame)
                    for fb in frame_blocks:
                        fb.extra["timestamp_seconds"] = timestamp
                        fb.extra["video_source"] = str(p)
                        blocks.append(fb)
                except Exception as e:
                    # 单帧描述失败不放弃整个视频：记录跳过（鲁棒性）
                    blocks.append(Block(
                        content=f"[第 {timestamp} 秒关键帧描述失败: {e}]",
                        doc_name=p.name, page=None, kind="image",
                        extra={"video_source": str(p), "frame_failed": True},
                    ))

        if not blocks:
            raise ParsingError("视频解析产出为空（无音轨内容且无有效画面帧）")
        return blocks

    @staticmethod
    def _probe_duration(p: Path) -> float:
        """用 ffprobe 获取视频时长（秒）。失败返回 0（触发默认抽帧数）。"""
        import subprocess
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
                capture_output=True, text=True, timeout=60,
            )
            return float(r.stdout.strip())
        except Exception:
            return 0.0
