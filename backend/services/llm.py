from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from config import get_api_key, get_base_url, get_model_name, llm_configured
from openai import OpenAI

from schemas import Factor, Persona
from services.job_store import load_jobs, load_outcomes, load_sub_jobs
from services.prompt import build_generation_prompt


def _client() -> OpenAI | None:
    if not llm_configured():
        return None
    return OpenAI(api_key=get_api_key(), base_url=get_base_url())


def extract_json_array(text: str) -> Any:
    text = text.strip()
    if text.startswith("["):
        return json.loads(text)
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        return json.loads(match.group())
    raise ValueError("无法从 LLM 响应中提取 JSON 数组")


def llm_available() -> bool:
    return _client() is not None


def generate_personas_llm(
    count: int,
    factors: List[Factor],
    *,
    job_ids: Optional[List[str]] = None,
    entry_situations: Optional[List[str]] = None,
    steps: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    **_kwargs,
) -> List[Persona]:
    client = _client()
    if client is None:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY（请检查 consumer_ai_sim/.env）")

    jobs = load_jobs()
    sub_jobs = load_sub_jobs()
    outcomes = load_outcomes()
    if job_ids:
        jobs = [j for j in jobs if j.id in job_ids] or jobs

    prompt = build_generation_prompt(
        count,
        factors,
        jobs,
        sub_jobs,
        outcomes,
        job_ids=job_ids,
        entry_situations=entry_situations,
        steps=steps,
        roles=roles,
    )
    resp = client.chat.completions.create(
        model=get_model_name(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=8192,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise ValueError("LLM 返回空内容")

    raw_list = extract_json_array(content)
    return [Persona.model_validate(p) for p in raw_list]
