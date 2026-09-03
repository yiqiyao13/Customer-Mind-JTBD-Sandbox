from __future__ import annotations

import json
from typing import List, Optional

from schemas import Factor, Job, Outcome, SubJob


def build_generation_prompt(
    count: int,
    factors: List[Factor],
    jobs: List[Job],
    sub_jobs: List[SubJob],
    outcomes: List[Outcome],
    *,
    job_ids: Optional[List[str]] = None,
    entry_situations: Optional[List[str]] = None,
    steps: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
) -> str:
    filter_note = ""
    if job_ids:
        filter_note += f"\n优先覆盖 Job: {job_ids}"
    if entry_situations:
        filter_note += f"\n优先起点情境: {entry_situations}"
    if steps:
        filter_note += f"\n优先当前步骤: {steps}"
    if roles:
        filter_note += f"\n优先 Job Owner / 角色: {roles}"

    return f"""你是消费者心智画像生成器。基于以下 JTBD 任务本体与维度数据库，生成 {count} 个呼吸机消费者心智。

【任务本体 jobs】(id/名称/起点情境/发起者/statement/步骤)
{json.dumps([j.model_dump() for j in jobs], ensure_ascii=False, indent=2)}

【子任务 sub_jobs】
{json.dumps([s.model_dump() for s in sub_jobs], ensure_ascii=False, indent=2)}

【期望结果 outcomes】(id/成功标准)
{json.dumps([o.model_dump() for o in outcomes], ensure_ascii=False, indent=2)}

【决策维度 factors】(id/名称/权重/定义/force_default/job_ids/outcome_ids)
{json.dumps([f.model_dump() for f in factors], ensure_ascii=False, indent=2)}
{filter_note}

【生成顺序 — 严格按此，禁止反向拼装】
1. 先从 jobs 中选一个 entry_situation、job_owner、core_job（job 名称）和当前 job_step（子任务名，取自 sub_jobs.name）；
2. 为该 Job 选 3-5 条 desired_outcomes（id 必须来自 outcomes），给出 importance（1-10）与 satisfaction（1-10，越低越急需改善）；
3. 从 factors 中选有证据关联的 push / pull / anxiety / habit_or_alternative 四类 force（填 factor id）；
4. 再生成与上述任务一致的人口学、家庭、疾病情境、segment/role/subject；
5. 最后生成第一人称 react 模板（含 {{{{topic}}}}），不得引入 factors 之外的新临床/行为事实；
6. 输出 evidence_refs；无真实来源时标 synthetic / hypothesis。

【逻辑一致性】
- J5 关系修复 → job_owner 多为伴侣，主导 A1/B2/B4，禁止单独挂 A8
- J7 孝道照护 → job_owner 为子女，可用 A8，禁止伴侣分房话术当核心
- J4 重症呼吸支持 → 必须含 A10，与治打鼾分流
- J2 白天精力 → 本人，A4/B1
- dominant_features 与 forces 中的 factor id 必须来自 factors；desired_outcomes.id 必须来自 outcomes；jtbd.job_id 必须来自 jobs

【覆盖要求】覆盖的对象是 Job × Entry Situation × Step，而非每个 factor 都做成一个人。{count} 个人要尽量覆盖 7 个 Job 与不同 job_owner（本人/伴侣/子女）。

【输出】只输出一个 JSON 数组，不要其他文字。每人必须含 jtbd 对象：
[ {{
  "id":"P01", "name":"...", "emoji":"...", "segment":"...", "role":"...", "subject":"...",
  "age":40, "gender":"女", "city":"...", "occupation":"...", "family":"...", "income":"...",
  "osa":{{...}}, "mindset":{{...}},
  "dominant_features":[{{"code":"A1","weight":9}}],
  "factor_weights":{{"A1":9,...}},
  "blockers":[], "drivers":[], "decision_style":"理性",
  "react":{{"advance":"...{{{{topic}}}}...","hesitate":"...","reject":"...","na":"..."}},
  "jtbd":{{
    "entry_situation":"...",
    "job_id":"J5",
    "job_owner":"伴侣",
    "core_job":"修复/维系亲密关系",
    "job_statement":"...",
    "current_step":"确认能适应",
    "desired_outcomes":[{{"id":"O4","importance":9,"satisfaction":3}}],
    "forces":{{"push":["A1"],"pull":["B4"],"anxiety":["B2"],"habit_or_alternative":[]}}
  }},
  "evidence_refs":["synthetic"]
}} ]
"""
