"""LLM 逐人生成全新人格：14 原型仅作 JTBD 结构槽，带 QC 与修复重试。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from config import get_api_key, get_base_url, get_model_name, llm_configured
from openai import OpenAI

from schemas import Factor, Persona
from services.job_store import load_jobs, load_outcomes, load_sub_jobs, resolve_step_name
from services.fallback_gen import generate_personas_fallback
from services.persona_blueprint import archetype_seed_names, build_blueprints
from services.persona_coherence import (
    fix_persona_coherence,
    validate_against_blueprint,
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


def _normalize_current_step(persona: Persona) -> Persona:
    """LLM 常把 current_step 填成字母 id，统一成中文步骤名。"""
    persona.jtbd.current_step = resolve_step_name(
        persona.jtbd.current_step, persona.jtbd.job_id
    )
    return persona


def _qc_issues(
    persona: Persona,
    factors: List[Factor],
    *,
    used_names: set[str],
    blueprint=None,
) -> List[str]:
    persona = fix_persona_coherence(persona, factors)
    persona = _normalize_current_step(persona)
    issues = validate_persona(persona, factors)
    issues.extend(validate_persona_uniqueness(persona, used_names=used_names))
    issues.extend(validate_against_blueprint(persona, blueprint))
    step = (persona.jtbd.current_step or "").strip()
    if step and len(step) <= 2 and step.isalpha():
        issues.append(f"current_step「{step}」仍是字母编码，须改为中文步骤名")
    names = {s.name for s in load_sub_jobs()}
    if step and step not in names and resolve_step_name(step, persona.jtbd.job_id) == step:
        if len(step) <= 4:
            issues.append(f"current_step「{step}」不在子任务词典中")
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
        "字母编码",
        "不在子任务词典",
        "蓝图",
        "缺少室友",
    )
    return [i for i in issues if any(m in i for m in hard_markers)]


def _normalize_factor_weights(persona: Persona, factors: List[Factor]) -> Persona:
    """补齐缺失权重，并清洗 LLM 偶发的非法键（如「04」而非「A4」/「B4」）。"""
    valid = {f.id for f in factors}
    cleaned: dict[str, int] = {}
    for code, weight in (persona.factor_weights or {}).items():
        key = str(code).strip().upper()
        if key in valid:
            cleaned[key] = int(weight)
            continue
        # 「04」「4」→ 优先映射到主导维度里出现的 A4/B4，否则丢弃
        m = re.fullmatch(r"0*([1-9]|1[01])", key)
        if m:
            n = m.group(1)
            candidates = [f"A{n}", f"B{n}"]
            dom = {d.code for d in (persona.dominant_features or [])}
            hit = next((c for c in candidates if c in dom and c in valid), None)
            if not hit:
                hit = next((c for c in candidates if c in valid), None)
            if hit:
                cleaned[hit] = max(cleaned.get(hit, 0), int(weight))
                continue
        # 完全无法识别的键直接丢弃，避免整批生成失败
    for f in factors:
        if f.id not in cleaned:
            cleaned[f.id] = 0
    persona.factor_weights = cleaned

    # 主导维度非法编码一并丢掉
    persona.dominant_features = [
        d for d in (persona.dominant_features or []) if d.code in valid
    ]
    return persona


def _enforce_blueprint_structure(persona: Persona, blueprint, factors: List[Factor]) -> Persona:
    """通过 QC 后仍强制对齐 Job/分群/角色骨架，杜绝「室友→J5」类漂移入库。"""
    from services.job_store import get_job
    from services.persona_coherence import _replace_outcomes

    if blueprint is None:
        return fix_persona_coherence(persona, factors)

    bp_job = getattr(blueprint, "job_id", "") or ""
    bp_seg = getattr(blueprint, "segment", "") or ""
    bp_role = getattr(blueprint, "role_hint", "") or ""
    bp_subject = getattr(blueprint, "subject_hint", "") or ""
    bp_owner = getattr(blueprint, "job_owner", "") or ""
    bp_outcomes = list(getattr(blueprint, "desired_outcome_ids", None) or [])

    if bp_job and persona.jtbd.job_id != bp_job:
        persona.jtbd.job_id = bp_job
        job = get_job(bp_job)
        if job:
            persona.jtbd.core_job = job.name
    if bp_owner:
        persona.jtbd.job_owner = bp_owner
    if bp_seg:
        persona.segment = bp_seg
    if "室友" in bp_role:
        persona.role = bp_role
        if bp_subject:
            persona.subject = bp_subject
        if not any(x in (persona.family or "") for x in ("室友", "合租", "宿舍")):
            persona.family = "合租，室友打鼾严重影响夜间睡眠"
    if bp_outcomes:
        existing = {d.id: d for d in persona.jtbd.desired_outcomes}
        # 丢掉蓝图未授权且与角色冲突的 Outcome（如室友身上的 O4）
        allowed = set(bp_outcomes)
        if "室友" in bp_role:
            allowed.discard("O4")
        kept = [existing[oid] for oid in bp_outcomes if oid in existing]
        if len(kept) < 2:
            _replace_outcomes(persona, bp_job)
        else:
            persona.jtbd.desired_outcomes = kept
            # 若仍含冲突 id，再滤一次
            persona.jtbd.desired_outcomes = [
                d for d in persona.jtbd.desired_outcomes if d.id in allowed or d.id in bp_outcomes
            ]
            if "室友" in bp_role:
                persona.jtbd.desired_outcomes = [
                    d for d in persona.jtbd.desired_outcomes if d.id != "O4"
                ]
                if not persona.jtbd.desired_outcomes:
                    _replace_outcomes(persona, bp_job or "J1")

    return fix_persona_coherence(persona, factors)


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
        persona = _normalize_current_step(persona)
        persona = fix_persona_coherence(persona, factors)
        if "llm_generated" not in persona.evidence_refs:
            persona.evidence_refs = ["llm_generated", *persona.evidence_refs]

        issues = _qc_issues(
            persona, factors, used_names=used_names, blueprint=blueprint
        )
        hard = _hard_issues(issues)
        if not hard:
            # 结构字段最终对齐蓝图，防止 QC 软过但仍漂
            persona = _enforce_blueprint_structure(persona, blueprint, factors)
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
