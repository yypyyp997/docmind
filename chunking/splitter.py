"""切分层：把解析出来的内容块，按标题结构重新组织成待入库的文本块（Chunk）。

切分思路（两步）：
- 第一步（按标题分章）：每遇到一个标题，就开启一个新章节。一个章节里的
  内容永远不会跑到别的标题下面——这样用户问"XX要点"时，检索出来的
  内容就是干净的，不会混进别的章节的内容，引用来源也能精确到章节
- 第二步（控制大小）：一个章节如果太长（超过 max_len 字），按段落切开，
  并且每段开头保留上一段结尾的一部分文字（overlap，防止上下文断掉）；
  如果某个章节的内容太少（不足 min_len 字），就并到相邻章节里，避免
  入库一堆只有一句话的碎块

已知简化（记录在案）：
- 一个章节跨多页时，page 只记录第一页（精确到每一页太复杂，先不做）
- 标题后面直接跟着的文字（还没到下一个标题之前），算作这个新章节的开头
"""
from dataclasses import dataclass, field
from ingest.base import Block

@dataclass
class Chunk:
    """入库单元：一段带"标题导航"的文本，将来直接存进向量库。

heading_path 是"章节路径"，比如"力量训练 > 深蹲要点"——它会被拼在
content 开头一起入库，这样检索时标题词也参与匹配，回答时也能说明出处。
"""

    content: str                          # = heading_path 前缀 + 章节内正文段落
    doc_name: str
    page: int | None
    heading_path: str                     # 章节导航："健身基础 > 安全要点"；无标题章节为 ""
    chunk_index: int                      # 同章节内段序号（0 起）
    extra: dict = field(default_factory=dict)


def split_blocks(
    blocks: list[Block],
    max_len: int = 500,
    overlap: int = 100,
    min_len: int = 50,
) -> list[Chunk]:
    """主入口：内容块列表 → 待入库块列表。分三步：分章 → 章内切段 → 组装。"""
    groups = _stage_scan(blocks)
    results: list[Chunk] = []
    for path, texts, doc_name, page in groups:
        segments = _stage_split_group(texts, max_len, overlap)
        chunks = _stage_assemble(path, segments, doc_name, page)
        results.extend(chunks)
    return _merge_fragments(results, min_len)


# ---------------------------------------------------------------
# 第一步：分章——把内容块按标题边界分成一个个"章节"
# ---------------------------------------------------------------
def _stage_scan(blocks: list[Block]) -> list[tuple]:
    """把内容块按标题分成章节。

    返回列表，每一项是一个章节：(章节路径, 该章节的文字列表, 文档名, 页码)。

    工作方式：从头到尾逐个看内容块。遇到标题就把之前攒的内容打包成一个
    章节（前提是攒到过东西），然后记住这个新标题（连同它的层级）；普通
    内容块就攒进当前章节。全部看完后，最后攒的那个章节也要打包（它没有
    "下一个标题"来触发打包，必须手动收尾）。

    两个容易出 bug 的地方（都处理了）：
    1. 打包后必须用"全新的空列表"继续攒内容——如果直接复用旧列表，
       旧章节里存的那份也会跟着变（Python 列表按引用共享）
    2. 切换到更高级标题时要"清掉"之前记的低级标题：比如从"## 小标题"
       跳回"# 大标题"，章节路径里的"小标题"部分要删掉
    """
    groups: list[tuple] = []              # 收集完成的章节列表
    heading_levels: dict[int, str] = {}   # 当前标题路径：{层级: 标题文字}，如 {1:"力量训练", 2:"深蹲要点"}
    current_texts: list[str] = []         # 当前章节攒到的文字
    current_doc: str | None = None        # 当前章节的文档名
    current_page: int | None = None       # 当前章节的起始页码

    for block in blocks:
        # 记一下这个章节属于哪个文档、从哪页开始（用第一个块的信息）
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

            # ---- 把之前攒的章节打包保存 ----
            # 有两种章节要保存：① 攒到过正文的；② 虽然没正文但下面挂着子章节的
            #   （比如"# 力量训练"下面全是"## 小标题"，它自己是目录，删掉的话
            #    路径溯源就断了，所以也要保存）
            prev_path = " > ".join(heading_levels[k] for k in sorted(heading_levels))
            is_ancestor = bool(prev_path) and next_path.startswith(prev_path + " > ")
            if current_texts or is_ancestor:
                groups.append((prev_path, current_texts[:], current_doc, current_page))
            current_texts = []                  # 必须换成全新列表（旧列表已被存进 groups，
                                                #  继续往里塞会把已保存的章节一起改掉）

            # ---- 更新当前标题路径 ----
            heading_levels = next_levels

            # ---- heading 块里标题之外的直属正文，作为新章节正文开头 ----
            body_lines = block.content.splitlines()[1:]
            body = "\n".join(l for l in body_lines if l.strip())
            if body:
                current_texts = [body]

            # 新章节的起始页码从标题所在页重新计
            current_page = block.page
        else:
            current_texts.append(block.content)

    # ---- 最后一个章节没有"下一个标题"来触发打包，在这里手动收尾 ----
    prev_path = " > ".join(heading_levels[k] for k in sorted(heading_levels))
    if current_texts or (prev_path and heading_levels):
        groups.append((prev_path, current_texts[:], current_doc, current_page))

    return groups


