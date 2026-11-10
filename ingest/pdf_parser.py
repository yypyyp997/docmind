from pathlib import Path
from ingest.base import Block,Parser,ParsingError

class PdfParser(Parser):
    def parse(self,path:str|Path)->list[Block]:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
        p= Path(path)
        if not p.exists():
            raise ParsingError(f"文件不存在:{p}")
        try:
            reader=PdfReader(str(p))
        except PdfReadError as e:
            raise ParsingError(f"PDF无法读取(损坏或加密):{p}") from e
        if reader.is_encrypted:
            raise ParsingError(f"PDF已加密:{p}")
        blocks:list[Block]=[]
        for page_no,page in enumerate(reader.pages,start=1):
            try:
                text=page.extract_text() or ""
            except Exception as e:
                blocks.append(Block(
                    content=f"第{page_no}页提取失败:{e}",
                    doc_name=p.name,
                    page=page_no,
                    kind="text",
                    extra={"extraction_failed":True}
                ))
                continue
            text=text.strip()
            if not text:
                continue
            for para_text in self._split_long_text(text,max_len=800):
                blocks.append(Block(
                    content=para_text,
                    doc_name=p.name,
                    page=page_no,
                    kind="text"
                ))
            if not blocks:
                raise ParsingError(f"未提取到任何文本（可能是扫描件/图片型 PDF，无文本层）: {p}")
            return blocks

    @staticmethod
    def _split_long_text(text:str,max_len:int=800)->list[str]:
        paras=[para.strip() for para in text.split("\n")if para.strip()]
        if not paras:
            return []
        result:list[str]=[]
        buf=""
        for para in paras:
            if len(para)>max_len:
                if buf:
                    result.append(buf)
                    buf=""
                for i in range(0,len(para),max_len):
                    result.append(para[i:i+max_len])
                continue
            if len(buf)+len(para)<=max_len:
                buf=f"{buf}\n{para}" if buf else para
            else:
                if buf:
                    result.append(buf)
                buf=para
        if buf:
            result.append(buf)
        return result