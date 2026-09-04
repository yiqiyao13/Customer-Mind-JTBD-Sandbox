"""生成结果逻辑一致性校验。"""
from __future__ import annotations

from typing import List, Optional, Set

from schemas import DesiredOutcome, Factor, Persona

# 14 个预设原型种子名 — LLM 生成时应避免直接复用
ARCHETYPE_SEED_NAMES: Set[str] = {
    "刘女士", "吴姐", "林姐", "孙女士", "小李", "韩女士", "王叔", "小陈",
    "周医生", "张先生", "老马", "小杨", "小徐", "赵大爷", "陈女士",
}

# Job → 默认核心 Outcome（修复漂移时用）
_JOB_OUTCOME_DEFAULTS = {
    "J1": [("O1", 9, 2), ("O3", 8, 4), ("O6", 7, 5)],
    "J2": [("O2", 9, 3), ("O3", 8, 4), ("O8", 7, 5)],
    "J3": [("O2", 10, 2), ("O3", 9, 4), ("O7", 8, 3)],
    "J4": [("O9", 10, 2), ("O7", 8, 3), ("O3", 7, 4)],
    "J5": [("O4", 9, 3), ("O3", 8, 4), ("O6", 7, 5)],
    "J6": [("O10", 10, 2), ("O8", 7, 4), ("O3", 6, 5)],
    "J7": [("O5", 9, 3), ("O7", 8, 4), ("O2", 7, 5)],
}


def factor_fits_persona(
    factor: Factor,
    role: str,
    subject: str,
    family: str,
    segment: str,
) -> bool:
    fid = factor.id

    if fid == "A8":
        if role == "子女(为父母)":
            return True
        if any(x in subject for x in ("父亲", "母亲", "父母", "老人", "长辈")):
            return True
        return False

    if fid == "A1":
        if role == "子女(为父母)":
            return False
        return (
            "伴侣" in role
            or "家人" in role
            or "室友" in role
            or "丈夫" in family
            or "妻子" in family
            or segment in ("关系驱动型", "场景干扰型")
        )

    if fid == "A10":
        blob = (subject + role).lower()
        return any(x in blob for x in ("重症", "als", "渐冻", "慢阻肺", "子女"))

    if fid == "A11":
        return True

    if fid in ("A4", "A5") and role == "子女(为父母)":
        return segment in ("长期照护型", "健康焦虑自用型")

    return True


def _is_roommate_victim(persona: Persona) -> bool:
    role = persona.role or ""
    return "室友" in role and "影响" in role


def _is_caregiver_role(persona: Persona) -> bool:
    role = persona.role or ""
    return "子女" in role or "照护" in role or "推动" in role


