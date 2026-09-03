"""LLM 入口：逐人生成 + QC（见 llm_persona_gen）。"""
from __future__ import annotations

import json
import re
from typing import Any

from config import get_api_key, get_base_url, llm_configured
from openai import OpenAI

from services.llm_persona_gen import extract_json_object, generate_personas_llm

__all__ = [
    "extract_json_array",
    "extract_json_object",
    "generate_personas_llm",
    "llm_available",
]


def _client() -> OpenAI | None:
    if not llm_configured():
        return None
    return OpenAI(api_key=get_api_key(), base_url=get_base_url())


def llm_available() -> bool:
    return _client() is not None


def extract_json_array(text: str) -> Any:
    text = text.strip()
    if text.startswith("["):
        return json.loads(text)
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        return json.loads(match.group())
    raise ValueError("无法从 LLM 响应中提取 JSON 数组")
