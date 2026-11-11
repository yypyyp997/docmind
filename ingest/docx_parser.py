from pathlib import Path
from ingest.base import Parser,ParsingError,Block
from docx import Document

class DocxParser(Parser):
    def parse(self,path:str|Path)->list[Block]:
        p=Path(path)
        if not p.exists():
            raise ParsingError(f"文件不存在:{p}")
        try:
            doc=Document(str(p))
        except Exception as e:
            raise ParsingError(f"DOCX无法读取(可能已损坏或不是有效的docx):{p}")from e
        blocks:list[Block]=[]
        current:Block|None=None
        for para in doc.paragraphs:
            text=para.text.strip()
            if not text:
                continue
            style_name = para.style.name
            if style_name.startswith(("Heading","标题"))or style_name=="Title":
                level=int(style_name.split()[-1]) if style_name.split()[-1].isdigit() else 1
                current=Block(
                    content=text,
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
                current.content=(current.content+"\n"+text).strip()
        return blocks