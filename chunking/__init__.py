"""切分层（chunking）：把解析层产出的内容块，重新组织成待入库的文本块（Chunk）。

这一层回答的问题是："怎么把大小不一的内容块，变成大小合适、带着章节出处的入库单元？"

两步切分思路：
- 第一步（按标题分章）：每遇到一个标题就开一个新章节，章节里的内容不会
  跑到别的标题下面（检索不串味，引用能精确到章节）
- 第二步（控制大小）：太长的章节按段落切、段间保留重叠文字；太碎的
  （不足 min_len 字）并到相邻章节

对外提供：
- Chunk        入库单元（content 里已经拼好了章节路径，检索时标题词参与匹配）
- split_blocks 主入口：给一列 Block，返回一列 Chunk

目录里的文件：
- splitter.py   全部切分逻辑（分章/章内切段/组装/碎块合并都在这一个文件）

使用示例：
    from chunking import split_blocks
    chunks = split_blocks(blocks)          # blocks 来自 ingest 层
    # chunks 里每个 Chunk 都有 .content / .heading_path / .page / .chunk_index
"""
from chunking.splitter import Chunk, split_blocks

__all__ = ["Chunk", "split_blocks"]