def validate_persona(persona: Persona, factors: List[Factor]) -> List[str]:
    issues: List[str] = []
    factor_map = {f.id: f for f in factors}
    family = persona.family or ""
    jid = persona.jtbd.job_id if persona.jtbd else ""
    role = persona.role or ""
    seg = persona.segment or ""

    for d in persona.dominant_features:
        f = factor_map.get(d.code)
        if not f:
            issues.append(f"未知维度 {d.code}")
            continue
        if not factor_fits_persona(f, persona.role, persona.subject, family, persona.segment):
            issues.append(
                f"主导维度「{f.name}」与角色「{persona.role}」/对象「{persona.subject}」不匹配"
            )

    if persona.role == "子女(为父母)":
        if persona.age >= 55 and "独居" in family and "母亲" not in family and "父亲" not in family:
            issues.append(
                f"角色为子女尽孝，但人口学像被照护老人（{persona.name}/{persona.age}岁/{family}）"
            )
        if not any(x in family for x in ("父亲", "母亲", "父母", "爸", "妈")):
            issues.append(f"子女照护角色但家庭描述缺少父母（{persona.name}/{family}）")
        if "A8" not in [d.code for d in persona.dominant_features] and persona.segment == "长期照护型":
            issues.append("子女为父母购机建议包含孝心/隔代亲(A8)维度")
        if not any(x in persona.subject for x in ("父亲", "母亲", "父母", "老人", "长辈")):
            issues.append(f"子女照护的对象应是长辈，当前为「{persona.subject}」")

    if "伴侣" in persona.role or "家人推动" in persona.role:
        if "丈夫" in persona.subject and persona.gender == "男":
            issues.append(f"男性推动者不应以「丈夫」为照护对象（{persona.name}）")
        if "妻子" in persona.subject and persona.gender == "女":
            issues.append(f"女性推动者不应以「妻子」为照护对象（{persona.name}）")
        if "丈夫" in persona.subject and not any(x in family for x in ("丈夫", "老公")):
            issues.append(f"对象是丈夫但家庭描述未提及（{persona.name}/{family}）")
        if "妻子" in persona.subject and not any(x in family for x in ("妻子", "老婆")):
            issues.append(f"对象是妻子但家庭描述未提及（{persona.name}/{family}）")

    if "重症" in persona.subject or jid == "J4":
        if not any(x in family for x in ("渐冻", "慢阻肺", "呼吸支持", "重症")):
            issues.append(f"重症照护对象与家庭描述不一致（{persona.name}/{family}）")

    # —— Job / 角色 / 分群互斥 ——
    if jid == "J7" and persona.jtbd.job_owner != "子女" and "子女" not in role:
        issues.append("J7 孝道 Job 的发起者应为子女")
    if jid == "J6" and _is_roommate_victim(persona):
        issues.append("J6 羞耻 Job 不应绑在「被室友吵醒的受害者」角色上")
    if jid == "J4" and "A10" not in [d.code for d in persona.dominant_features]:
        issues.append("J4 重症 Job 应包含 A10 呼吸支持维度")

    if _is_roommate_victim(persona):
        if jid in ("J5", "J7", "J4"):
            issues.append(
                f"「室友影响」角色不应配 {jid}（伴侣/孝道/重症），应为 J1 恢复睡眠"
            )
        if persona.jtbd and persona.jtbd.job_owner == "伴侣":
            issues.append("「室友影响」的 job_owner 不应为「伴侣」")
        if persona.jtbd and any(d.id == "O4" for d in persona.jtbd.desired_outcomes):
            issues.append("「室友影响」不应以 O4（伴侣睡眠/关系）为核心 Outcome")
        if not any(x in family for x in ("室友", "合租", "宿舍")):
            issues.append(
                f"「室友影响」角色但家庭描述缺少室友/合租（{persona.name}/{family}）"
            )
        if seg not in ("场景干扰型", ""):
            issues.append(f"「室友影响」分群应为场景干扰型，当前为「{seg}」")
        # 叙事不得漂成已婚带娃/伴侣关系
        narrative_blob = " ".join(
            [
                persona.jtbd.job_statement or "",
                persona.jtbd.entry_situation or "",
                (persona.mindset.quote if persona.mindset else "") or "",
                (persona.mindset.core_motive if persona.mindset else "") or "",
                (persona.react.reject if persona.react else "") or "",
            ]
        )
        family_has_kids = any(x in family for x in ("孩子", "女儿", "儿子", "二孩"))
        if not family_has_kids and any(
            x in narrative_blob for x in ("两个孩子", "照顾孩子", "影响孩子睡觉", "照顾家庭")
        ):
            issues.append("「室友影响」叙事不应夹带已婚带娃/照顾孩子（与合租受害者冲突）")
        if any(x in narrative_blob for x in ("分房", "老公打呼", "妻子打呼", "伴侣睡眠")) and "室友" not in narrative_blob:
            issues.append("「室友影响」叙事不应写成伴侣分房关系话术")

    if jid == "J5":
        if _is_roommate_victim(persona):
            pass  # already flagged
        elif "伴侣" not in role and "家人" not in role and "推动" not in role:
            if persona.jtbd and persona.jtbd.job_owner == "伴侣" and role == "本人":
                issues.append("J5 伴侣关系 Job 不应挂在「本人」自用角色上（无伴侣推动语义）")

    # 分群 vs Job/角色
    if seg == "长期照护型" and role == "本人" and jid in ("J1", "J2", "J3", "J6") and not _is_caregiver_role(persona):
        issues.append(
            f"本人自用诉求（{jid}）不应标成「长期照护型」，应为健康焦虑自用型"
        )
    if seg == "健康焦虑自用型" and jid == "J6":
        issues.append("J6 社交羞耻诉求不应标成「健康焦虑自用型」，应为场景干扰型")
    if seg == "关系驱动型" and _is_roommate_victim(persona):
        issues.append("「室友影响」不应标成关系驱动型")

    if not persona.osa.diagnosed and persona.osa.ahi not in ("—", "", None):
        if persona.osa.stage in ("未察觉", "察觉"):
            issues.append("未确诊/察觉阶段不应有精确 AHI")

    return issues


