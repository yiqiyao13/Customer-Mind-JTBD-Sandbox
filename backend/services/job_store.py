from __future__ import annotations

import json
from pathlib import Path
from typing import List

from schemas import Job, Outcome, SubJob

ROOT = Path(__file__).resolve().parents[2]


def _jobs_raw() -> dict:
    return json.loads((ROOT / "data" / "jobs.json").read_text(encoding="utf-8"))


def load_jobs() -> List[Job]:
    return [Job.model_validate(j) for j in _jobs_raw()["jobs"]]


def load_sub_jobs() -> List[SubJob]:
    return [SubJob.model_validate(s) for s in _jobs_raw()["sub_jobs"]]


def load_stages() -> List[str]:
    return list(_jobs_raw().get("stages", []))


def load_outcomes() -> List[Outcome]:
    data = json.loads((ROOT / "data" / "outcomes.json").read_text(encoding="utf-8"))
    return [Outcome.model_validate(o) for o in data["outcomes"]]


def get_job(job_id: str) -> Job | None:
    for j in load_jobs():
        if j.id == job_id:
            return j
    return None


def get_sub_job(step_id: str) -> SubJob | None:
    for s in load_sub_jobs():
        if s.id == step_id:
            return s
    return None


def get_outcome(outcome_id: str) -> Outcome | None:
    for o in load_outcomes():
        if o.id == outcome_id:
            return o
    return None


def resolve_step_name(step: str, job_id: str = "") -> str:
    """把 LLM 偶发填的 step id（如 e/a）归一成中文步骤名；已是中文则原样返回。"""
    step = (step or "").strip()
    if not step:
        return step
    sub_jobs = load_sub_jobs()
    by_id = {s.id: s.name for s in sub_jobs}
    names = {s.name for s in sub_jobs}
    if step in names:
        return step
    if step in by_id:
        return by_id[step]
    # 蓝图偶发写成 "e 预算内选对"
    for sid, name in by_id.items():
        if step.startswith(sid + " ") or step.startswith(sid + "：") or step.startswith(sid + ":"):
            return name
    return step


def next_step_name(current_step: str, job_id: str) -> str:
    """按 Job 的 step_ids 顺序推进到下一步名称；已是末步则保持。"""
    job = get_job(job_id)
    sub_jobs = {s.id: s for s in load_sub_jobs()}
    if not job:
        return resolve_step_name(current_step, job_id)

    current_step = resolve_step_name(current_step, job_id)

    # current_step 可能是名称或 id
    current_id = None
    for sid in job.step_ids:
        sj = sub_jobs.get(sid)
        if not sj:
            continue
        if sj.name == current_step or sid == current_step:
            current_id = sid
            break

    if current_id is None:
        return current_step

    idx = job.step_ids.index(current_id)
    if idx + 1 >= len(job.step_ids):
        return sub_jobs[current_id].name if current_id in sub_jobs else current_step
    nxt = job.step_ids[idx + 1]
    return sub_jobs[nxt].name if nxt in sub_jobs else current_step
