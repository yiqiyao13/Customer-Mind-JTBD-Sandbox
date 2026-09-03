"""生成结果逻辑一致性校验。"""
from __future__ import annotations

from typing import List, Tuple

from schemas import Factor, Persona


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
            or segment == "关系驱动型"
        )

    if fid == "A10":
        blob = (subject + role).lower()
        return any(x in blob for x in ("重症", "als", "渐冻", "慢阻肺", "子女"))

    if fid == "A11":
        return True

    if fid in ("A4", "A5") and role == "子女(为父母)":
        return segment in ("长期照护型", "健康焦虑自用型")

    return True


def validate_persona(persona: Persona, factors: List[Factor]) -> List[str]:
    issues: List[str] = []
    factor_map = {f.id: f for f in factors}
    family = persona.family or ""

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
        # subject 须是长辈
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

    if "重症" in persona.subject or persona.jtbd.job_id == "J4":
        if not any(x in family for x in ("渐冻", "慢阻肺", "呼吸支持", "重症")):
            issues.append(f"重症照护对象与家庭描述不一致（{persona.name}/{family}）")

    # Job 与角色粗检
    jid = persona.jtbd.job_id
    if jid == "J7" and persona.jtbd.job_owner != "子女" and "子女" not in persona.role:
        issues.append("J7 孝道 Job 的发起者应为子女")
    if jid == "J6" and "室友影响" in persona.role:
        issues.append("J6 羞耻 Job 不应绑在「被室友吵醒的受害者」角色上")
    if jid == "J4" and "A10" not in [d.code for d in persona.dominant_features]:
        issues.append("J4 重症 Job 应包含 A10 呼吸支持维度")

    if not persona.osa.diagnosed and persona.osa.ahi not in ("—", "", None):
        if persona.osa.stage in ("未察觉", "察觉"):
            issues.append("未确诊/察觉阶段不应有精确 AHI")

    return issues


def fix_persona_coherence(persona: Persona, factors: List[Factor]) -> Persona:
    """剔除不一致主导维度；修正明显的 AHI/确诊矛盾。"""
    family = persona.family or ""
    kept = []
    for d in persona.dominant_features:
        f = next((x for x in factors if x.id == d.code), None)
        if f and factor_fits_persona(f, persona.role, persona.subject, family, persona.segment):
            kept.append(d)
    if kept:
        persona.dominant_features = kept[:4]

    # 权重：不匹配角色的归零
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

    return persona


def assert_personas_coherent(personas: List[Persona], factors: List[Factor]) -> None:
    """硬错误直接抛；用于生成出口。"""
    hard_markers = ("不匹配", "不应", "应为", "人口学像", "缺少父母", "不一致")
    for p in personas:
        p = fix_persona_coherence(p, factors)
        issues = validate_persona(p, factors)
        hard = [i for i in issues if any(m in i for m in hard_markers)]
        if hard:
            raise ValueError(f"心智 {p.id}/{p.name} 逻辑不成立：" + "；".join(hard))