def validate_persona_uniqueness(
    persona: Persona,
    *,
    used_names: Optional[Set[str]] = None,
) -> List[str]:
    """批次内姓名唯一 + 不得与 14 原型种子名完全相同。"""
    issues: List[str] = []
    base_name = persona.name.split("·")[0].split("（")[0].strip()
    if base_name in ARCHETYPE_SEED_NAMES:
        issues.append(f"姓名「{persona.name}」与预设原型重名，请创造全新姓名")
    if used_names and persona.name in used_names:
        issues.append(f"姓名「{persona.name}」与本批已生成结果重复")
    return issues


def validate_against_blueprint(persona: Persona, blueprint) -> List[str]:
    """LLM 槽位：结构字段不得偏离蓝图。"""
    issues: List[str] = []
    if blueprint is None:
        return issues
    bp_job = getattr(blueprint, "job_id", "") or ""
    bp_role = getattr(blueprint, "role_hint", "") or ""
    bp_seg = getattr(blueprint, "segment", "") or ""
    bp_owner = getattr(blueprint, "job_owner", "") or ""

    if bp_job and persona.jtbd and persona.jtbd.job_id != bp_job:
        issues.append(f"job_id 应为蓝图 {bp_job}，当前为 {persona.jtbd.job_id}")
    if bp_owner and persona.jtbd and persona.jtbd.job_owner and persona.jtbd.job_owner != bp_owner:
        # 允许近义，但「伴侣」vs「本人」是硬冲突
        if {persona.jtbd.job_owner, bp_owner} == {"伴侣", "本人"} or (
            "子女" in bp_owner) != ("子女" in persona.jtbd.job_owner):
            issues.append(
                f"job_owner 应为蓝图「{bp_owner}」，当前为「{persona.jtbd.job_owner}」"
            )
    if "室友" in bp_role and "室友" not in (persona.role or ""):
        issues.append(f"角色须保留室友影响语义（蓝图「{bp_role}」），当前为「{persona.role}」")
    if bp_seg and persona.segment and persona.segment != bp_seg:
        # 分群漂移：硬拦与角色互斥的组合
        if bp_seg == "场景干扰型" and persona.segment in ("关系驱动型", "长期照护型", "健康焦虑自用型"):
            if "室友" in bp_role or getattr(blueprint, "job_id", "") in ("J1", "J6"):
                issues.append(f"分群应为蓝图「{bp_seg}」，当前为「{persona.segment}」")
        if bp_seg == "健康焦虑自用型" and persona.segment == "长期照护型":
            issues.append(f"分群应为蓝图「{bp_seg}」，当前为「{persona.segment}」")
    if bp_job == "J1" and persona.jtbd:
        if any(d.id == "O4" for d in persona.jtbd.desired_outcomes):
            issues.append("J1 恢复睡眠不应把 O4（伴侣关系）列为 desired_outcome")
    return issues


def _replace_outcomes(persona: Persona, job_id: str) -> None:
    defaults = _JOB_OUTCOME_DEFAULTS.get(job_id)
    if not defaults or not persona.jtbd:
        return
    persona.jtbd.desired_outcomes = [
        DesiredOutcome(id=oid, importance=imp, satisfaction=sat)
        for oid, imp, sat in defaults
    ]


