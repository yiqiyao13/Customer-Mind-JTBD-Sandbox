"""统一加载 DeepSeek 配置：优先本目录 .env，否则复用 consumer_ai_sim/.env"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
LEGACY_ENV = PROJECT_ROOT.parent / "consumer_ai_sim" / ".env"
LOCAL_ENV = PROJECT_ROOT / ".env"


def load_env() -> Path | None:
    """加载环境变量，返回实际使用的 .env 路径（若有）。"""
    if LOCAL_ENV.exists():
        load_dotenv(LOCAL_ENV, override=False)
    if LEGACY_ENV.exists():
        load_dotenv(LEGACY_ENV, override=False)
    return LOCAL_ENV if LOCAL_ENV.exists() else (LEGACY_ENV if LEGACY_ENV.exists() else None)


def get_api_key() -> str:
    load_env()
    return os.getenv("DEEPSEEK_API_KEY", "")


def get_base_url() -> str:
    load_env()
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def get_model_name() -> str:
    load_env()
    raw = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash")
    return raw.split("/", 1)[-1]


def llm_configured() -> bool:
    key = get_api_key()
    return bool(key) and not key.startswith("sk-your")
