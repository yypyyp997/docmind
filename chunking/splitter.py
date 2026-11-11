# -*- coding: utf-8 -*-
"""切分层：结构感知切分（Block 流 → Chunk 列表）。

双层规则（Phase 1 设计定稿）：
- 第一层（结构边界）：heading 块定义语义域，heading_path 为域的导航地址；
  域内正文永不跨标题——检索命中不串味，溯源精确到章节
- 第二层（尺寸控制）：域内超过 max_len 时按段落切 + overlap 回退；
  碎片 Chunk（< min_len）向前合并

已知简化（记录在案）：
- 跨页域的 page 取首 Block（牺牲精页度换实现简单）
- heading 块 content 中的标题行之外的直属正文，并入新域正文开头
"""
from dataclasses import dataclass, field

from ingest.base import Block


@dataclass
class Chunk:
    """入库单元：heading_path 做前缀的定尺寸语义块。"""

    content: str                          # = heading_path 前缀 + 域内正文段落
    doc_name: str
    page: int | None
    heading_path: str                     # 域导航："健身基础 > 安全要点"；无标题域为 ""
    chunk_index: int                      # 同域内段序号（0 起）
    extra: dict = field(default_factory=dict)


def split_blocks(
    blocks: list[Block],
    max_len: int = 500,
    overlap: int = 100,
    min_len: int = 50,
) -> list[Chunk]:
    """主入口：Block 流 → Chunk 列表（三阶段：扫描 → 域内切 → 组装）。"""
    groups = _stage_scan(blocks)
    results: list[Chunk] = []
    for path, texts, doc_name, page in groups:
        segments = _stage_split_group(texts, max_len, overlap)
        chunks = _stage_assemble(path, segments, doc_name, page)
        results.extend(chunks)
    return _merge_fragments(results, min_len)


# ---------------------------------------------------------------
# 阶段 A：域扫描——把 Block 流按 heading 边界切成「语义域」
# ---------------------------------------------------------------
def _stage_scan(blocks: list[Block]) -> list[tuple]:
    """一次遍历，产出 (heading_path, texts, doc_name, page) 组列表。

    状态机两个状态：heading_levels（层级→标题文本的游标）、current_texts（当前域正文）。
    flush 时机：遇到新 heading 时（先打包旧域）、全部遍历结束后（最后一域）。
    注意：flush 后 current_texts 必须重新赋值为新列表（切断引用），这是引用共享陷阱的高发处。
    """
    groups: list[tuple] = []
    heading_levels: dict[int, str] = {}
    current_texts: list[str] = []
    current_doc: str | None = None
    current_page: int | None = None

    for block in blocks:
        if current_doc is None:
            current_doc = block.doc_name
        if current_page is None and block.page is not None:
            current_page = block.page

        if block.kind == "heading":
            # ---- 先算出新 heading 的完整 path（用旧游标 + 新标题）----
            title = block.content.splitlines()[0].lstrip("#").strip()
            level = block.extra.get("level", 1)
            next_levels = dict(heading_levels)
            next_levels[level] = title
            next_levels = {k: v for k, v in next_levels.items() if k <= level}
            next_path = " > ".join(next_levels[k] for k in sorted(next_levels))

            # ---- flush 旧域 ----
            # 保留条件：旧域有正文；或旧 path 是新 path 的祖先（目录节点：
            # 子域内容全在后面，丢掉会破坏层级溯源与导航）
            prev_path = " > ".join(heading_levels[k] for k in sorted(heading_levels))
            is_ancestor = bool(prev_path) and next_path.startswith(prev_path + " > ")
            if current_texts or is_ancestor:
                groups.append((prev_path, current_texts[:], current_doc, current_page))
            current_texts = []                  # 新列表！切断引用共享

            # ---- 更新层级游标 ----
            heading_levels = next_levels

            # ---- heading 块里标题之外的直属正文，作为新域正文开头 ----
            body_lines = block.content.splitlines()[1:]
            body = "\n".join(l for l in body_lines if l.strip())
            if body:
                current_texts = [body]

            # 新域重置页码起点（heading 所在页）
            current_page = block.page
        else:
            current_texts.append(block.content)

    # ---- flush 最后一个域（for 循环没有触发点，必须显式收尾）----
    prev_path = " > ".join(heading_levels[k] for k in sorted(heading_levels))
    if current_texts or (prev_path and heading_levels):
        groups.append((prev_path, current_texts[:], current_doc, current_page))

    return groups


# ---------------------------------------------------------------
# 阶段 B：域内切分——段落累积，超长切段，overlap 回退
# ---------------------------------------------------------------
def _stage_split_group(texts: list[str], max_len: int, overlap: int) -> list[str]:
    """域内文本列表 → 段列表。段落边界优先，段尾保留 overlap 字符给下一段开头。"""
    full = "\n".join(texts).strip()
    if not full:
        return []
    if len(full) <= max_len:
        return [full]                        # 域内总长不超标：单段直出

    paras = [p.strip() for p in full.split("\n") if p.strip()]
    segments: list[str] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 1 <= max_len:
            buf = f"{buf}\n{para}" if buf else para
            continue
        # 装不下了：结算当前 buf，开启新 buf（带 overlap 回退）
        if buf:
            segments.append(buf)
        tail = buf[-overlap:] if len(buf) >= overlap else buf
        merged = f"{tail}\n{para}" if tail else para
        # merge 后仍超长（单段巨长）：硬切
        if len(merged) > max_len:
            for i in range(0, len(merged), max_len):
                segments.append(merged[i:i + max_len])
            buf = ""
        else:
            buf = merged
    if buf:
        segments.append(buf)
    return segments


# ---------------------------------------------------------------
# 阶段 C：组装——路径做前缀，建 Chunk
# ---------------------------------------------------------------
def _stage_assemble(
    path: str, segments: list[str], doc_name: str | None, page: int | None
) -> list[Chunk]:
    """域信息 + 段列表 → Chunk 列表（chunk_index 域内从 0 起）。"""
    chunks: list[Chunk] = []
    prefix = f"{path}\n" if path else ""
    for idx, seg in enumerate(segments):
        chunks.append(Chunk(
            content=f"{prefix}{seg}",
            doc_name=doc_name or "",
            page=page,
            heading_path=path,
            chunk_index=idx,
            extra={"heading_levels": path.split(" > ") if path else []},
        ))
    return chunks


# ---------------------------------------------------------------
# 后处理：碎片合并——content 不足 min_len 的 Chunk 向前并入相邻块
# ---------------------------------------------------------------
def _merge_fragments(chunks: list[Chunk], min_len: int) -> list[Chunk]:
    """碎片合并：正文过短的 Chunk 向前并入，避免入库碎片。

    合并规则：剥掉前缀后的正文长度 < min_len 时，整个 content 追加到
    前一个 Chunk 末尾；首个 Chunk 的碎片向后并（由遍历顺序天然处理：
    第一个 Chunk 不参与向前并，作为merged起点）。
    """
    if len(chunks) <= 1:
        return chunks
    merged: list[Chunk] = [chunks[0]]
    for chunk in chunks[1:]:
        prev = merged[-1]
        body = chunk.content
        if chunk.heading_path and body.startswith(chunk.heading_path + "\n"):
            body = body[len(chunk.heading_path) + 1:]
        if len(body) < min_len:
            prev.content = f"{prev.content}\n{chunk.content}"
            if prev.page is None:
                prev.page = chunk.page
            continue
        merged.append(chunk)
    return merged
