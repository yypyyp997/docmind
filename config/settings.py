# -*- coding: utf-8 -*-
"""DocMind 配置中心：.env 驱动（pydantic-settings），占位符默认值 + env_file 加载。

设计原则：
- 占位符默认值没问题——问题从来是「.env 是否被加载」
- model_config 的 env_file 是生命线：没有它 pydantic-settings 不读 .env，
  全部字段回退默认值（占位符密码 → 认证失败连环坑的真正根因）
- DASHSCOPE_API_KEY 用 SecretStr：日志打印自动掩码；
  模块取真实值必须 .get_secret_value()（str() 会拿到掩码）
- 双库支持：DATABASE_URL（开发）+ TEST_DATABASE_URL（测试），ENV 切换
- 全项目配置唯一来源：任何模块禁止私自 os.getenv / load_dotenv
"""
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """DocMind 全局配置。字段名 = 环境变量名 = .env 的键名。"""

    # ---- 模型服务（外部密钥）----
    DASHSCOPE_API_KEY: SecretStr = SecretStr("")       # .env 里有值则覆盖

    # ---- 数据库（占位符默认值：.env 加载后必被覆盖）----
    DATABASE_URL: str = "postgresql://docmind:***@localhost:15432/docmind"
    TEST_DATABASE_URL: str = "postgresql://docmind:***@localhost:15432/docmind_test"
    ENV: str = "dev"                         # "dev" = 开发库 / "test" = 测试库

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:16379/0"

    # ---- API 服务 ----
    API_KEY: SecretStr = SecretStr("")       # 空 = 开发模式（API 跳过认证）
    DOCS_BASE_DIR: str = str(Path(__file__).resolve().parent.parent / "docs" / "official")

    # ---- 日志 ----
    LOG_LEVEL: str = "INFO"                  # DEBUG / INFO / WARNING / ERROR
    LOG_FORMAT: str = "console"              # console = 人类可读 / json = 结构化（生产）

    # ---- 检索参数 ----
    SEARCH_TOP_K: int = 3
    RECALL_K: int = 20

    @field_validator("DASHSCOPE_API_KEY", "API_KEY", mode="before")
    @classmethod
    def _strip_secret_whitespace(cls, v):
        """剥离密钥首尾空白——CI Secret/手工粘贴常带行尾换行，
        带换行的 key 放不进 HTTP 头（requests 抛 InvalidHeader）。"""
        return v.strip() if isinstance(v, str) else v

    @property
    def ACTIVE_DATABASE_URL(self) -> str:
        """当前生效的连接串：ENV 决定开发库还是测试库。"""
        return self.TEST_DATABASE_URL if self.ENV == "test" else self.DATABASE_URL

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
