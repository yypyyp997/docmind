from pathlib import Path
from ingest.base import Parser,ParsingError
from ingest.docx_parser import DocxParser
from ingest.md_parser import MdParser
from ingest.pdf_parser import PdfParser
from ingest.txt_parser import TxtParser

_PARSER_DICT = {".md": MdParser, ".pdf": PdfParser, ".docx": DocxParser, ".txt": TxtParser}

def get_parser(path:str|Path)->Parser:
    p=Path(path)
    doc_type=p.suffix.lower()
    parser_cls=_PARSER_DICT.get(doc_type)
    if parser_cls is None:
        raise ParsingError(f"不支持的文档格式: '{doc_type}'（支持: .md .pdf .docx .txt）")
    return parser_cls()