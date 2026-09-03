"""LLM 逐人生成全新人格：14 原型仅作 JTBD 结构槽，带 QC 与修复重试。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from config import get_api_key, get_base_url, get_model_name, llm_configured
from openai import OpenAI

from schemas import Factor, Persona
from services.job_store import load_jobs, load_outcomes, load_sub_jobs
from services.fallback_gen import generate_personas_fallback
from services.persona_blueprint import archetype_seed_names, build_blueprints
from services.persona_coherence import (
    fix_persona_coherence,
    validate_persona,
    validate_persona_uniqueness,
)
from services.prompt import build_repair_prompt, build_single_persona_prompt

logger = logging.getLogger(__name__)

MAX_QC_RETRIES = 3
GEN_TEMPERATURE = 0.88
REPAIR_TEMPERATURE = 0.35


def _client() -> OpenAI | None:
    if not llm_configured():
        return None
    return OpenAI(api_key=get_api_key(), base_url=get_base_url())


def extract_json_object(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("{"):
        return json.loads(text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    raise ValueError("无法从 LLM 响应中提取 JSON 对象")


def _call_llm(client: OpenAI, prompt: str, *, temperature: float, max_tokens: int = 4096) -> str:
    resp = client.chat.completions.create(
        model=get_model_name(),
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise ValueError("LLM 返回空内容")
    return content


def _qc_issues(
    persona: Persona,
    factors: List[Factor],
    *,
    used_names: set[str],
) -> List[str]:
    persona = fix_persona_coherence(persona, factors)
    issues = validate_persona(persona, factors)
    issues.extend(validate_persona_uniqueness(persona, used_names=used_names))
    return issues


def _hard_issues(issues: List[str]) -> List[str]:
    hard_markers = (
        "不匹配",
        "不应",
        "应为",
        "人口学像",
        "缺少父母",
        "不一致",
        "重复",
        "重名",
        "预设原型",
        "未知维度",
        "非法",
    )
    return [i for i in issues if any(m in i for m in hard_markers)]


def _normalize_factor_weights(persona: Persona, factors: List[Factor]) -> Persona:
    for f in factors:
        if f.id not in persona.factor_weights:
            persona.factor_weights[f.id] = 0
    return persona


def _generate_one_persona(
    client: OpenAI,
    blueprint,
    factors: List[Factor],
    jobs,
    sub_jobs,
    outcomes,
    *,
    used_names: set[str],
    banned_names: set[str],
) -> Persona:
    slot = blueprint.slot_index
    pid = blueprint.persona_id
    prompt = build_single_persona_prompt(
        blueprint,
        factors,
        jobs,
        sub_jobs,
        outcomes,
        used_names=sorted(used_names),
        banned_names=sorted(banned_names),
    )

    last_issues: List[str] = []
    persona: Persona | None = None

    for attempt in range(1, MAX_QC_RETRIES + 1):
        print(
            f"[LLM生成] {slot} {pid} · {blueprint.job_id} "
            f"第 {attempt}/{MAX_QC_RETRIES} 次…",
            flush=True,
        )
        if attempt == 1:
            content = _call_llm(client, prompt, temperature=GEN_TEMPERATURE)
            raw = extract_json_object(content)
        else:
            if persona is None:
                break
            repair_prompt = build_repair_prompt(
                persona.model_dump(),
                last_issues,
                factors,
                jobs,
                sub_jobs,
                outcomes,
                blueprint=blueprint,
            )
            content = _call_llm(
                client, repair_prompt, temperature=REPAIR_TEMPERATURE
            )
            raw = extract_json_object(content)

        raw["id"] = pid
        persona = Persona.model_validate(raw)
        persona = _normalize_factor_weights(persona, factors)
        persona = fix_persona_coherence(persona, factors)
        if "llm_generated" not in persona.evidence_refs:
            persona.evidence_refs = ["llm_generated", *persona.evidence_refs]

        issues = _qc_issues(persona, factors, used_names=used_names)
        hard = _hard_issues(issues)
        if not hard:
            print(f"[LLM生成] {pid} ✓ 质检通过", flush=True)
            return persona

        last_issues = hard
        print(
            f"[LLM生成] {pid} ✗ 质检未过：{'；'.join(hard[:3])}",
            flush=True,
        )

    raise ValueError(
        f"{pid} 在 {MAX_QC_RETRIES} 次尝试后仍未通过质检："
        + "；".join(last_issues[:5])
    )


def _fallback_one_slot(
    factors: List[Factor],
    blueprint,
    used_names: set[str],
    **kwargs,
) -> Persona:
    """单槽兜底：仍尽量换姓名，并标记为规则回退。"""
    print(f"[LLM生成] {blueprint.persona_id} ↪ 使用规则原型兜底", flush=True)
    batch = generate_personas_fallback(1, factors, job_ids=[blueprint.job_id], **kwargs)
    if not batch:
        raise ValueError(f"{blueprint.persona_id} 规则兜底也失败")
    p = batch[0]
    p.id = blueprint.persona_id
    if p.name in used_names:
        p.name = f"{p.name}·{blueprint.slot_index}"
    p.evidence_refs = ["archetype_fallback", *p.evidence_refs]
    return fix_persona_coherence(p, factors)


def generate_personas_llm(
    count: int,
    factors: List[Factor],
    *,
    job_ids: Optional[List[str]] = None,
    entry_situations: Optional[List[str]] = None,
    entry_themes: Optional[List[str]] = None,
    steps: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    allow_archetype_fallback: bool = True,
    **_kwargs,
) -> List[Persona]:
    """
    逐人生成 + QC。
    - 14 原型 → 结构蓝图（Job/角色/分群）
    - LLM → 全新姓名/职业/家庭/心智文案
    - 质检不过 → 带问题清单修复重试（最多 MAX_QC_RETRIES 次）
    """
    client = _client()
    if client is None:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY（请检查 .env）")

    jobs = load_jobs()
    sub_jobs = load_sub_jobs()
    outcomes = load_outcomes()
    if job_ids:
        jobs = [j for j in jobs if j.id in job_ids] or jobs

    blueprints = build_blueprints(
        count, job_ids=job_ids, entry_situations=entry_situations
    )
    banned_names = archetype_seed_names()
    used_names: set[str] = set()
    personas: List[Persona] = []
    fallback_count = 0

    print(
        f"[LLM生成] 开始逐人生成 {count} 人（结构来自 JTBD 槽位，故事由 LLM 创造）…",
        flush=True,
    )

    fb_kwargs = {
        "entry_situations": entry_situations,
        "entry_themes": entry_themes,
        "steps": steps,
        "roles": roles,
    }

    for bp in blueprints:
        try:
            persona = _generate_one_persona(
                client,
                bp,
                factors,
                jobs,
                sub_jobs,
                outcomes,
                used_names=used_names,
                banned_names=banned_names,
            )
        except Exception as exc:
            logger.warning("LLM slot %s failed: %s", bp.persona_id, exc)
            if not allow_archetype_fallback:
                raise
            persona = _fallback_one_slot(factors, bp, used_names, **fb_kwargs)
            fallback_count += 1

        used_names.add(persona.name)
        personas.append(persona)

    llm_count = count - fallback_count
    print(
        f"[LLM生成] 完成：{llm_count} 人 LLM 原创"
        + (f"，{fallback_count} 人规则兜底" if fallback_count else ""),
        flush=True,
    )
    return personas
