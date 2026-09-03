from __future__ import annotations

import random
from typing import Dict, List, Optional

from schemas import (
    DesiredOutcome,
    DominantFeature,
    Factor,
    ForceMap,
    JTBDProfile,
    Mindset,
    OSAInfo,
    Persona,
    ReactTemplates,
)
from services.job_store import get_job, load_sub_jobs
from services.persona_archetypes import PERSONA_ARCHETYPES, pick_archetypes
from services.persona_coherence import factor_fits_persona
from services.simulate import ENTRY_THEME_TO_JOBS

PERSONA_SEEDS: List[Dict] = [
    {
        "name": "刘女士", "emoji": "👩‍💼", "gender": "女", "age_range": (38, 48),
        "city": "三线城市", "occupation": "全职主妇", "income": "家庭月入约1.2万",
        "family": "丈夫42岁(中度OSA)+一子(小学)",
    },
    {
        "name": "王叔", "emoji": "👨", "gender": "男", "age_range": (45, 58),
        "city": "二线城市", "occupation": "货车司机", "income": "个人月入约8千",
        "family": "妻子同城，无子女",
    },
    {
        "name": "周医生", "emoji": "👨‍⚕️", "gender": "男", "age_range": (35, 45),
        "city": "一线城市", "occupation": "呼吸科主治医师", "income": "个人月入约2.5万",
        "family": "已婚，配偶无OSA",
    },
    {
        "name": "张先生", "emoji": "👨‍💼", "gender": "男", "age_range": (42, 52),
        "city": "一线城市", "occupation": "企业中层管理", "income": "家庭月入约3万",
        "family": "妻子+一子(初中)",
    },
    {
        "name": "老马", "emoji": "👴", "gender": "男", "age_range": (62, 72),
        "city": "四线城市", "occupation": "退休工人", "income": "退休金+子女补贴",
        "family": "与老伴同住，子女异地",
    },
    {
        "name": "林姐", "emoji": "👩", "gender": "女", "age_range": (40, 50),
        "city": "二线城市", "occupation": "超市店长", "income": "家庭月入约1.5万",
        "family": "丈夫(打鼾严重)+一女(高中)",
    },
    {
        "name": "李阿姨", "emoji": "👵", "gender": "女", "age_range": (55, 65),
        "city": "三线城市", "occupation": "退休教师", "income": "退休金约5千",
        "family": "独居，子女同城",
    },
    {
        # 尽孝女儿：中年子女，不是独居老人
        "name": "小李", "emoji": "👩", "gender": "女", "age_range": (34, 44),
        "city": "二线城市", "occupation": "中学语文老师", "income": "家庭月入约1.6万",
        "family": "已婚一子；母亲同城独居(中度OSA)",
    },
    {
        "name": "小陈", "emoji": "🧑", "gender": "男", "age_range": (28, 35),
        "city": "一线城市", "occupation": "互联网产品经理", "income": "个人月入约1.8万",
        "family": "独居，父母异地",
    },
    {
        "name": "韩女士", "emoji": "👩", "gender": "女", "age_range": (36, 44),
        "city": "二线城市", "occupation": "银行柜员", "income": "家庭月入约2万",
        "family": "已婚；父亲异地需睡眠照护",
    },
    {
        "name": "孙女士", "emoji": "👩", "gender": "女", "age_range": (33, 42),
        "city": "一线城市", "occupation": "护士", "income": "个人月入约1万",
        "family": "丈夫(疑似OSA)+幼子",
    },
    {
        "name": "小杨", "emoji": "🧑‍💻", "gender": "男", "age_range": (26, 32),
        "city": "二线城市", "occupation": "程序员", "income": "个人月入约1.2万",
        "family": "合租，室友打鼾影响睡眠",
    },
    {
        "name": "小徐", "emoji": "🧑", "gender": "女", "age_range": (26, 33),
        "city": "一线城市", "occupation": "设计师", "income": "个人月入约1.4万",
        "family": "合租，自己打呼被室友吐槽",
    },
    {
        "name": "吴姐", "emoji": "👩‍🦰", "gender": "女", "age_range": (45, 55),
        "city": "四线城市", "occupation": "个体户(小超市)", "income": "家庭月入约6千",
        "family": "丈夫(患者)+三代同堂",
    },
    {
        "name": "赵大爷", "emoji": "👴", "gender": "男", "age_range": (68, 75),
        "city": "三线城市", "occupation": "退休干部", "income": "退休金+儿子补贴",
        "family": "与老伴同住",
    },
    {
        "name": "陈女士", "emoji": "👩", "gender": "女", "age_range": (40, 50),
        "city": "二线城市", "occupation": "会计", "income": "家庭月入约1.8万",
        "family": "父亲患渐冻症，需夜间呼吸支持",
    },
]

