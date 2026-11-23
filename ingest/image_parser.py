"""图片解析器：调用 qwen-vl 视觉模型生成图片描述（Phase 6 多模态第一块）。

架构契约（与其他解析器一致）：
- 产出的 Block：content = 视觉模型生成的图片描述文本
  kind = "image"，extra 记录原图路径与描述模型名
- 支持格式：png / jpg / jpeg / webp / bmp
- 失败契约：文件不存在 / 格式不支持 / API 失败 → ParsingError（或 EmbeddingError 同族处理）

前置：DASHSCOPE_API_KEY 已配置（.env），qwen-vl-max 模型可用。
"""
import base64
from pathlib import Path
from config.settings import settings
from ingest.base import Block, Parser, ParsingError

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VL_MODEL = "qwen-vl-ocr"

def _image_to_data_url(path: Path) -> str:
    """图片转 base64 data URL（DashScope VL 接口的输入格式）"""
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg"}.get(suffix, suffix)
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"

class ImageParser(Parser):
    """图片解析器：视觉模型生成图片描述，产出统一的描述性 Block。"""

    def parse(self, path: str | Path) -> list[Block]:
        p = Path(path)
        if not p.exists():
            raise ParsingError(f"文件不存在: {p}")
        if p.suffix.lower() not in SUPPORTED_EXTS:
            raise ParsingError(f"不支持的图片格式: {p.suffix}（支持: {sorted(SUPPORTED_EXTS)}）")

        api_key = settings.DASHSCOPE_API_KEY.get_secret_value()
        if not api_key:
            raise ParsingError("DASHSCOPE_API_KEY 未设置（.env / settings），无法做图片视觉描述")
        data_url = _image_to_data_url(p)
        try:
            import dashscope
            resp = dashscope.MultiModalConversation.call(
                model=VL_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"image": data_url},
                        {"text": "请详细描述这张图片的内容：图中有什么对象、文字、图表或流程？"
                                 "如果是架构图或流程图，请描述其结构和各部分的关系。"},
                    ],
                }],
                api_key=api_key,
            )
        except Exception as e:
            raise ParsingError(f"视觉模型调用失败: {e}") from e

        if resp.status_code != 200:
            raise ParsingError(f"视觉模型返回错误 code={resp.code}: {resp.message}")

        try:
            description = resp.output.choices[0].message.content[0]["text"]
        except (KeyError, IndexError) as e:
            raise ParsingError(f"视觉模型响应结构异常: {e}") from e

        if not description or not description.strip():
            raise ParsingError("视觉模型返回了空描述")

        return [
            Block(
                content=description.strip(),
                doc_name=p.name,
                page=None,
                kind="image",
                extra={"source_path": str(p), "vl_model": VL_MODEL},
            )
        ]
