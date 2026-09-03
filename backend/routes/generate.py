from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas import GenerateRequest, Persona
from services.factor_store import get_enabled_factors
from services.fallback_gen import generate_personas_fallback
from services.job_store import load_jobs, load_outcomes
from services.llm import generate_personas_llm, llm_available
from services.memory import reset_evolution
from services.persona_coherence import (
    assert_personas_coherent,
    fix_persona_coherence,
    validate_persona,
)
from services.persona_store import set_personas
from services.simulate import ENTRY_THEME_TO_JOBS

router = APIRouter(prefix="/api", tags=["generate"])


def _validate_personas(personas: list[Persona], factors) -> list[Persona]:
    valid_ids = {f.id for f in factors}
    valid_jobs = {j.id for j in load_jobs()}
    valid_outcomes = {o.id for o in load_outcomes()}
    cleaned: list[Persona] = []
    for p in personas:
        for d in p.dominant_features:
            if d.code not in valid_ids:
                raise ValueError(f"心智 {p.id} 含非法维度编码 {d.code}")
        for code in p.factor_weights:
            if code not in valid_ids:
                raise ValueError(f"心智 {p.id} factor_weights 含非法编码 {code}")
        for f in factors:
            if f.id not in p.factor_weights:
                p.factor_weights[f.id] = 0
        p = fix_persona_coherence(p, factors)
        if p.jtbd.job_id and p.jtbd.job_id not in valid_jobs:
            raise ValueError(f"心智 {p.id} job_id {p.jtbd.job_id} 不在 jobs 内")
        for do in p.jtbd.desired_outcomes:
            if do.id not in valid_outcomes:
                raise ValueError(f"心智 {p.id} desired_outcome {do.id} 非法")
        cleaned.append(p)

    # 姓名唯一
    names = [p.name for p in cleaned]
    if len(names) != len(set(names)):
        dup = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"生成结果姓名重复：{dup}")

    assert_personas_coherent(cleaned, factors)
    return cleaned


@router.post("/generate", response_model=list[Persona])
def generate_personas(req: GenerateRequest):
    factors = get_enabled_factors()
    if not factors:
        raise HTTPException(status_code=400, detail="无启用维度，无法生成")

    use_llm = req.use_llm if req.use_llm is not None else llm_available()
    opts = req.options or {}
    entry_themes = opts.get("entry_themes") or []
    job_ids = list(req.job_ids or opts.get("job_ids") or [])
    for theme in entry_themes:
        job_ids.extend(ENTRY_THEME_TO_JOBS.get(theme, []))
    job_ids = list(dict.fromkeys(job_ids)) or None

    kwargs = {
        "job_ids": job_ids,
        "entry_situations": req.entry_situations or opts.get("entry_situations"),
        "entry_themes": entry_themes or None,
        "steps": req.steps or opts.get("steps"),
        "roles": req.roles or opts.get("roles"),
    }

    try:
        if use_llm:
            personas = generate_personas_llm(req.count, factors, **kwargs)
        else:
            personas = generate_personas_fallback(req.count, factors, **kwargs)
        personas = _validate_personas(personas, factors)
    except Exception as e:
        if use_llm:
            personas = generate_personas_fallback(req.count, factors, **kwargs)
            personas = _validate_personas(personas, factors)
        else:
            raise HTTPException(status_code=500, detail=str(e))

    if len(personas) != req.count:
        raise HTTPException(
            status_code=500,
            detail=f"生成数量不符：期望 {req.count}，实际 {len(personas)}",
        )

    reset_evolution()
    return set_personas(personas)
