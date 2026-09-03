from __future__ import annotations

from fastapi import APIRouter

from services.job_store import load_jobs, load_outcomes, load_stages, load_sub_jobs
from services.simulate import ENTRY_THEME_TO_JOBS, INTERVENTION_MAP

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs")
def list_jobs():
    jobs = load_jobs()
    sub_jobs = load_sub_jobs()
    stages = load_stages()
    # 主任务 → 子任务 树（按 jobs.step_ids 顺序；未知 step 忽略）
    sub_by_id = {s.id: s for s in sub_jobs}
    job_trees = []
    for j in jobs:
        steps = []
        for sid in j.step_ids:
            s = sub_by_id.get(sid)
            if not s:
                continue
            steps.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "stage": s.stage,
                }
            )
        # 按阶段分组，便于前端泳道展示
        by_stage: dict[str, list] = {st: [] for st in stages}
        for step in steps:
            by_stage.setdefault(step["stage"], []).append(step)
        job_trees.append(
            {
                **j.model_dump(),
                "steps": steps,
                "stages": [
                    {"name": st, "steps": by_stage.get(st, [])}
                    for st in stages
                    if by_stage.get(st)
                ],
            }
        )
    return {
        "jobs": [j.model_dump() for j in jobs],
        "sub_jobs": [s.model_dump() for s in sub_jobs],
        "job_trees": job_trees,
        "stages": stages,
        "entry_themes": list(ENTRY_THEME_TO_JOBS.keys()),
        "theme_to_jobs": ENTRY_THEME_TO_JOBS,
    }


@router.get("/sub_jobs")
def list_sub_jobs():
    return [s.model_dump() for s in load_sub_jobs()]


@router.get("/outcomes")
def list_outcomes():
    return [o.model_dump() for o in load_outcomes()]


@router.get("/interventions")
def list_interventions():
    return {
        key: {
            "outcomes": meta.get("outcomes", []),
            "forces": meta.get("forces", []),
            "keywords": meta.get("keywords", []),
        }
        for key, meta in INTERVENTION_MAP.items()
    }