# 复用原型时的姓名池。family 须能支撑对应故事角色。
EXTRA_SEEDS: List[Dict] = [
    # —— 本人/经济敏感 ——
    {"name": "钱叔", "emoji": "👨", "gender": "男", "age_range": (52, 62), "city": "三线城市", "occupation": "工厂班长", "income": "个人月入约7千", "family": "妻子同住"},
    {"name": "何先生", "emoji": "👨‍💼", "gender": "男", "age_range": (40, 50), "city": "一线城市", "occupation": "销售经理", "income": "家庭月入约2.5万", "family": "已婚一女"},
    {"name": "郑工", "emoji": "🧑‍🔧", "gender": "男", "age_range": (38, 48), "city": "二线城市", "occupation": "机电工程师", "income": "个人月入约1.5万", "family": "已婚"},
    {"name": "小马", "emoji": "👨", "gender": "男", "age_range": (30, 38), "city": "一线城市", "occupation": "外卖站长", "income": "个人月入约9千", "family": "合租"},
    {"name": "邓先生", "emoji": "👨‍💼", "gender": "男", "age_range": (44, 54), "city": "一线城市", "occupation": "公务员", "income": "家庭月入约2.2万", "family": "已婚一子"},
    {"name": "周姐", "emoji": "👩‍💼", "gender": "女", "age_range": (35, 45), "city": "一线城市", "occupation": "行政主管", "income": "个人月入约1.3万", "family": "已婚"},
    {"name": "小薇", "emoji": "🧑", "gender": "女", "age_range": (26, 33), "city": "一线城市", "occupation": "平面设计师", "income": "个人月入约1.4万", "family": "独居"},
    # —— 老人自用 ——
    {"name": "老周", "emoji": "👴", "gender": "男", "age_range": (65, 74), "city": "四线城市", "occupation": "退休司机", "income": "退休金约4千", "family": "与老伴同住"},
    {"name": "刘叔", "emoji": "👨", "gender": "男", "age_range": (55, 65), "city": "三线城市", "occupation": "社区保安", "income": "个人月入约5千", "family": "子女同城"},
    {"name": "罗大爷", "emoji": "👴", "gender": "男", "age_range": (68, 76), "city": "三线城市", "occupation": "退休教师", "income": "退休金+子女补贴", "family": "与老伴同住"},
    {"name": "冯大爷", "emoji": "👴", "gender": "男", "age_range": (66, 75), "city": "四线城市", "occupation": "退休工人", "income": "退休金约3.5千", "family": "独居，儿子同城"},
    {"name": "蒋叔", "emoji": "👨", "gender": "男", "age_range": (58, 66), "city": "二线城市", "occupation": "物业管理员", "income": "个人月入约6千", "family": "妻子同住"},
    {"name": "曹阿姨", "emoji": "👵", "gender": "女", "age_range": (58, 68), "city": "三线城市", "occupation": "退休会计", "income": "退休金约5千", "family": "独居，女儿同城"},
    # —— 伴侣推动（女→丈夫 / 男→妻子）——
    {"name": "黄姐", "emoji": "👩", "gender": "女", "age_range": (42, 52), "city": "二线城市", "occupation": "幼儿园老师", "income": "家庭月入约1.4万", "family": "丈夫打鼾+一子"},
    {"name": "唐女士", "emoji": "👩", "gender": "女", "age_range": (48, 58), "city": "四线城市", "occupation": "药店店员", "income": "家庭月入约8千", "family": "丈夫患者"},
    {"name": "潘姐", "emoji": "👩", "gender": "女", "age_range": (40, 50), "city": "三线城市", "occupation": "服装店主", "income": "家庭月入约1.1万", "family": "丈夫打鼾严重，快分房"},
    {"name": "顾先生", "emoji": "👨", "gender": "男", "age_range": (38, 48), "city": "二线城市", "occupation": "物流主管", "income": "家庭月入约1.8万", "family": "妻子打鼾严重，影响睡眠"},
    {"name": "陆先生", "emoji": "👨‍💼", "gender": "男", "age_range": (42, 52), "city": "一线城市", "occupation": "项目经理", "income": "家庭月入约2.8万", "family": "妻子(中度OSA)+一子"},
    # —— 子女照护 / 孝道 / 重症（必须是中年子女 + 父母在家庭描述里）——
    {"name": "许女士", "emoji": "👩", "gender": "女", "age_range": (34, 44), "city": "二线城市", "occupation": "人事专员", "income": "家庭月入约1.7万", "family": "已婚一子；母亲同城独居(中度OSA)"},
    {"name": "江先生", "emoji": "👨", "gender": "男", "age_range": (36, 46), "city": "一线城市", "occupation": "软件工程师", "income": "家庭月入约2.4万", "family": "已婚；父亲异地需睡眠照护"},
    {"name": "沈女士", "emoji": "👩", "gender": "女", "age_range": (38, 48), "city": "二线城市", "occupation": "药房主管", "income": "家庭月入约1.9万", "family": "父亲患渐冻症，需夜间呼吸支持"},
    {"name": "崔女士", "emoji": "👩", "gender": "女", "age_range": (35, 45), "city": "三线城市", "occupation": "小学老师", "income": "家庭月入约1.5万", "family": "已婚；母亲高血压打鼾需照护"},
    {"name": "姚先生", "emoji": "👨", "gender": "男", "age_range": (40, 50), "city": "二线城市", "occupation": "建筑项目员", "income": "家庭月入约1.6万", "family": "已婚一女；父亲慢阻肺需呼吸支持"},
    {"name": "温女士", "emoji": "👩", "gender": "女", "age_range": (36, 44), "city": "二线城市", "occupation": "银行客户经理", "income": "家庭月入约2万", "family": "父母异地需照护"},
    {"name": "邱女士", "emoji": "👩", "gender": "女", "age_range": (32, 40), "city": "一线城市", "occupation": "内容运营", "income": "个人月入约1.6万", "family": "合租"},
    {"name": "黎姐", "emoji": "👩", "gender": "女", "age_range": (41, 49), "city": "二线城市", "occupation": "保险顾问", "income": "家庭月入约2.1万", "family": "丈夫打鼾+一女"},
    {"name": "宋先生", "emoji": "👨", "gender": "男", "age_range": (34, 42), "city": "一线城市", "occupation": "产品经理", "income": "家庭月入约2.6万", "family": "已婚"},
    {"name": "万阿姨", "emoji": "👵", "gender": "女", "age_range": (60, 68), "city": "三线城市", "occupation": "退休护士", "income": "退休金约4.5千", "family": "与老伴同住"},
]

