# -*- coding: utf-8 -*-
"""DocMind 配置中心：.env 驱动的统一配置（pydantic-settings，类型校验）。

用法：各模块从本文件导入配置对象，不再直接散布 os.getenv：
    from config.settings import settings
    url = settings.DATABASE_URL

设计：
- Settings 类：字段声明即配置（类型校验 + 缺省值 + .env 自动加载）
- 环境变量优先级：真实环境变量 > .env 文件 > 字段缺省值（pydantic-settings 默认行为）
- 密钥类字段建议升级 SecretStr：日志打印时自动掩码（当前 str 起步，演进项）
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """DocMind 全局配置。字段名 = 环境变量名。"""

    # ---- 模型服务 ----
    DASHSCOPE_API_KEY: str = ""

    # ---- 数据库 ----
    DATABASE_URL: str = "postgresql://docmind:***@localhost:15432/docmind"

    # ---- Redis（Phase 5）----
    REDIS_URL: str = ""                      # 空 = 降级模式（缓存层自动回退）

    # ---- API 服务 ----
    API_KEY: str = ""                        # 空 = 开发模式（API 跳过认证）
    DOCS_BASE_DIR: str = str(Path(__file__).resolve().parent.parent / "docs" / "official")

    # ---- 检索参数 ----
    SEARCH_TOP_K: int = 3
    RECALL_K: int = 20

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",                       # .env 里多余的字段不报错
    )


settings = Settings()
