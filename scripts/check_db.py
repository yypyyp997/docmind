from dotenv import load_dotenv
load_dotenv()
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import get_connection

conn = get_connection()
print("走 .env 的连接成功")
conn.close()