SEED_BY_NAME: Dict[str, Dict] = {s["name"]: s for s in PERSONA_SEEDS}


def _persona_id(index: int) -> str:
    return f"P{index:02d}" if index < 100 else f"P{index:03d}"


def _age_mid(seed: Dict) -> int:
    lo, hi = seed.get("age_range", (40, 50))
    return (lo + hi) // 2


def _seed_age_distance(a: Dict, b: Dict) -> int:
    return abs(_age_mid(a) - _age_mid(b))


def _arch_kind(arch: Dict) -> str:
    key = arch.get("key", "")
    role = arch.get("role", "")
    job = (arch.get("jtbd") or {}).get("job_id", "")
    if key == "nurse_caregiver":
        return "nurse_care"
    if key == "als_caregiver" or job == "J4" or "重症" in arch.get("subject", ""):
        return "als_care"
    if key.startswith("filial") or job == "J7" or "子女" in role:
        return "filial"
    if key.startswith("spouse") or role in ("家人推动者(伴侣)", "伴侣(推动者)"):
        return "spouse"
    if key in ("elderly_self", "retiree_struggle") or (
        arch.get("role") == "本人" and _age_mid(SEED_BY_NAME.get(arch.get("seed_name", ""), {})) >= 60
    ):
        return "elderly"
    if key in ("roommate_young", "shame_self"):
        return "young_social"
    return "self"


def _seed_fit_score(arch: Dict, seed: Dict) -> int:
    """越高越适合挂到该原型；负数表示不该复用到此人。"""
    kind = _arch_kind(arch)
    family = seed.get("family", "")
    occ = seed.get("occupation", "")
    age = _age_mid(seed)
    score = 0

    has_parent = any(x in family for x in ("父亲", "母亲", "父母", "爸", "妈"))
    has_critical = any(x in family for x in ("渐冻", "慢阻肺", "呼吸支持", "重症"))
    has_spouse_patient = any(
        x in family for x in ("丈夫", "老公", "妻子", "老婆", "打鼾", "患者", "OSA")
    ) and "室友" not in family
    is_elderly = age >= 58 or "退休" in occ
    is_young = age <= 36

    if kind in ("filial", "als_care"):
        if is_elderly and not has_parent:
            return -100  # 独居老人不能当子女照护者
        if age >= 55 and "独居" in family and not has_parent:
            return -100
        if has_critical and kind == "als_care":
            score += 40
        elif has_parent:
            score += 30
        elif 30 <= age <= 52:
            score += 10  # 中年可改写家庭为尽孝
        else:
            return -50
        if has_spouse_patient and not has_parent:
            score -= 25  # 黄姐这类优先给伴侣故事，不宜硬套重症父亲
    elif kind == "spouse":
        if is_elderly and not has_spouse_patient:
            return -40
        if has_spouse_patient:
            score += 30
        elif "已婚" in family or "妻子" in family or "丈夫" in family:
            score += 15
        else:
            score -= 10
        # 性别与「照护丈夫」默认女推动者：男种子仍可，稍后改 subject
        if arch.get("seed_name") and SEED_BY_NAME.get(arch["seed_name"], {}).get("gender"):
            if seed.get("gender") == SEED_BY_NAME[arch["seed_name"]]["gender"]:
                score += 5
    elif kind == "elderly":
        if is_elderly:
            score += 30
        elif age < 50:
            return -40
    elif kind == "young_social":
        if is_young or "合租" in family or "室友" in family:
            score += 25
        elif age >= 55:
            return -30
    else:
        score += 5

    preferred = SEED_BY_NAME.get(arch.get("seed_name", ""))
    if preferred:
        score -= _seed_age_distance(seed, preferred) // 3
    return score


def _unique_clone_name(base_name: str, used_names: set) -> str:
    """避免「小徐2」脏数据感：用城市后缀或乙丙丁。"""
    for mark in ("乙", "丙", "丁", "戊", "己", "庚", "辛"):
        cand = f"{base_name}（{mark}）"
        if cand not in used_names:
            return cand
    n = 2
    while f"{base_name}·{n}" in used_names:
        n += 1
    return f"{base_name}·{n}"


