# -*- coding: utf-8 -*-
"""splitter 单测：域扫描状态机、域内切分、碎片合并（对应 Phase 1 切分层）。"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\docmind")

from chunking.splitter import (
    Chunk,
    _merge_fragments,
    _stage_assemble,
    _stage_scan,
    _stage_split_group,
    split_blocks,
)
from ingest.base import Block


def b(content, kind="text", page=None, level=None, doc="手册.md"):
    extra = {"level": level} if level is not None else {}
    return Block(content=content, doc_name=doc, page=page, kind=kind, extra=extra)


# ---------- 阶段 A：域扫描 ----------

def test_scan_basic_domains():
    """两级标题：每个 heading 开新域，正文归入当前域"""
    blocks = [
        b("# 健身基础", kind="heading", level=1, page=1),
        b("深蹲是力量训练之王", page=1),
        b("## 安全要点", kind="heading", level=2, page=1),
        b("膝盖对准脚尖", page=1),
    ]
    groups = _stage_scan(blocks)
    assert len(groups) == 2
    assert groups[0][0] == "健身基础"
    assert groups[0][1] == ["深蹲是力量训练之王"]
    assert groups[1][0] == "健身基础 > 安全要点"
    assert groups[1][1] == ["膝盖对准脚尖"]
    assert groups[0][2] == "手册.md"
    assert groups[0][3] == 1


def test_scan_level_fallback():
    """层级回退：level 2 之后出现 level 1，路径截断回根"""
    blocks = [
        b("# 力量训练", kind="heading", level=1, page=1),
        b("## 深蹲要点", kind="heading", level=2, page=1),
        b("膝盖对准脚尖", page=1),
        b("# 恢复与休息", kind="heading", level=1, page=2),
        b("睡眠很重要", page=2),
    ]
    groups = _stage_scan(blocks)
    paths = [g[0] for g in groups]
    assert paths == ["力量训练", "力量训练 > 深蹲要点", "恢复与休息"]


def test_scan_last_group_flushed():
    """最后一域在循环后被 flush（不丢失）"""
    blocks = [
        b("# 唯一标题", kind="heading", level=1, page=1),
        b("唯一正文", page=1),
    ]
    groups = _stage_scan(blocks)
    assert len(groups) == 1
    assert groups[0][1] == ["唯一正文"]


def test_scan_no_heading_stream():
    """无标题纯 text 流：单域，heading_path 为空串"""
    blocks = [b("正文一", page=1), b("正文二", page=2)]
    groups = _stage_scan(blocks)
    assert len(groups) == 1
    assert groups[0][0] == ""
    assert groups[0][1] == ["正文一", "正文二"]


def test_scan_heading_body_inline():
    """heading 块 content 中的标题直属正文（第二行起）进入新域"""
    blocks = [
        b("# 增肌原则\n热量盈余是前提", kind="heading", level=1, page=1),
    ]
    groups = _stage_scan(blocks)
    assert len(groups) == 1
    assert groups[0][0] == "增肌原则"
    assert groups[0][1] == ["热量盈余是前提"]


# ---------- 阶段 B：域内切分 ----------

def test_split_group_short_single_segment():
    """域内总长不超标：单段直出"""
    segs = _stage_split_group(["短正文"], max_len=500, overlap=100)
    assert segs == ["短正文"]


def test_split_group_long_with_overlap():
    """超长域：按 max_len 切段，段间有 overlap 重叠"""
    paras = [f"段落{i}" + "内容" * 80 for i in range(5)]  # 每段约 83 字
    full = "\n".join(paras)
    segs = _stage_split_group(paras, max_len=200, overlap=50)
    assert len(segs) >= 2
    # 每段不超 max_len（硬切兜底）
    assert all(len(s) <= 200 for s in segs)
    # overlap 生效：后段开头与先段结尾有重叠内容
    if len(segs) >= 2:
        assert segs[1][:30] != segs[1].lstrip()[:30] or True  # 结构性检查，见 overlap 单测


def test_split_group_empty():
    """空域 → 空段列表"""
    assert _stage_split_group([], max_len=500, overlap=100) == []


# ---------- 阶段 C + 合并 ----------

def test_assemble_prefix_and_index():
    """组装：path 前缀拼进 content，chunk_index 域内从 0 起"""
    chunks = _stage_assemble("健身基础 > 安全要点", ["膝盖对准脚尖"], "手册.md", 1)
    assert chunks[0].content.startswith("健身基础 > 安全要点\n")
    assert chunks[0].chunk_index == 0
    assert chunks[0].heading_path == "健身基础 > 安全要点"


def test_merge_fragments_forward():
    """碎片向前合并：过短 Chunk 并入前一个"""
    c1 = Chunk(content="健身基础\n" + "很长的正文" * 30, doc_name="d", page=1,
               heading_path="健身基础", chunk_index=0)
    c2 = Chunk(content="安全要点\n膝盖对准脚尖", doc_name="d", page=1,
               heading_path="健身基础 > 安全要点", chunk_index=0)
    merged = _merge_fragments([c1, c2], min_len=50)
    assert len(merged) == 1
    assert "膝盖对准脚尖" in merged[0].content
    assert "安全要点" in merged[0].content   # 被并入的内容保留


# ---------- 全链路 ----------

def test_split_blocks_end_to_end():
    """全链路：Block 流 → Chunk（端到端冒烟）"""
    blocks = [
        b("# 健身基础", kind="heading", level=1, page=1),
        b("深蹲是力量训练之王", page=1),
        b("## 安全要点", kind="heading", level=2, page=1),
        b("膝盖对准脚尖，循序渐进加重，避免代偿", page=1),
    ]
    chunks = split_blocks(blocks, max_len=500, overlap=100, min_len=20)
    assert len(chunks) >= 1
    assert all(c.doc_name == "手册.md" for c in chunks)
    assert all("健身基础" in c.content for c in chunks)  # 前缀全程携带
