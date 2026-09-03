from __future__ import annotations

import json
from typing import Any, List, Optional

from schemas import Factor, Job, Outcome, SubJob
from services.persona_coherence import ARCHETYPE_SEED_NAMES


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


def _schema_example() -> str:
    return """{
  "id":"P01", "name":"...", "emoji":"...", "segment":"...", "role":"...", "subject":"...",
  "age":40, "gender":"女", "city":"...", "occupation":"...", "family":"...", "income":"...",
  "osa":{"severity":"中度","ahi":"—","diagnosed":false,"stage":"察觉"},
  "mindset":{"core_motive":"...","fear":"...","decision_logic":"...","price_sensitivity":5,
    "brand_anchor":"...","channel_preference":"...","quote":"..."},
  "dominant_features":[{"code":"A1","weight":9}],
  "factor_weights":{"A1":9},
  "blockers":[],"drivers":[],"decision_style":"理性",
  "react":{"advance":"...{{topic}}...","hesitate":"...","reject":"...","na":"..."},
  "jtbd":{
    "entry_situation":"...","job_id":"J5","job_owner":"伴侣",
    "core_job":"...","job_statement":"...","current_step":"...",
    "desired_outcomes":[{"id":"O4","importance":9,"satisfaction":3}],
    "forces":{"push":["A1"],"pull":["B4"],"anxiety":["B2"],"habit_or_alternative":[]}
  },
  "evidence_refs":["llm_generated","synthetic"]
}"""


def build_single_persona_prompt(
    blueprint: Any,
    factors: List[Factor],
    jobs: List[Job],
    sub_jobs: List[SubJob],
    outcomes: List[Outcome],
    *,
    used_names: Optional[List[str]] = None,
    banned_names: Optional[List[str]] = None,
) -> str:
    bp = blueprint.to_prompt_dict() if hasattr(blueprint, "to_prompt_dict") else blueprint
    job = next((j for j in jobs if j.id == bp.get("job_id")), None)
    used = used_names or []
    banned = banned_names or sorted(ARCHETYPE_SEED_NAMES)

    return f"""你是呼吸机消费者心智画像生成器。请基于 JTBD 结构槽位，创造**一个全新的、独立的真实人物**。

【重要 — 禁止复制预设原型】
- 不得使用以下已有原型姓名：{json.dumps(banned, ensure_ascii=False)}
- 本批已用姓名（不可重复）：{json.dumps(used, ensure_ascii=False)}
- 不得照搬「刘女士/王叔/陈女士」等固定故事；姓名、职业、家庭、口语 quote 必须原创
- 14 个原型只提供 Job/角色/分群等**结构约束**，不是让你抄写内容

【本槽位结构蓝图 — 必须遵守】
{json.dumps(bp, ensure_ascii=False, indent=2)}

【对应 Job 详情】
{json.dumps(job.model_dump() if job else {}, ensure_ascii=False, indent=2)}

【子任务 sub_jobs】
{json.dumps([s.model_dump() for s in sub_jobs], ensure_ascii=False, indent=2)}

【期望结果 outcomes】
{json.dumps([o.model_dump() for o in outcomes], ensure_ascii=False, indent=2)}

【决策维度 factors】
{json.dumps([f.model_dump() for f in factors], ensure_ascii=False, indent=2)}

【生成顺序】
1. 严格按蓝图 job_id / job_owner / entry_situation / current_step_id 设定 jtbd
2. segment、role、subject 与蓝图 role_hint / subject_hint **同类但可改写**（如换具体亲属、换职业场景）
3. 创造全新人口学：age/gender/city/occupation/family/income — 须与 role/subject 逻辑自洽
4. desired_outcomes 从蓝图 desired_outcome_ids 中选 3-5 条，importance/satisfaction 拉开差距（最急缺口 satisfaction 低）
5. dominant_features 与 forces 的 factor id 必须来自 factors，且与角色匹配（J7→A8，J4→A10，伴侣→A1 等）
6. mindset 与 react 第一人称，口语化，体现 creativity_seed 带来的随机生活细节
7. osa：未确诊/察觉阶段 ahi 填 "—"；确诊后才有数值
8. id 必须为 "{bp.get("persona_id", "P01")}"

【逻辑红线】
- 子女(为父母)：年龄 28-52，family 须含父母，subject 为父亲/母亲(患者|重症)
- 伴侣推动：性别与 subject 对应（女→丈夫，男→妻子）
- J4 重症：family 须体现渐冻/慢阻肺/呼吸支持/重症
- J6 羞耻：本人自用，非室友受害者叙事

【随机创意提示】
- 城市层级参考：{bp.get("city_tier")}
- 职业方向参考：{bp.get("occupation_hint")}
- 生活纹理：{bp.get("life_texture")}
- 创意种子（用于差异化）：{bp.get("creativity_seed")}

【输出】只输出一个 JSON 对象，不要 markdown 或解释。格式：
{_schema_example()}
"""


def build_repair_prompt(
    persona_dict: dict,
    issues: List[str],
    factors: List[Factor],
    jobs: List[Job],
    sub_jobs: List[SubJob],
    outcomes: List[Outcome],
    *,
    blueprint: Any = None,
) -> str:
    bp = (
        blueprint.to_prompt_dict()
        if blueprint is not None and hasattr(blueprint, "to_prompt_dict")
        else {}
    )
    return f"""你是消费者心智画像 QC 修复器。下面这份 JSON 未通过逻辑质检，请**最小改动**修复全部问题后重新输出。

【质检问题 — 必须全部解决】
{json.dumps(issues, ensure_ascii=False, indent=2)}

【结构蓝图（不可偏离 Job/角色骨架）】
{json.dumps(bp, ensure_ascii=False, indent=2)}

【当前错误画像】
{json.dumps(persona_dict, ensure_ascii=False, indent=2)}

【jobs / sub_jobs / outcomes / factors 参照】
jobs: {json.dumps([j.model_dump() for j in jobs], ensure_ascii=False)}
outcomes: {json.dumps([o.model_dump() for o in outcomes], ensure_ascii=False)}
factors ids: {json.dumps([f.id for f in factors], ensure_ascii=False)}

【修复要求】
- 保留 id 不变；尽量保留已合理的原创姓名与故事，只修逻辑矛盾处
- 若姓名与预设原型重名，换一个全新姓名
- dominant_features / factor_weights / jtbd / family / role / subject 须彼此一致
- evidence_refs 保留 "llm_generated"

【输出】只输出修复后的单个 JSON 对象，格式同生成 schema。
"""
