"""JTBD 驱动的 Campaign 仿真：以 Outcome / Force balance 判定，而非纯关键词命中。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from schemas import Factor, Outcome, Persona, SimulateResult
from services.job_store import load_outcomes, next_step_name

# 阈值：保留关键 Outcome 门控；弱功能词不能仅凭 soft 大面积推进
ADVANCE_THRESHOLD = 8
HESITATE_THRESHOLD = 3
SOFT_ADVANCE_THRESHOLD = 7
# 单独出现时偏弱、不宜只靠 soft 大面积 advance
WEAK_INTERVENTIONS = frozenset({
    "financing",
    "mask_fit_support",
    "material_hygiene",
    "trade_in",
})

INTERVENTION_MAP: Dict[str, dict] = {
    "hospital_endorsement": {
        "outcomes": ["O1", "O7"],
        "forces": [("B7", "anxiety", -2), ("B7", "pull", 1)],
        "keywords": ["医院", "三甲", "医生", "呼吸科", "睡眠中心", "专家", "挂号"],
    },
    "data_visibility": {
        "outcomes": ["O2"],
        "forces": [("B1", "pull", 3)],
        "keywords": ["数据", "报告", "小程序", "app", "同步", "AHI", "可视化", "监测记录"],
    },
    "trial": {
        "outcomes": ["O3", "O8"],
        "forces": [("B4", "pull", 2)],
        "keywords": ["试戴", "试用", "租赁", "免费试", "30天", "可退", "无理由", "体验"],
    },
    "mask_fit_support": {
        "outcomes": ["O3"],
        "forces": [("B2", "anxiety", -2), ("B2", "pull", 1)],
        "keywords": ["面罩适配", "鼻枕", "头带", "贴合", "漏气", "佩戴舒适", "面罩合适", "免费适配"],
    },
    "family_participation": {
        # O4：伴侣关系；孝道冲突风险 O5 由 filial_care 单独覆盖，避免「夫妻话术」误推 J7
        "outcomes": ["O4"],
        "forces": [("A1", "push", 2)],
        "keywords": ["伴侣", "家人", "分房", "夫妻", "老公", "老婆", "一起", "家庭"],
    },
    "filial_care": {
        "outcomes": ["O5"],
        "forces": [("A8", "push", 3)],
        "keywords": [
            "爸妈", "父母", "父亲", "母亲", "老人", "长辈", "孝心",
            "给爸妈", "给父母", "尽孝", "孝顺",
        ],
    },
    "financing": {
        "outcomes": ["O6"],
        "forces": [("B8", "anxiety", -2), ("B8", "pull", 1)],
        "keywords": ["分期", "国补", "补贴", "优惠", "预算", "性价比", "0利息", "免息"],
    },
    "trade_in": {
        "outcomes": ["O6", "O8"],
        "forces": [("A9", "habit_or_alternative", 1)],
        "keywords": ["二手", "以旧换新", "闲置", "翻新", "回收"],
    },
    "after_sales": {
        "outcomes": ["O7"],
        "forces": [("B3", "anxiety", -2), ("B3", "pull", 1)],
        "keywords": ["售后", "质保", "保修", "上门", "维修", "跟进"],
    },
    "life_support": {
        "outcomes": ["O9", "O7"],
        "forces": [
            ("A10", "push", 4),
            ("B3", "anxiety", -2),
            ("B7", "anxiety", -2),
        ],
        "keywords": [
            "渐冻", "als", "慢阻肺", "呼吸衰竭", "呼吸支持", "无创通气",
            "医疗级", "远程监护", "监护", "保命",
        ],
    },
    "shame_relief": {
        "outcomes": ["O5", "O1"],
        "forces": [("B6", "pull", 2)],
        "keywords": ["体面", "不丢人", "隐形", "名人", "明星", "小巧"],
    },
    "material_hygiene": {
        "outcomes": ["O3"],
        "forces": [("B9", "anxiety", -2), ("B9", "pull", 1)],
        "keywords": ["泡棉", "消音棉", "无泡棉", "滤棉", "卫生", "粉化", "纯净水"],
    },
}

ENTRY_THEME_TO_JOBS = {
    "心血管风险": ["J3"],
    "伴侣睡眠受损": ["J5", "J1"],
    "日间功能与安全": ["J2"],
    "照护责任": ["J7"],
    "重症呼吸支持": ["J4"],
    "社交羞耻": ["J6"],
}


def identify_factors(campaign: str, factors: List[Factor]) -> List[str]:
    text = campaign.lower()
    hits: List[str] = []
    for f in factors:
        if not f.enabled:
            continue
        for kw in f.keywords:
            if kw.lower() in text:
                hits.append(f.id)
                break
    return hits


def detect_interventions(
    campaign: str,
    explicit: Optional[List[str]] = None,
) -> List[str]:
    if explicit:
        return [i for i in explicit if i in INTERVENTION_MAP]
    text = campaign.lower()
    active: List[str] = []
    for key, meta in INTERVENTION_MAP.items():
        for kw in meta.get("keywords", []):
            if kw.lower() in text:
                active.append(key)
                break
    return active


def _interventions_for_persona(active: List[str], persona: Persona) -> List[str]:
    """保命干预仅对重症照护 Job 生效，避免普通共病人群被 ALS/慢阻肺话术拖进犹豫。"""
    out: List[str] = []
    for key in active:
        if key == "life_support" and persona.jtbd.job_id != "J4":
            continue
        if key == "filial_care" and persona.jtbd.job_id not in ("J7", "J4"):
            # 孝道干预主要服务子女照护；重症照护可共享「给父母」语境
            continue
        out.append(key)
    return out


def _factor_name_map(factors: List[Factor]) -> Dict[str, str]:
    return {f.id: f.name for f in factors}


def _factor_weight_map(factors: List[Factor]) -> Dict[str, int]:
    return {f.id: f.weight for f in factors}


def _outcomes_improved_by(active: List[str]) -> set[str]:
    improved: set[str] = set()
    for key in active:
        meta = INTERVENTION_MAP.get(key, {})
        improved.update(meta.get("outcomes", []))
    return improved


def _force_deltas(active: List[str]) -> List[Tuple[str, str, int]]:
    out: List[Tuple[str, str, int]] = []
    for key in active:
        for item in INTERVENTION_MAP.get(key, {}).get("forces", []):
            if len(item) == 3:
                out.append((item[0], item[1], item[2]))
            elif len(item) == 2:
                out.append((item[0], item[1], 1))
    return out


def _required_outcome(persona: Persona):
    dos = persona.jtbd.desired_outcomes
    if not dos:
        return None
    return min(dos, key=lambda d: (d.satisfaction / max(d.importance, 1), -d.importance))


def _pick_reaction(persona: Persona, decision: str, topic: str) -> str:
    """按角色/Job/障碍拼差异化口语，避免全员同一句。"""
    j = persona.jtbd
    job = j.core_job or persona.segment
    step = j.current_step or "当前这步"
    blocker = (persona.blockers or ["心里没底"])[0]
    quote_bit = (persona.mindset.quote or "").strip("「」")
    role = persona.role

    if "子女" in role:
        identity = f"我给长辈选设备"
    elif "伴侣" in role or "家人" in role:
        identity = f"我是家里在推动这件事的人"
    elif "室友" in role:
        identity = f"我被室友鼾声折磨够了"
    else:
        identity = f"我自己是当事人（{persona.occupation}）"

    tpl = getattr(persona.react, decision, "") or ""
    # 模板若仍是笼统句，改用人设拼装
    generic = (not tpl) or ("有点相关" in tpl) or ("J" in tpl and "任务" in tpl)
    if tpl and "{{topic}}" in tpl and not generic:
        return tpl.replace("{{topic}}", topic)
    if tpl and "{topic}" in tpl and not generic:
        return tpl.format(topic=topic)

    by_decision = {
        "advance": (
            f"{identity}。卡在「{step}」好久了，"
            f"听到「{topic}」总算对上我在做的「{job}」。"
            f"我最怕的是{blocker}，这一点要是能落地，我就愿意往下走。"
            + (f"说实话，我一直觉得「{quote_bit}」。" if quote_bit else "")
        ),
        "hesitate": (
            f"{identity}，现在卡在「{step}」。"
            f"「{topic}」沾边，但没解开我的顾虑——{blocker}。"
            f"对「{job}」来说，还差一口气。"
        ),
        "reject": (
            f"{identity}。你们讲的「{topic}」跟我真正卡的「{step}」不是一回事。"
            f"我操心的是{blocker}，这个没答到。"
        ),
        "na": (
            f"{identity}，我在忙的是「{job}」，"
            f"这段推广跟我的「{step}」关系不大。"
        ),
    }
    return by_decision.get(decision, by_decision["hesitate"])


def decide_for(
    persona: Persona,
    campaign: str,
    factors: List[Factor],
    *,
    hit_ids: Optional[List[str]] = None,
    interventions: Optional[List[str]] = None,
    outcomes: Optional[List[Outcome]] = None,
) -> Tuple[str, str, List[str], List[str], int, List[str], List[str], str, List[str]]:
    enabled = [f for f in factors if f.enabled]
    name_map = _factor_name_map(enabled)
    weight_map = _factor_weight_map(enabled)
    outcomes = outcomes or load_outcomes()
    outcome_names = {o.id: o.name for o in outcomes}

    hit_ids = hit_ids if hit_ids is not None else identify_factors(campaign, enabled)
    # 重症维度不对普通 OSA/共病人群计分
    if persona.jtbd.job_id != "J4":
        hit_ids = [h for h in hit_ids if h != "A10"]
    active = _interventions_for_persona(
        detect_interventions(campaign, interventions),
        persona,
    )
    improved_set = _outcomes_improved_by(active)
    force_deltas = _force_deltas(active)

    improved: List[str] = []
    unresolved: List[str] = []
    score = 0.0

    for do in persona.jtbd.desired_outcomes:
        if do.id in improved_set:
            strength = 1 + sum(
                1 for k in active if do.id in INTERVENTION_MAP.get(k, {}).get("outcomes", [])
            )
            score += do.importance * strength * 0.7
            improved.append(do.id)
        else:
            unresolved.append(do.id)

    forces = persona.jtbd.forces
    activated_force_ids = {fid for fid, _, _ in force_deltas} | set(hit_ids)

    for fid in forces.push:
        if fid in activated_force_ids:
            score += weight_map.get(fid, persona.factor_weights.get(fid, 3))
    for fid in forces.pull:
        if fid in activated_force_ids:
            score += weight_map.get(fid, persona.factor_weights.get(fid, 3))

    # 保命/关键 push 已命中时，未解除的 anxiety 降权，避免「售后没提」压死保命话术
    life_critical = persona.jtbd.job_id == "J4" and (
        "A10" in activated_force_ids or "O9" in improved
    )
    anxiety_scale = 0.25 if life_critical else 0.5
    # 最关键 Outcome 已被功能话术改善时，勿被无关 anxiety 轻易压死（数据/面罩/售后等）
    required = _required_outcome(persona)
    if required and required.id in improved_set:
        anxiety_scale = min(anxiety_scale, 0.25)
        score += 2.0  # 关键缺口被填的确认加成（控制幅度，避免弱词刷分）

    for fid in forces.anxiety:
        addressed = any(
            f == fid and force == "anxiety" and delta < 0
            for f, force, delta in force_deltas
        )
        if not addressed:
            score -= weight_map.get(fid, persona.factor_weights.get(fid, 4)) * anxiety_scale
        else:
            score += 2

    for fid in forces.habit_or_alternative:
        raised = any(
            f == fid and force == "habit_or_alternative" and delta > 0
            for f, force, delta in force_deltas
        )
        if raised:
            score += 1
        else:
            score -= weight_map.get(fid, 3) * 0.35

    if not active and not hit_ids:
        decision = "na"
        next_step = persona.jtbd.current_step
        topic = "这个活动"
    else:
        required_addressed = True if not required else required.id in improved

        anxiety_eased = any(
            f == fid and force == "anxiety" and delta < 0
            for fid in forces.anxiety
            for f, force, delta in force_deltas
        )
        pull_hit = any(fid in activated_force_ids for fid in forces.pull)
        push_hit = any(fid in activated_force_ids for fid in forces.push)
        # 功能话术：虽未打中「最渴」Outcome，但改善了高重要度 desired 且对症缓解 anxiety
        feature_pull = (
            anxiety_eased
            and any(
                do.id in improved and do.importance >= 7
                for do in persona.jtbd.desired_outcomes
            )
        )
        only_weak = bool(active) and set(active).issubset(WEAK_INTERVENTIONS)
        hard_advance = score >= ADVANCE_THRESHOLD and required_addressed
        # soft：关键 Outcome 对上即可；但「仅弱干预」还需 push/对症消焦虑/多 Outcome，防「便宜」「面罩」刷屏
        soft_ok = required_addressed or feature_pull or life_critical
        if only_weak and required_addressed and not (push_hit or anxiety_eased or pull_hit or len(improved) >= 2):
            soft_ok = False
        soft_advance = score >= SOFT_ADVANCE_THRESHOLD and soft_ok

        if hard_advance or soft_advance:
            decision = "advance"
            next_step = next_step_name(persona.jtbd.current_step, persona.jtbd.job_id)
        elif score >= HESITATE_THRESHOLD:
            decision = "hesitate"
            next_step = persona.jtbd.current_step
        else:
            decision = "reject"
            next_step = persona.jtbd.current_step

        if improved:
            topic = "、".join(outcome_names.get(i, i) for i in improved[:2])
        elif hit_ids:
            topic = "、".join(name_map.get(h, h) for h in hit_ids[:2])
        else:
            topic = "、".join(active[:2]) if active else "这个活动"

    reaction = _pick_reaction(persona, decision, topic)

    dom_codes = [d.code for d in persona.dominant_features]
    hit_dom = [h for h in hit_ids if h in dom_codes]

    willingness = 2
    if decision == "advance":
        willingness = min(10, 6 + int(score // 4))
    elif decision == "hesitate":
        willingness = min(7, 3 + int(score // 5))
    elif decision == "reject":
        willingness = max(1, 2)

    return (
        decision,
        reaction,
        hit_ids,
        hit_dom,
        willingness,
        improved,
        unresolved,
        next_step,
        active,
    )


def simulate_campaign(
    campaign: str,
    personas: List[Persona],
    factors: List[Factor],
    persona_ids: List[str] | None = None,
    interventions: Optional[List[str]] = None,
) -> Tuple[List[SimulateResult], Dict[str, int], List[str], List[str]]:
    enabled = [f for f in factors if f.enabled]
    campaign_hits = identify_factors(campaign, enabled)
    hit_names = [f.name for f in enabled if f.id in campaign_hits]
    active_global = detect_interventions(campaign, interventions)
    outcomes = load_outcomes()

    targets = personas
    if persona_ids:
        id_set = set(persona_ids)
        targets = [p for p in personas if p.id in id_set]

    results: List[SimulateResult] = []
    summary = {"advance": 0, "hesitate": 0, "na": 0, "reject": 0}

    for persona in targets:
        (
            decision,
            reaction,
            hits,
            hit_dom,
            willingness,
            improved,
            unresolved,
            next_step,
            active,
        ) = decide_for(
            persona,
            campaign,
            enabled,
            hit_ids=campaign_hits,
            interventions=interventions,
            outcomes=outcomes,
        )
        summary[decision] = summary.get(decision, 0) + 1
        results.append(
            SimulateResult(
                persona_id=persona.id,
                persona_name=persona.name,
                decision=decision,
                reaction=reaction,
                hit_factors=[f.name for f in enabled if f.id in hits],
                hit_dominant=[f.name for f in enabled if f.id in hit_dom],
                willingness=willingness,
                mode="rule",
                outcome_improved=improved,
                unresolved_outcomes=unresolved,
                next_step=next_step,
                interventions=active,
                reasoning=(
                    f"关键 Outcome 门控 + Force balance；"
                    f"改善 {improved or '无'}；未解 {unresolved or '无'}；"
                    f"下一步「{next_step}」"
                ),
            )
        )

    return results, summary, hit_names, active_global