# ---------------------------------------------------------------
# 第二步：章内切段——一个章节太长时，按段落切成多段
# ---------------------------------------------------------------
def _stage_split_group(texts: list[str], max_len: int, overlap: int) -> list[str]:
    """把一个章节的文字列表切成若干段。

    max_len：每段的最大字数。overlap：下一段开头要保留上一段结尾的字数
    （这样每段都不是"凭空开始"的，上下文不会断）。
    章节总长不超 max_len 就直接整段返回，不用切。
    """
    full = "\n".join(texts).strip()
    if not full:
        return []
    if len(full) <= max_len:
        return [full]                        # 总长没超标：不用切，整章就是一段

    # 按段落拆开（去掉空行），逐段往"缓冲区"里装，装满了就结算成一段
    paras = [p.strip() for p in full.split("\n") if p.strip()]
    segments: list[str] = []              # 切好的段，最终返回它
    buf = ""                              # 当前正在装的段（缓冲区）
    for para in paras:
        # 还装得下（不超 max_len）：装进去继续
        if len(buf) + len(para) + 1 <= max_len:
            buf = f"{buf}\n{para}" if buf else para
            continue
        # 装不下了：把缓冲区里攒的结算成一段，开新段
        if buf:
            segments.append(buf)
        # 新段开头带上旧段结尾的 overlap 个字（上下文衔接）
        tail = buf[-overlap:] if len(buf) >= overlap else buf
        merged = f"{tail}\n{para}" if tail else para
        # 单个段落自己就超长的（巨长段落）：硬切成 max_len 的小片
        if len(merged) > max_len:
            for i in range(0, len(merged), max_len):
                segments.append(merged[i:i + max_len])
            buf = ""
        else:
            buf = merged
    if buf:
        segments.append(buf)              # 别忘了最后还在缓冲区里的那段
    return segments


# ---------------------------------------------------------------
# 第三步：组装——把章节路径拼到每段文字开头，做成入库块
# ---------------------------------------------------------------
def _stage_assemble(
    path: str, segments: list[str], doc_name: str | None, page: int | None
) -> list[Chunk]:
    """章节信息 + 段列表 → 入库块列表（chunk_index 是章内的第几段，从 0 数）。

    章节路径拼在每段 content 开头一起入库——检索时标题词参与匹配，
    回答时也能引用"出自《xx》的 XX 章节"。
    """
    chunks: list[Chunk] = []
    prefix = f"{path}\n" if path else ""   # 章节路径做前缀，如"力量训练 > 深蹲要点\n"
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
# 收尾：碎块合并——内容太短的入库块，并到前一个块里
# ---------------------------------------------------------------
def _merge_fragments(chunks: list[Chunk], min_len: int) -> list[Chunk]:
    """太碎的入库块并到前面的块里，避免存一堆一句话的碎块。

    规则：去掉章节路径前缀后，正文不足 min_len 字的块，整个并到前一个
    块的末尾（内容一个字不丢）；第一个块太碎时不往前并（它前面没有块），
    保留原样等下一个块来并。
    """
    if len(chunks) <= 1:
        return chunks
    merged: list[Chunk] = [chunks[0]]     # 第一个块先放进结果（它没有"前一个"可并）
    for chunk in chunks[1:]:
        prev = merged[-1]                 # 结果里最后一个块 = 可能被并入的对象
        body = chunk.content
        # 去掉章节路径前缀，量正文的真实长度
        if chunk.heading_path and body.startswith(chunk.heading_path + "\n"):
            body = body[len(chunk.heading_path) + 1:]
        if len(body) < min_len:
            # 太碎：整个并进前一个块（内容一个字不丢）
            prev.content = f"{prev.content}\n{chunk.content}"
            if prev.page is None:
                prev.page = chunk.page
            continue
        merged.append(chunk)
    return merged
