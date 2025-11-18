from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    twitter_bearer_token: str | None = os.getenv("TWITTER_BEARER_TOKEN")
    # 是否使用全量历史搜索（需要 Academic 权限）
    use_search_all: bool = os.getenv("USE_SEARCH_ALL", "true").lower() == "true"
    # 速率限制相关（默认适中，便于演示；可在界面修改）
    rate_limit_max_retries: int = int(os.getenv("RATE_LIMIT_MAX_RETRIES", "5"))
    rate_limit_base_delay_seconds: float = float(os.getenv("RATE_LIMIT_BASE_DELAY_SECONDS", "1.5"))
    rate_limit_max_delay_seconds: float = float(os.getenv("RATE_LIMIT_MAX_DELAY_SECONDS", "60"))
    requests_per_minute: int = int(os.getenv("REQUESTS_PER_MINUTE", "30"))  # 简单节流：约每2秒1次


def get_settings() -> Settings:
    return Settings()


