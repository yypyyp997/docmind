"""存储层：PostgreSQL 连接管理 + 建表。

设计：
- 连接参数从 .env 读（DATABASE_URL），缺省回退本地默认地址——CI 没有 PG 也不炸
- get_connection() 每次返回独立连接（简单可靠；连接池等上量后再优化——记录在案）
- init_tables() 幂等：CREATE TABLE IF NOT EXISTS，跑多少遍表结构都一样
"""
import os

import psycopg
from dotenv import load_dotenv

from utils.exceptions import StorageError

load_dotenv()
# DATABASE_URL 从环境变量读；开发环境缺省值指向本地 compose 的 PG
DEFAULT_URL = "postgresql://docmind:***@localhost:15432/docmind"

def get_connection():
    """返回一个新的独立数据库连接。用完由调用方 close（配合 with 使用）。"""
    url = os.getenv("DATABASE_URL", DEFAULT_URL)
    try:
        return psycopg.connect(url)
    except psycopg.OperationalError as e:
        raise StorageError(f"数据库连接失败（服务没起？地址密码对吗？）: {e}") from e

def init_tables():
    """建表（幂等）。表结构：
    documents: 文档级元数据，一个文档对应一次 ingest
    chunks:    入库的文本块，通过外键挂在文档下，文档删除时级联删除
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id           SERIAL PRIMARY KEY,
                    doc_name     TEXT UNIQUE NOT NULL,
                    total_chunks INT NOT NULL DEFAULT 0,
                    ingested_at  TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id           SERIAL PRIMARY KEY,
                    doc_id       INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index  INT NOT NULL,
                    heading_path TEXT NOT NULL DEFAULT '',
                    content      TEXT NOT NULL,
                    page         INT,
                    extra        JSONB DEFAULT '{}'
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id)")
        conn.commit()
