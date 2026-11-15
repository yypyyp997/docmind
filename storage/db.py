"""存储层：PostgreSQL 连接管理 + 建表。

设计：
- 连接参数从 .env 读（DATABASE_URL），缺省回退本地默认地址——CI 没有 PG 也不炸
- get_connection() 每次返回独立连接（简单可靠；连接池等上量后再优化——记录在案）
- init_tables() 幂等：CREATE TABLE IF NOT EXISTS，跑多少遍表结构都一样
"""
import psycopg

from config.settings import settings
from utils.exceptions import StorageError


def get_connection():
    """返回一个新的独立数据库连接。用完由调用方 close（配合 with 使用）。

    连接串统一从 config.settings 读取（.env 驱动，配置中心唯一来源）。
    """
    try:
        return psycopg.connect(settings.DATABASE_URL)
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
                     id SERIAL             PRIMARY KEY,
                     doc_name TEXT         UNIQUE NOT NULL,
                     total_chunks          INT NOT NULL DEFAULT 0,
                     content_hash          TEXT,
                     ingested_at           TIMESTAMP DEFAULT NOW()
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
                    extra        JSONB DEFAULT '{}',
                    embedding    vector(1024)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id)")
            cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT")
            cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(1024)")
        conn.commit()
