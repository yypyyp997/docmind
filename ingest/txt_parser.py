"""纯文本解析器：按空行分段（ingest 层第四个实现，最简单的一个）。

txt 没有任何结构标记（无标题/无页码/无样式），所以：
- 所有 Block 的 kind 恒为 "text"，page 恒为 None，extra 恒为空
- 分段依据只有空行：连续的非空行合成为一段，空行是分段边界
- 空文件 → 返回 []；文件不存在/编码错误 → 抛 ParsingError（协议契约）
"""
from pathlib import Path

from ingest.base import Block, Parser, ParsingError

class TxtParser(Parser):
    """纯文本解析器：实现 Parser 协议。无状态，用完即弃。"""

    def parse(self, path: str | Path) -> list[Block]:
        """按空行分段，每段一个 text Block。"""
        p = Path(path)
        if not p.exists():
            raise ParsingError(f"文件不存在: {p}")
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ParsingError(f"编码错误（需要 UTF-8）: {p}") from e

        blocks: list[Block] = []
        current_lines: list[str] = []      # 当前段落攒的行

        for line in text.splitlines():
            if line.strip():
                current_lines.append(line.rstrip())
            else:
                # 空行 = 段落边界：结算当前段（攒到过行才结算）
                if current_lines:
                    blocks.append(Block(
                        content="\n".join(current_lines),
                        doc_name=p.name,
                        page=None,
                        kind="text",
                    ))
                    current_lines = []     # 新列表，继续攒下一段

        # 文件结尾的最后一段（没有空行触发，手动结算）
        if current_lines:
            blocks.append(Block(
                content="\n".join(current_lines),
                doc_name=p.name,
                page=None,
                kind="text",
            ))

        return blocks