def _pick_unique_seed(
    preferred_name: str,
    used_names: set,
    *,
    gender_hint: str = "",
    arch: Optional[Dict] = None,
) -> Dict:
    """同次生成内姓名不重复；永不跨性别；优先角色匹配的备选。"""
    primary = SEED_BY_NAME.get(preferred_name)
    if primary and preferred_name not in used_names:
        used_names.add(preferred_name)
        return dict(primary)

    gender = gender_hint or (primary or {}).get("gender") or "男"

    def _available(pool: List[Dict]) -> List[Dict]:
        return [s for s in pool if s["gender"] == gender and s["name"] not in used_names]

    # 严禁跨性别兜底（N6）
    pool = _available(EXTRA_SEEDS)
    if not pool:
        pool = _available(PERSONA_SEEDS)
    if not pool:
        # 同性别耗尽：克隆人口学，只改名字
        base = primary or next(
            (s for s in PERSONA_SEEDS if s["gender"] == gender), PERSONA_SEEDS[0]
        )
        seed = dict(base)
        seed["name"] = _unique_clone_name(base["name"], used_names)
        used_names.add(seed["name"])
        return seed

    if arch:
        scored = sorted(
            pool,
            key=lambda s: (-_seed_fit_score(arch, s), _seed_age_distance(s, primary or s)),
        )
        good = [s for s in scored if _seed_fit_score(arch, s) >= 0]
        if good:
            seed = dict(good[0])
        elif _arch_kind(arch) in ("filial", "als_care", "spouse", "nurse_care") and primary:
            # 无合适备选时克隆主种子人口学，绝不硬套老人/错性别故事
            seed = dict(primary)
            seed["name"] = _unique_clone_name(primary["name"], used_names)
        else:
            seed = dict(scored[0])
    else:
        if primary:
            pool = sorted(pool, key=lambda s: _seed_age_distance(s, primary))
        seed = dict(pool[0])

    used_names.add(seed["name"])
    return seed


def _occ_matches(occupation: str, keywords: List[str]) -> bool:
    return any(k in occupation for k in keywords)


def _infer_care_parent(family: str, default: str = "父亲") -> str:
    if any(x in family for x in ("母亲", "妈妈", "妈")) and "父亲" not in family and "爸爸" not in family:
        return "母亲"
    if any(x in family for x in ("父亲", "爸爸", "爸")):
        return "父亲"
    if "父母" in family:
        return "父亲"
    return default


def _align_role_subject_family(arch: Dict, seed: Dict) -> tuple[str, str, str]:
    """
    换姓名后同步 role / subject / family，避免「黄姐照护父亲」但家庭只有丈夫。
    """
    kind = _arch_kind(arch)
    role = arch["role"]
    subject = arch["subject"]
    family = seed.get("family", "")
    gender = seed.get("gender", "")

    if kind == "spouse":
        role = "家人推动者(伴侣)"
        if gender == "男":
            subject = "妻子(患者)"
            if not any(x in family for x in ("妻子", "老婆")):
                family = "妻子打鼾严重，影响共同睡眠" + (f"；{family}" if family else "")
            # 去掉误导性的「丈夫患者」表述
            family = family.replace("丈夫患者", "妻子患者").replace("丈夫打鼾", "妻子打鼾")
        else:
            subject = "丈夫(患者)"
            if not any(x in family for x in ("丈夫", "老公")):
                family = "丈夫打鼾严重，快要分房" + (f"；{family}" if family else "")

    elif kind == "nurse_care":
        # 保留「伴侣照护者 / 护士」身份，不改写成普通推动者
        role = arch.get("role") or "伴侣照护者"
        subject = arch.get("subject") or ("丈夫(患者)" if gender != "男" else "妻子(患者)")
        if not any(x in family for x in ("丈夫", "老婆", "妻子", "老公")):
            family = ("妻子需规范治疗与夜间照护" if gender == "男" else "丈夫需规范治疗与夜间照护") + (
                f"；{family}" if family else ""
            )

    elif kind in ("filial", "als_care"):
        role = "子女(为父母)"
        parent = _infer_care_parent(family, "父亲" if kind == "als_care" else "母亲")
        if kind == "als_care":
            subject = f"{parent}(重症)"
            if not any(x in family for x in ("渐冻", "慢阻肺", "呼吸支持", "重症")):
                family = f"已婚；{parent}需夜间呼吸支持（重症）"
        else:
            subject = f"{parent}(患者)"
            if not any(x in family for x in ("父亲", "母亲", "父母", "照护")):
                family = f"已婚；{parent}同城需睡眠照护"
        # 老人独居种子被误用时，改写成「中年子女」家庭叙事
        age = _age_mid(seed)
        if age >= 58 or ("独居" in family and "子女同城" in family and parent not in (family or "")):
            if kind == "als_care":
                family = f"已婚一子；{parent}需夜间呼吸支持（重症）"
            else:
                family = f"已婚一子；{parent}需睡眠与设备照护"

    return role, subject, family


