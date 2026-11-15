"""批量入库：遍历指定目录，全部文档走解析→切分→入库链路。

用法：python scripts/ingest_docs.py [目录]
缺省目录：docs/official/fastapi_docs_cn
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from ingest.factory import get_parser
from chunking.splitter import split_blocks
from storage.document_store import (
    compute_hash,
    save_document,
)
from storage.db import init_tables
init_tables()

def main(base_dir: str):
    base = Path(base_dir)
    md_files = sorted(base.rglob("*.md"))
    print(f"发现 {len(md_files)} 个 md 文件，开始入库...")
    ok,fail,skipped= 0,0,0
    for i, path in enumerate(md_files, 1):
        try:
            rel_name = str(path.relative_to(base))
            blocks = get_parser(str(path)).parse(str(path))
            file_hash = compute_hash(path.read_text(encoding="utf-8"))
            chunks = split_blocks(blocks)
            saved = save_document(rel_name, chunks, content_hash=file_hash)
            if saved == 0:
                skipped += 1
                print(f"  [跳过] {path.name}（内容未变）")
                continue
            ok += 1
            if i % 20 == 0:
                print(f"  进度 {i}/{len(md_files)}")
        except Exception as e:
            fail += 1
            print(f"  [失败] {path.name}: {type(e).__name__}: {str(e)[:80]}")
    print(f"完成: 成功 {ok}，跳过 {skipped}，失败 {fail}")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else r"D:\docmind\docs\official\fastapi_docs_cn"
    main(base)
