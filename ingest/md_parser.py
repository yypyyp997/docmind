from pathlib import Path
from ingest.base import Block,Parser,ParsingError

class MdParser(Parser):
    """Markdown解析器：实现Parser协议。无状态，用完即弃。"""
    def parse(self,path:str|Path)->list[Block]:
        p=Path(path)
        if not p.exists():
            raise ParsingError(f"文件不存在:{p}")
        try:
            text=p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ParsingError(f"编码错误(需要UTF-8):{p}")from e
        blocks:list[Block]=[]
        current:Block|None=None
        for line in text.splitlines():
            stripped=line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                level=len(stripped)-len(stripped.lstrip("#"))
                current=Block(
                    content=stripped,
                    doc_name=p.name,
                    page=None,
                    kind="heading",
                    extra={"level":level}
                )
                blocks.append(current)
            else:
                if current is None:
                    current=Block(
                        content="",
                        doc_name=p.name,
                        page=None,
                        kind="text"
                    )
                    blocks.append(current)
                current.content=(current.content+"\n"+line).strip()
        return blocks