def _adapt_story_to_seed(
    arch: Dict, seed: Dict, *, subject: str, family: str
) -> tuple[Dict, List[str], List[str]]:
    """
    原型复用换姓名后，按新人口学 + 对齐后的 subject/family 改写文案。
    """
    ms = dict(arch["mindset"])
    blockers = list(arch.get("blockers") or [])
    drivers = list(arch.get("drivers") or [])
    key = arch.get("key", "")
    occ = seed.get("occupation", "")
    age = _age_mid(seed)
    kind = _arch_kind(arch)

    if seed["name"] == arch.get("seed_name") and family == seed.get("family"):
        # 原装种子且家庭未改写
        return ms, blockers, drivers

    if kind == "spouse":
        if "妻子" in subject:
            ms["core_motive"] = (
                "妻子鼾声越来越大，我们快要分房睡了，得帮她选一台能试戴、面罩合适的机器。"
            )
            ms["fear"] = "最怕买了她戴不住，家里人更埋怨我瞎折腾。"
            ms["quote"] = "我不是不想买，是得先让她愿意戴，别又白花钱。"
            ms["decision_logic"] = "先确认她愿意试，再比面罩和售后，价格要在家庭预算内。"
            blockers = ["妻子怕戴不住就放弃", "担心买贵被说乱花钱"]
            drivers = ["分房压力", "先试后买", "面罩适配"]
        else:
            ms["core_motive"] = (
                "丈夫鼾声越来越大，我们快要分房睡了，得帮他选一台能试戴、面罩合适的机器。"
            )
            if "开支紧" in (arch.get("mindset") or {}).get("core_motive", "") or key == "spouse_shopkeeper":
                ms["core_motive"] = "老公打鼾全家睡不好，但家里开支紧，得找性价比高的方案。"

    elif kind in ("filial", "als_care"):
        parent = "母亲" if "母" in subject else "父亲"
        pronoun = "她" if parent == "母亲" else "他"
        if kind == "als_care":
            ms["core_motive"] = f"{parent}需要夜间呼吸支持，这是保命设备，不能省。"
            ms["fear"] = f"最怕机器失灵或没人指导，危及{pronoun}的生命。"
            ms["quote"] = "能多陪一天，就值。"
            ms["decision_logic"] = "选医疗级、售后上门、能远程监护的方案。"
            blockers = ["设备可靠性要求极高", "长期维护成本"]
            drivers = ["呼吸支持", "远程照护", "售后上门"]
        else:
            ms["core_motive"] = (
                f"{parent}有睡眠呼吸问题，我作为子女得帮{pronoun}把关，别把照护变成催促冲突。"
            )
            ms["fear"] = f"怕催得太紧伤感情，也怕买了没人教{pronoun}用。"
            ms["quote"] = "孝心不是买最贵，是买能坚持用的。"
            blockers = [f"{parent}可能不愿戴", "两地奔波或时间不够"]
            drivers = ["孝心", "售后上门", "医院渠道"]

    elif key == "trucker_self":
        if _occ_matches(occ, ["司机", "驾驶", "外卖", "快递"]):
            ms["core_motive"] = "开车犯困太危险，但新机太贵，想看看二手或租赁。"
            blockers = ["跑活赚钱紧", "觉得戴机麻烦"]
            drivers = ["白天嗜睡安全", "二手低门槛", "价格敏感"]
        elif _occ_matches(occ, ["工厂", "班长", "工人", "保安", "物业", "机电"]):
            ms["core_motive"] = f"上{('夜班' if age >= 45 else '班')}犯困太危险，影响干活，但新机太贵，想看看二手或租赁。"
            ms["fear"] = "怕花大钱买了用不住，耽误上班挣钱。"
            ms["quote"] = "我知道要重视，可厂里挣的也就那么多。"
            blockers = ["手头紧", "觉得戴机麻烦"]
            drivers = ["班上犯困安全", "二手低门槛", "价格敏感"]
        elif "退休" in occ or age >= 62:
            ms["core_motive"] = "白天犯困怕摔跤，新机太贵，想看看二手或让子女帮忙租一台。"
            ms["fear"] = "怕给儿女添麻烦，也怕设备用不住白花钱。"
            ms["quote"] = "老了更怕摔，可也不敢乱花儿女的钱。"
            blockers = ["退休金有限", "操作怕复杂"]
            drivers = ["白天安全", "二手低门槛", "子女帮忙"]
        else:
            ms["core_motive"] = f"白天犯困太危险（我是{occ}），但新机太贵，想看看二手或租赁。"
            blockers = ["预算紧", "觉得戴机麻烦"]

    elif key == "shame_self":
        if age >= 50 or "退休" in occ:
            who = "女儿" if "女儿" in family else "家人"
            ms["core_motive"] = f"自己打呼被{who}吐槽难听，想体面解决，又不想闹得街坊都知道。"
            ms["fear"] = "最怕戴机更丢人，亲戚串门看见笑话。"
            ms["decision_logic"] = "选小巧不显眼、操作简单、能偷偷用的方案。"
            ms["quote"] = "年纪大了也要脸面，不想被当成笑话。"
            blockers = ["觉得戴机丢人", "不想被街坊知道"]
            drivers = ["社交尊严", "体面外观", "操作简单"]
        elif "合租" in family or age < 36:
            ms["core_motive"] = "自己打呼被室友录音嘲笑，想体面地解决，又不想闹得人尽皆知。"
        else:
            ms["core_motive"] = "自己打呼让家人难堪，想体面解决，又不想闹大。"

    elif key == "roommate_young":
        if "合租" in family or age < 36:
            pass
        elif age >= 50:
            ms["core_motive"] = "老伴/同住人鼾声如雷，我整夜睡不着，想推动对方去筛查或自己想办法睡好。"
            ms["fear"] = "怕开口伤感情，也怕查了发现两人都要治。"
            blockers = ["预算有限", "不确定该不该硬推对方"]
            drivers = ["同住打鼾", "睡眠被影响", "价格"]
        else:
            ms["core_motive"] = "同住人鼾声太响，我整夜睡不着，想推动对方去筛查或自己想办法睡好。"

    elif key == "elderly_self":
        if age < 50:
            ms["core_motive"] = "有高血压等基础病，医生说要治打鼾，家人也催我去配机。"
            ms["fear"] = "怕给家人添麻烦，也怕设备太复杂。"
            ms["quote"] = "不怕花钱，怕不会用、坚持不了。"

    elif key == "exec_self":
        if not _occ_matches(occ, ["管理", "经理", "主管", "公务员", "销售"]):
            ms["core_motive"] = f"白天犯困影响工作（{occ}），体检也提示睡眠问题，必须解决。"

    return ms, blockers, drivers