def fix_persona_coherence(persona: Persona, factors: List[Factor]) -> Persona:
    """剔除不一致主导维度；修正明显的 Job/分群/角色漂移；步骤名归一化。"""
    from services.job_store import get_job, resolve_step_name

    family = persona.family or ""
    kept = []
    for d in persona.dominant_features:
        f = next((x for x in factors if x.id == d.code), None)
        if f and factor_fits_persona(f, persona.role, persona.subject, family, persona.segment):
            kept.append(d)
    if kept:
        persona.dominant_features = kept[:4]

    for f in factors:
        if f.id in persona.factor_weights and not factor_fits_persona(
            f, persona.role, persona.subject, family, persona.segment
        ):
            if f.id not in [d.code for d in persona.dominant_features]:
                persona.factor_weights[f.id] = 0

    if not persona.osa.diagnosed or persona.osa.stage in ("未察觉", "察觉"):
        if persona.osa.severity == "未确诊" or persona.osa.stage in ("未察觉", "察觉"):
            if not persona.osa.diagnosed:
                persona.osa.ahi = "—"

    if persona.jtbd:
        jid = persona.jtbd.job_id or ""

        # 室友受害者：禁止 J5/O4/伴侣 owner
        if _is_roommate_victim(persona):
            persona.segment = "场景干扰型"
            if jid in ("J5", "J7", "J4") or persona.jtbd.job_owner == "伴侣":
                persona.jtbd.job_id = "J1"
                persona.jtbd.job_owner = "本人"
                jid = "J1"
                job = get_job("J1")
                if job:
                    persona.jtbd.core_job = job.name
                _replace_outcomes(persona, "J1")
            elif any(d.id == "O4" for d in persona.jtbd.desired_outcomes):
                _replace_outcomes(persona, "J1" if jid == "J1" else jid or "J1")
                if jid != "J1":
                    persona.jtbd.job_id = "J1"
                    persona.jtbd.job_owner = "本人"
                    job = get_job("J1")
                    if job:
                        persona.jtbd.core_job = job.name
            if not any(x in (persona.family or "") for x in ("室友", "合租", "宿舍")):
                persona.family = "合租，室友打鼾严重影响夜间睡眠"
            if "室友" not in (persona.subject or ""):
                persona.subject = "本人(受室友影响)"
            # 叙事残留「伴侣/孩子」时，收紧入口与陈述，避免 UI 仍读出 J5 味道
            if persona.jtbd.job_id == "J1":
                es = persona.jtbd.entry_situation or ""
                if any(x in es for x in ("孩子", "伴侣", "丈夫", "妻子", "分房")) and "室友" not in es:
                    persona.jtbd.entry_situation = "合租室友鼾声严重，夜间睡眠被反复打断"
                if persona.jtbd.job_owner == "伴侣":
                    persona.jtbd.job_owner = "本人"
                js = persona.jtbd.job_statement or ""
                if any(x in js for x in ("照顾孩子", "两个孩子", "照顾家庭", "自身鼾声")) and "室友" not in js:
                    persona.jtbd.job_statement = (
                        "当合租室友鼾声如雷、整夜把我吵醒，导致白天精神恍惚时，"
                        "我需要找到一个能恢复连续、安稳睡眠的方法，让自己能重新充满精力地工作。"
                    )
                if persona.mindset:
                    q = persona.mindset.quote or ""
                    if any(x in q for x in ("两个孩子", "孩子都睡", "照顾孩子")):
                        persona.mindset.quote = (
                            "我白天开会时脑子就像一团浆糊，但我还得装出一副精神饱满的样子。"
                            "晚上被室友鼾声反复吵醒，我已经受够了。"
                        )
                    fear = persona.mindset.fear or ""
                    if "全家" in fear and "室友" not in fear:
                        persona.mindset.fear = fear.replace(
                            "让全家的日子更难过",
                            "也怕管室友的事撕破脸、合租日子更难过",
                        )
                if persona.react and persona.react.reject:
                    rj = persona.react.reject
                    if "孩子" in rj and "室友" not in rj:
                        persona.react.reject = rj.replace("影响孩子睡觉", "影响室友休息、把合租关系搞僵")

        # J6 羞耻 → 场景干扰型（非健康焦虑）
        if persona.jtbd.job_id == "J6" and persona.segment == "健康焦虑自用型":
            persona.segment = "场景干扰型"

        # 本人自用 J1–J3/J6 误标长期照护 → 健康焦虑自用型
        if (
            persona.segment == "长期照护型"
            and (persona.role or "") == "本人"
            and persona.jtbd.job_id in ("J1", "J2", "J3", "J6")
            and not _is_caregiver_role(persona)
        ):
            persona.segment = "健康焦虑自用型"

        persona.jtbd.current_step = resolve_step_name(
            persona.jtbd.current_step, persona.jtbd.job_id
        )

    return persona


def assert_personas_coherent(personas: List[Persona], factors: List[Factor]) -> None:
    """硬错误直接抛；用于生成出口。"""
    hard_markers = (
        "不匹配", "不应", "应为", "人口学像", "缺少父母", "不一致",
        "缺少室友", "蓝图",
    )
    for p in personas:
        p = fix_persona_coherence(p, factors)
        issues = validate_persona(p, factors)
        hard = [i for i in issues if any(m in i for m in hard_markers)]
        if hard:
            raise ValueError(f"心智 {p.id}/{p.name} 逻辑不成立：" + "；".join(hard))