def _factor_map(factors: List[Factor]) -> Dict[str, Factor]:
    return {f.id: f for f in factors}


def _dominant_from_archetype(
    arch: Dict, factors: List[Factor], *, role: str, subject: str
) -> List[Factor]:
    fmap = _factor_map(factors)
    dom: List[Factor] = []
    for fid in arch["dominant"]:
        if fid in fmap:
            dom.append(fmap[fid])
    if len(dom) < 2:
        for f in factors:
            if f.id not in [x.id for x in dom] and factor_fits_persona(
                f, role, subject, "", arch["segment"]
            ):
                dom.append(f)
            if len(dom) >= 3:
                break
    return dom[:4]


def _build_factor_weights(
    factors: List[Factor],
    dominant: List[Factor],
    arch: Dict,
    *,
    role: str,
    subject: str,
) -> Dict[str, int]:
    """不匹配角色的维度权重为 0，避免孝心等污染自用者。"""
    dom_ids = {f.id for f in dominant}
    segment = arch["segment"]
    weights: Dict[str, int] = {}
    for f in factors:
        if f.id in dom_ids:
            weights[f.id] = min(10, max(6, f.weight))
        elif not factor_fits_persona(f, role, subject, "", segment):
            weights[f.id] = 0
        else:
            weights[f.id] = random.choice([0, 1, 2])
    return weights


def _react_from_archetype(arch: Dict, primary_name: str) -> ReactTemplates:
    job = get_job((arch.get("jtbd") or {}).get("job_id", ""))
    job_label = job.name if job else arch.get("segment", "这件事")
    step_id = (arch.get("jtbd") or {}).get("current_step_id", "")
    sub_map = {s.id: s for s in load_sub_jobs()}
    step = sub_map[step_id].name if step_id in sub_map else "当前步骤"
    # 用动机短句，避免把维度名（可能含「室友」）原样塞进所有人的反应模板
    motive = ((arch.get("mindset") or {}).get("core_motive") or primary_name)[:28]
    return ReactTemplates(
        advance=f"听到{{{{topic}}}}，这正好推进我在「{job_label}」上的任务（我卡在{step}），尤其是{motive}…想深入了解。",
        hesitate=f"{{{{topic}}}}有点相关，但我还卡在「{step}」，得再想想。",
        reject=f"推广没解开我真正卡点（{step} / {motive}…），不太信。",
        na=f"跟我现在的任务「{job_label}」关系不大。",
    )


def _osa_for_archetype(arch: Dict) -> OSAInfo:
    stage = arch["stage"]
    severity = arch.get("patient_severity", "未确诊")
    diagnosed = (
        stage in ("就医确诊", "决策纠结", "购买", "适应", "依从习惯", "复购更换")
        and severity != "未确诊"
    )
    ahi_map = {"轻度": "12", "中度": "22", "重度": "35", "未确诊": "—"}
    # 未确诊或仍在察觉前：不给精确 AHI
    ahi = ahi_map.get(severity, "—") if diagnosed else "—"
    return OSAInfo(
        severity=severity,
        ahi=ahi,
        diagnosed=diagnosed,
        stage=stage,
    )


# Outcome 与典型驱动的关联（用于按人物主导维度微调重要度）
_OUTCOME_FACTOR_HINTS: Dict[str, List[str]] = {
    "O1": ["A2", "A3", "A5", "A11", "B7"],
    "O2": ["B1", "A4", "A6"],
    "O3": ["B2", "B4", "B9", "B10"],
    "O4": ["A1", "A5"],
    "O5": ["A8", "B6", "A1"],
    "O6": ["A7", "A9", "B8", "B5"],
    "O7": ["B3", "B7"],
    "O8": ["B11", "A9", "B4"],
    "O9": ["A10"],
}

# 阶段越靠前，诊断/确认类越不满意；越靠后，适配/售后类越突出
_STAGE_SAT_BIAS: Dict[str, Dict[str, int]] = {
    "未察觉": {"O1": -2, "O2": -1, "O7": 0},
    "察觉": {"O1": -1, "O2": -1, "O4": -1, "O5": -1},
    "就医确诊": {"O1": 2, "O2": 0, "O7": -1},
    "决策纠结": {"O6": -2, "O3": -1, "O8": -1, "O7": -1},
    "购买": {"O6": 1, "O3": -1, "O8": -2},
    "适应": {"O3": -2, "O2": 1, "O8": 0},
    "依从习惯": {"O3": 1, "O2": 2, "O7": 1},
}


def _clamp_score(v: int, lo: int = 1, hi: int = 10) -> int:
    return max(lo, min(hi, int(v)))


def _score_desired_outcomes(arch: Dict, *, salt: str = "") -> List[DesiredOutcome]:
    """
    按 Job / 阶段 / 主导维度 / 价格敏感度 拉开 importance·satisfaction，
    避免全员同款 9/2、8/3、7/4。
    """
    jt = arch.get("jtbd") or {}
    job = get_job(jt.get("job_id", ""))
    desired_ids = list(jt.get("desired_outcome_ids") or (job.outcome_ids if job else []))[:5]
    if not desired_ids:
        return []

    # 稳定随机：同一原型+盐值可复现，不同人不同分布
    rng = random.Random(f"{arch.get('key','')}|{salt}|{','.join(desired_ids)}")
    stage = arch.get("stage", "")
    dominant = set(arch.get("dominant") or [])
    forces = jt.get("forces") or {}
    push = set(forces.get("push") or [])
    pull = set(forces.get("pull") or [])
    anxiety = set(forces.get("anxiety") or [])
    price_sens = int((arch.get("mindset") or {}).get("price_sensitivity") or 5)
    blockers = " ".join(arch.get("blockers") or [])
    drivers = " ".join(arch.get("drivers") or [])
    kind = _arch_kind(arch)

    # 显式覆盖（原型可写 outcome_scores: {O4: {importance, satisfaction}}）
    overrides = jt.get("outcome_scores") or {}

    scored: List[DesiredOutcome] = []
    for rank, oid in enumerate(desired_ids):
        if oid in overrides:
            ov = overrides[oid]
            scored.append(
                DesiredOutcome(
                    id=oid,
                    importance=_clamp_score(ov.get("importance", 7)),
                    satisfaction=_clamp_score(ov.get("satisfaction", 4)),
                )
            )
            continue

        # —— 重要度：列表位次只作弱基线，再用故事要素拉开 ——
        importance = 7 - min(rank, 2)  # 7/6/5 …
        hints = set(_OUTCOME_FACTOR_HINTS.get(oid, []))
        # 主导/push 对齐 → 更在乎
        overlap_dom = len(hints & dominant)
        overlap_push = len(hints & push)
        importance += overlap_dom * 1 + overlap_push * 2
        if oid in ("O6",) and price_sens >= 8:
            importance += 2
        elif oid in ("O6",) and price_sens <= 3:
            importance -= 2
        if oid == "O4" and kind == "spouse":
            importance += 2
        if oid == "O5" and kind in ("filial", "als_care"):
            importance += 2
        if oid == "O9" and kind == "als_care":
            importance += 3
        if oid == "O3" and any(k in blockers + drivers for k in ("面罩", "戴", "不适", "闲置")):
            importance += 1
        if oid == "O8" and any(k in blockers + drivers for k in ("闲置", "试", "浪费", "二手")):
            importance += 1
        if oid == "O2" and any(k in drivers for k in ("白天", "嗜睡", "确认", "数据")):
            importance += 1
        if oid == "O1" and stage in ("未察觉", "察觉"):
            importance += 1
        # 人物微扰
        importance += rng.choice([-1, 0, 0, 1, 1])

        # —— 满意度：阶段偏见 + 焦虑未解则更低 ——
        satisfaction = 4 + rng.choice([-1, 0, 0, 1])
        for k, delta in (_STAGE_SAT_BIAS.get(stage) or {}).items():
            if k == oid:
                satisfaction += delta
        # 相关 anxiety 未解除 → 满意更低
        if hints & anxiety:
            satisfaction -= 2
        if hints & pull and stage in ("决策纠结", "购买", "适应"):
            satisfaction += 1  # 已在找解决方案，略有着落感
        if oid == "O9" and kind == "als_care":
            satisfaction = min(satisfaction, 2)  # 保命缺口始终很尖锐
        if oid == "O4" and kind == "spouse" and stage in ("察觉", "决策纠结"):
            satisfaction = min(satisfaction, 3)
        if oid == "O6" and price_sens >= 8:
            satisfaction = min(satisfaction, 3)
        # 列表越往后通常不是最疼，满意可略高
        satisfaction += min(rank, 2)
        satisfaction += rng.choice([-1, 0, 0, 1])

        # 保证缺口存在：最靠前的至少差 2 分
        importance = _clamp_score(importance, 4, 10)
        satisfaction = _clamp_score(satisfaction, 1, 8)
        satisfaction = min(satisfaction, importance)  # 满意不超过在乎
        if rank == 0 and importance - satisfaction < 2:
            satisfaction = _clamp_score(importance - 2 - rng.choice([0, 1]), 1, 8)
        if rank == 0 and importance < 7:
            importance = _clamp_score(importance + rng.choice([1, 2]), 7, 10)
            satisfaction = min(satisfaction, importance - 1)

        scored.append(DesiredOutcome(id=oid, importance=importance, satisfaction=satisfaction))

    # 按「缺口」重排展示顺序（不改 ids 集合）：最渴的排前面，UI 更直观
    scored.sort(key=lambda d: (d.satisfaction / max(d.importance, 1), -d.importance))
    return scored


def _build_jtbd(arch: Dict, *, salt: str = "") -> JTBDProfile:
    jt = arch.get("jtbd") or {}
    job = get_job(jt.get("job_id", ""))
    sub_map = {s.id: s for s in load_sub_jobs()}
    step_id = jt.get("current_step_id", "")
    step_name = sub_map[step_id].name if step_id in sub_map else ""

    desired = _score_desired_outcomes(arch, salt=salt)

    forces_raw = jt.get("forces") or {}
    forces = ForceMap(
        push=list(forces_raw.get("push", [])),
        pull=list(forces_raw.get("pull", [])),
        anxiety=list(forces_raw.get("anxiety", [])),
        habit_or_alternative=list(forces_raw.get("habit_or_alternative", [])),
    )

    return JTBDProfile(
        entry_situation=jt.get("entry_situation", ""),
        job_id=jt.get("job_id", ""),
        job_owner=jt.get("job_owner", ""),
        core_job=job.name if job else "",
        job_statement=job.statement if job else "",
        current_step=step_name,
        desired_outcomes=desired,
        forces=forces,
    )


def _persona_from_archetype(
    arch: Dict,
    index: int,
    factors: List[Factor],
    used_names: set,
) -> Persona:
    seed_name = arch["seed_name"]
    preferred = SEED_BY_NAME.get(seed_name) or PERSONA_SEEDS[index % len(PERSONA_SEEDS)]
    seed = _pick_unique_seed(
        seed_name,
        used_names,
        gender_hint=preferred.get("gender", ""),
        arch=arch,
    )
    role, subject, family = _align_role_subject_family(arch, seed)
    # 照护类复用到偏大年龄种子时，年龄也收到「子女」合理区间，避免 70 岁照护父亲
    age_lo, age_hi = seed["age_range"]
    if _arch_kind(arch) in ("filial", "als_care") and age_lo >= 55:
        age_lo, age_hi = 34, 48

    ms, blockers, drivers = _adapt_story_to_seed(
        arch, seed, subject=subject, family=family
    )
    dom = _dominant_from_archetype(arch, factors, role=role, subject=subject)
    primary_name = dom[0].name if dom else "这件事"
    jtbd = _build_jtbd(arch, salt=f"{seed['name']}|{index}|{family}")
    # job_owner 与角色对齐
    if _arch_kind(arch) in ("filial", "als_care"):
        jtbd.job_owner = "子女"
    elif _arch_kind(arch) == "spouse":
        jtbd.job_owner = "伴侣"

    return Persona(
        id=_persona_id(index + 1),
        name=seed["name"],
        emoji=seed["emoji"],
        segment=arch["segment"],
        role=role,
        subject=subject,
        age=random.randint(age_lo, age_hi),
        gender=seed["gender"],
        city=seed["city"],
        occupation=seed["occupation"],
        family=family,
        income=seed["income"],
        osa=_osa_for_archetype(arch),
        mindset=Mindset(**ms),
        dominant_features=[DominantFeature(code=f.id, weight=f.weight) for f in dom],
        factor_weights=_build_factor_weights(
            factors, dom, arch, role=role, subject=subject
        ),
        blockers=blockers,
        drivers=drivers,
        decision_style=arch["decision_style"],
        react=_react_from_archetype(arch, primary_name),
        jtbd=jtbd,
        evidence_refs=["synthetic", arch.get("key", "archetype")],
    )


def _resolve_job_filter(
    job_ids: Optional[List[str]],
    entry_themes: Optional[List[str]],
) -> Optional[List[str]]:
    resolved = set(job_ids or [])
    for theme in entry_themes or []:
        resolved.update(ENTRY_THEME_TO_JOBS.get(theme, []))
    return list(resolved) if resolved else None


def generate_personas_fallback(
    count: int,
    factors: List[Factor],
    *,
    job_ids: Optional[List[str]] = None,
    entry_situations: Optional[List[str]] = None,
    entry_themes: Optional[List[str]] = None,
    **_kwargs,
) -> List[Persona]:
    if not factors:
        raise ValueError("无可用维度")

    resolved_jobs = _resolve_job_filter(job_ids, entry_themes)
    archetypes = pick_archetypes(
        count, job_ids=resolved_jobs, entry_situations=entry_situations
    )
    archetypes = archetypes[:count]
    used_names: set = set()
    return [
        _persona_from_archetype(arch, i, factors, used_names)
        for i, arch in enumerate(archetypes)
    ]