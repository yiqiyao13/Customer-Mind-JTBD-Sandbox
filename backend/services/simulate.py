"""JTBD 驱动的 Campaign 仿真：以 Outcome / Force balance 判定，而非纯关键词命中。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from schemas import Factor, Outcome, Persona, SimulateResult
from services.job_store import load_outcomes, next_step_name, resolve_step_name

# 阈值：抬高推进门槛，避免「试戴+国补」人人满分
ADVANCE_THRESHOLD = 14
HESITATE_THRESHOLD = 5
SOFT_ADVANCE_THRESHOLD = 11
# 单独出现时偏弱、不宜只靠 soft 大面积 advance
WEAK_INTERVENTIONS = frozenset({
    "financing",
    "mask_fit_support",
    "material_hygiene",
    "trade_in",
    "trial",  # 试戴很香，但不能单独撑起全员推进
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
        "keywords": [
            "数据", "报告", "小程序", "app", "同步", "AHI", "可视化", "监测记录",
            "算法", "口径", "可导出", "原始数据", "漏气补偿", "疗效验证", "可核对",
        ],
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
        # 禁止用「一起」「家庭」等泛词，否则「一起去爬山」会误触发
        "outcomes": ["O4"],
        "forces": [("A1", "push", 2)],
        "keywords": [
            "伴侣", "分房", "夫妻", "老公", "老婆",
            "一起选", "一起试戴", "一起看设备", "全家一起选",
            "家人陪同", "家人陪着", "家庭方案", "夫妻共同",
        ],
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
        "outcomes": ["O10"],
        "forces": [("B6", "pull", 2), ("A11", "anxiety", -2)],
        "keywords": ["体面", "不丢人", "隐形", "名人", "明星", "小巧", "外观低调", "匿名"],
    },
    # 恢复连续睡眠 / 告别被吵醒：呼吸机最根本的价值主张
    "sleep_continuity": {
        "outcomes": ["O1", "O3"],
        "forces": [("A1", "push", 2), ("A4", "push", 1)],
        "keywords": [
            "安静整觉", "安静的整觉", "整觉", "连续睡眠", "不被打断",
            "告别鼾声", "鼾声打断", "鼾声", "打呼吵醒", "室友打呼",
            "睡整晚", "睡个好觉", "睡得好", "改善睡眠", "一觉到天亮",
            "不再被吵醒", "不被吵醒", "被吵醒", "睡不着", "吵得你睡",
            "安静睡眠", "还你一个安静", "告别吵醒", "睡个整觉",
        ],
    },
    # 先诊断/搞清严重度：正向引导，不是劝退
    "diagnosis_clarity": {
        "outcomes": ["O1"],
        "forces": [("B7", "pull", 1)],
        "keywords": [
            "睡眠监测", "多导睡眠", "筛查", "先查清楚", "先搞清楚",
            "搞清楚是不是病", "到底是不是病", "有多严重", "先诊断",
            "搞清楚到底", "再决定买不买", "再决定用不用买",
        ],
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

# 劝阻 / 反向话术信号：与「跑题无关」区分，命中则倾向「拒绝」
# 注意：勿用过短子串；「不是病」会误伤「是不是病」——见 detect_negative_signals 遮罩
NEGATIVE_SIGNAL_KEYWORDS = [
    "不用买", "不要买", "别买", "不买也行", "没必要买", "没必要花",
    "用不着", "不需要呼吸机", "不用花", "别花这个钱", "省省吧",
    "冤枉钱", "浪费钱", "智商税", "忽悠", "坑人",
    "不是大毛病", "不是病", "小题大做", "忍忍就行", "忍一忍",
    "戴了也没用", "治不治无所谓", "打呼噜正常", "打鼾正常",
]

# 诊断/延后决策语境：先遮罩，再匹配负面词，避免「是不是病」「用不用买」误伤
# 较长短语优先（detect 时按长度降序替换）
_DIAGNOSTIC_SAFE_PHRASES = (
    "搞清楚到底是不是病",
    "搞清楚是不是病",
    "到底是不是病",
    "是不是病",
    "先搞清楚再决定",
    "先搞清楚",
    "先查清楚",
    "再决定买不买",
    "再决定用不用买",
    "决定买不买",
    "决定用不用买",
    "用不用买",
    "买不买",
    "有多严重",
    "先做个睡眠监测",
    "做个睡眠监测",
    "睡眠监测",
    "多导睡眠",
    "先诊断再",
    "先筛查",
)

# 较强正向干预：即使话术里夹杂负面词，仍可能被这些拉回犹豫/推进
STRONG_POSITIVE_INTERVENTIONS = frozenset({
    "hospital_endorsement",
    "trial",
    "data_visibility",
    "life_support",
    "after_sales",
    "mask_fit_support",
    "sleep_continuity",
    "diagnosis_clarity",
})

INTERVENTION_LABELS = {
    "hospital_endorsement": "医院/专家背书",
    "data_visibility": "数据可见",
    "trial": "试戴/试用",
    "mask_fit_support": "面罩适配支持",
    "family_participation": "家庭共同参与",
    "filial_care": "孝道照护",
    "financing": "分期/补贴/优惠",
    "trade_in": "以旧换新",
    "after_sales": "售后保障",
    "life_support": "重症呼吸支持",
    "shame_relief": "减轻社交压力",
    "sleep_continuity": "连续睡眠/告别吵醒",
    "diagnosis_clarity": "先诊断/搞清严重度",
    "material_hygiene": "材质与卫生",
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


# 「一起试戴」等家庭复合词里的「试戴」不应再单独触发 trial
_FAMILY_EMBEDDED_TRIAL_PHRASES = (
    "一起试戴",
    "一起看设备",
    "全家一起选",
    "夫妻一起选",
    "家人陪同试戴",
)


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
    # 去掉被家庭话术「借壳」触发的 trial
    if "trial" in active and "family_participation" in active:
        stripped = text
        for phr in _FAMILY_EMBEDDED_TRIAL_PHRASES:
            stripped = stripped.replace(phr.lower(), " ")
        trial_kws = INTERVENTION_MAP["trial"].get("keywords", [])
        if not any(kw.lower() in stripped for kw in trial_kws):
            active = [k for k in active if k != "trial"]
    return active


def detect_negative_signals(campaign: str) -> List[str]:
    """劝阻信号检测：先遮罩诊断/延后决策语境，再做子串匹配。

    避免「搞清楚到底是不是病」「再决定买不买」被「不是病」「不用买」误伤。
    """
    text = campaign or ""
    masked = text
    for phrase in sorted(_DIAGNOSTIC_SAFE_PHRASES, key=len, reverse=True):
        if phrase in masked:
            masked = masked.replace(phrase, "〔诊〕")
    # 额外：否定问句「是不是病」残留（顿号/标点打断长短语时）
    for frag in ("是不是病", "用不用买", "买不买"):
        masked = masked.replace(frag, "〔诊〕")
    lowered = masked.lower()
    return [kw for kw in NEGATIVE_SIGNAL_KEYWORDS if kw.lower() in lowered]


def intervention_label(key: str) -> str:
    return INTERVENTION_LABELS.get(key, key)


def _interventions_for_persona(active: List[str], persona: Persona) -> List[str]:
    """按人设过滤不适用的干预，避免「夫妻话术」推动室友受害者等反向命中。"""
    role = persona.role or ""
    out: List[str] = []
    for key in active:
        if key == "life_support" and persona.jtbd.job_id != "J4":
            continue
        if key == "filial_care" and persona.jtbd.job_id not in ("J7", "J4"):
            continue
        # 室友受害者：夫妻/分房话术完全不适用
        if key == "family_participation" and "室友" in role:
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
    """关键 Outcome：缺口（importance−satisfaction）优先，Job/分群偏好仅作同分加权。

    避免「分群标签写错 → 关键缺口被硬锁成错误 Outcome」的连锁误判。
    """
    dos = persona.jtbd.desired_outcomes
    if not dos:
        return None

    preferred: List[str] = []
    jid = persona.jtbd.job_id or ""
    seg = persona.segment or ""
    role = persona.role or ""
    drivers = " ".join(persona.drivers or [])
    dom = {d.code for d in (persona.dominant_features or [])}

    # Job / 角色优先（比 segment 标签更可靠）
    if jid == "J6" or "社交尊严" in drivers or "A11" in dom:
        preferred = ["O10", "O8"]
    elif jid == "J5" and "室友" not in role:
        preferred = ["O4", "O3"]
    elif jid == "J1" or "室友" in role or seg == "场景干扰型":
        preferred = ["O1", "O3", "O6"]
    elif jid == "J4":
        preferred = ["O9", "O7"]
    elif jid == "J7" or "子女" in role:
        preferred = ["O5", "O7"]
    elif seg == "专业验证型" or any(
        x in drivers for x in ("AHI数据", "疗效可验证", "数据可见性", "算法")
    ):
        preferred = ["O2"]
    elif seg == "经济受限型" or jid == "J2":
        preferred = ["O6", "O8"] if seg == "经济受限型" else ["O2", "O3", "O8"]
    elif jid == "J3" or seg == "健康焦虑自用型":
        preferred = ["O2", "O3"]
    elif seg == "关系驱动型" and "伴侣" in role:
        preferred = ["O4", "O3"]
    elif seg == "长期照护型" and ("子女" in role or "照护" in role):
        preferred = ["O5", "O7"]

    pref_set = set(preferred)

    def _score(d):
        gap = d.importance - d.satisfaction
        # 同分时：在偏好列表里的靠前；仍不覆盖更大缺口
        pref_bonus = 0
        if d.id in pref_set:
            pref_bonus = 1 + max(0, 3 - preferred.index(d.id))
        return (gap, pref_bonus, d.importance)

    return max(dos, key=_score)


def _outcome_short(oid: str, outcomes: List[Outcome]) -> str:
    for o in outcomes:
        if o.id == oid:
            if o.label:
                return o.label
            m = None
            if "「" in (o.name or ""):
                try:
                    m = o.name.split("「", 1)[1].split("」", 1)[0]
                except Exception:
                    m = None
            return m or o.name or oid
    return oid


def _high_importance_coverage(persona: Persona, improved_set: set[str]) -> bool:
    """高重要度 Outcome 至少半数被回应，才允许推进。"""
    high = [d for d in persona.jtbd.desired_outcomes if d.importance >= 7]
    if not high:
        return True
    hit = sum(1 for d in high if d.id in improved_set)
    need = max(1, (len(high) + 1) // 2)
    return hit >= need


def _human_reasoning(
    persona: Persona,
    decision: str,
    improved: List[str],
    unresolved: List[str],
    next_step: str,
    outcomes: List[Outcome],
) -> str:
    """市场可读的内心独白，禁止 O编码 / Force balance 等实现术语。"""
    imp = "、".join(_outcome_short(i, outcomes) for i in improved) or "还没有真正打到点上"
    unr = "、".join(_outcome_short(i, outcomes) for i in unresolved)
    step = next_step or persona.jtbd.current_step or "下一步"
    if decision == "advance":
        extra = f"还挂着：{unr}。" if unr else "关键顾虑这轮基本对上了。"
        return f"这句话里，「{imp}」对我有用。{extra}我可以先往「{step}」走一步。"
    if decision == "hesitate":
        return (
            f"有听到「{imp}」，但我最卡的「{unr or persona.jtbd.current_step}」还没说透。"
            f"暂时还在「{persona.jtbd.current_step or '纠结'}」，不会立刻下单。"
        )
    if decision == "reject":
        return f"我真正在乎的是「{unr or persona.jtbd.core_job}」，这段推广几乎没碰到，倾向先放放。"
    return f"跟我现在在忙的「{persona.jtbd.core_job or '这件事'}」关系不大。"


def _scene_phrase(persona: Persona) -> str:
    """口语场景，禁止把「丈夫42岁(中度OSA)+一子」原样塞进反馈。"""
    role = persona.role or ""
    if "子女" in role:
        return "给长辈选设备这件事"
    if "室友" in role:
        return "被室友鼾声吵醒这件事"
    if "伴侣" in role or "家人" in role or "照护" in role:
        return "家里推动治疗这件事"
    return "我自己的睡眠治疗这件事"


def _pick_reaction(persona: Persona, decision: str, topic: str) -> str:
    """按角色/家庭/恐惧拼口语，避免全员同一机器人句式。"""
    j = persona.jtbd
    job = j.core_job or persona.segment
    step = j.current_step or "当前这步"
    blocker = (persona.blockers or ["心里没底"])[0]
    fear = (persona.mindset.fear or "").strip()
    quote_bit = (persona.mindset.quote or "").strip().strip("「」")
    role = persona.role
    occ = persona.occupation or ""
    scene = _scene_phrase(persona)

    if "子女" in role:
        identity = f"我是{occ or '子女'}，在给长辈盯设备"
    elif "室友" in role:
        identity = f"我是被室友鼾声折磨的{occ or '合租党'}"
    elif "伴侣" in role or "家人" in role or "照护" in role:
        identity = f"我是家里在推动这件事的人（{occ or '家属'}）"
    else:
        identity = f"我自己（{occ or '患者'}）"

    # 人格模板若是「听到…这正好推进」机器人句，一律不用
    tpl = getattr(persona.react, decision, "") or ""
    robotic = any(
        x in tpl
        for x in ("这正好推进", "想深入了解", "有点相关", "跟我现在的任务关系不大")
    )
    if tpl and ("{{topic}}" in tpl or "{topic}" in tpl) and not robotic:
        return tpl.replace("{{topic}}", topic).replace("{topic}", topic)

    fear_bit = _fear_clause(fear, blocker)
    # 引号内已带句末标点时不再在」外补「。」，避免「。」。」
    if quote_bit:
        qb = quote_bit.rstrip("。！？.!?")
        quote_tail = f"我心里那句一直是：「{qb}」。"
    else:
        quote_tail = ""
    discourage = any(x in (topic or "") for x in ("不用买", "忍忍", "别买", "劝阻"))

    by_decision = {
        "advance": (
            f"{identity}。就{scene}，我卡在「{step}」好久了。"
            f"你们提到的「{topic}」算对上了我在做的「{job}」——"
            f"{fear_bit}，这点要是能落地，我愿意先往下走。{quote_tail}"
        ),
        "hesitate": (
            f"{identity}。{scene}还搁在「{step}」。"
            f"「{topic}」听着沾边，但{fear_bit}，这话没解开。"
            f"对「{job}」来说，还差一口气，我得再想想。{quote_tail}"
        ),
        "reject": (
            (
                f"{identity}。你们这是在劝我「{topic}」，等于否定我正在做的「{job}」。"
                f"{fear_bit}，这种说法我听着抵触，更不会往下走。{quote_tail}"
            )
            if discourage
            else (
                f"{identity}。你们讲的「{topic}」跟我真正卡的「{step}」不是一回事。"
                f"{fear_bit}，这段几乎没答到。{quote_tail}"
            )
        ),
        "na": (
            f"{identity}。这段话跟我正在忙的「{job}」基本不沾边，"
            f"我还是卡在「{step}」，先当没听到。"
        ),
    }
    return by_decision.get(decision, by_decision["hesitate"])


def _fear_clause(fear: str, blocker: str) -> str:
    """拼恐惧短句：避免「我最怕」+「最怕…」叠成「最怕最怕」，并去掉句末标点以免「。，」。"""
    f = (fear or "").strip().strip("「」\"'")
    f = f.rstrip("。．.，,；;！!？?")
    prefixes = (
        "我最怕", "我怕", "我最担心", "我担心",
        "最怕", "很怕", "特怕", "有点怕", "怕",
        "最担心", "担心",
    )
    # 可叠多层「最怕最怕」
    changed = True
    while changed and f:
        changed = False
        for prefix in prefixes:
            if f.startswith(prefix):
                f = f[len(prefix):].lstrip("的了，, ")
                changed = True
                break
    f = f.strip().rstrip("。．.，,；;！!？?")
    if not f:
        b = (blocker or "心里没底").strip().rstrip("。．.，,；;")
        for prefix in ("最怕", "怕"):
            if b.startswith(prefix):
                b = b[len(prefix):].lstrip("的了，, ")
        return f"我顾虑的是{b or '心里没底'}"
    return f"我最怕{f}"


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
    active_global = detect_interventions(campaign, interventions)
    active = _interventions_for_persona(active_global, persona)
    negative_hits = detect_negative_signals(campaign)
    has_strong_positive = any(k in STRONG_POSITIVE_INTERVENTIONS for k in active)
    # 劝阻话术主导时，清掉可能误触发的「改善」，避免爬山式误匹配又把关系算改善
    if negative_hits and not has_strong_positive:
        active = []

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

    # 话术触发的干预对该人设全部不适用（如室友听到夫妻话术）→ 无关，
    # 不要靠 factor 关键词（A1/B4）漂成犹豫/推进
    interventions_irrelevant = bool(active_global) and not active

    if negative_hits and not has_strong_positive:
        # 劝阻 / 反向宣传 → 拒绝（不是无关）
        decision = "reject"
        next_step = persona.jtbd.current_step
        topic = "不用买、忍忍就行这类说法"
        # 负面话术下不记「已改善」
        improved = []
        unresolved = [do.id for do in persona.jtbd.desired_outcomes]
        score = -5
    elif interventions_irrelevant or (not active and not hit_ids):
        # 完全跑题，或干预与人设互斥 → 无关
        decision = "na"
        next_step = persona.jtbd.current_step
        topic = "这个活动"
        improved = []
        unresolved = [do.id for do in persona.jtbd.desired_outcomes]
    else:
        required_addressed = True if not required else required.id in improved
        coverage_ok = _high_importance_coverage(persona, improved_set)

        # 诊断话术只打 O1：对卡在「搞清楚是不是病」的人，单点命中关键缺口即可算覆盖
        if (
            "diagnosis_clarity" in active
            and required
            and required.id == "O1"
            and required.id in improved_set
        ):
            coverage_ok = True
            score += 3.0

        anxiety_eased = any(
            f == fid and force == "anxiety" and delta < 0
            for fid in forces.anxiety
            for f, force, delta in force_deltas
        )
        pull_hit = any(fid in activated_force_ids for fid in forces.pull)
        push_hit = any(fid in activated_force_ids for fid in forces.push)
        only_weak = bool(active) and set(active).issubset(WEAK_INTERVENTIONS)

        # 推进必须：关键缺口被回应 + 高重要度覆盖过半 + 分数够；弱干预组合不能单独撑推进
        hard_advance = (
            score >= ADVANCE_THRESHOLD
            and required_addressed
            and coverage_ok
            and not only_weak
        )
        soft_advance = (
            score >= SOFT_ADVANCE_THRESHOLD
            and required_addressed
            and coverage_ok
            and (push_hit or pull_hit or anxiety_eased or len(improved) >= 2)
            and not only_weak
        )
        # 生命危急特例：重症保命话术仍可 soft
        if life_critical and required_addressed and score >= SOFT_ADVANCE_THRESHOLD:
            soft_advance = True

        # 夹杂劝阻词时，即使有弱命中也不给推进
        if negative_hits:
            hard_advance = False
            soft_advance = False

        if hard_advance or soft_advance:
            decision = "advance"
            next_step = next_step_name(persona.jtbd.current_step, persona.jtbd.job_id)
        elif score >= HESITATE_THRESHOLD or (active or hit_ids):
            # 有命中但没过推进门 → 犹豫（而不是轻易无关）
            decision = "hesitate" if (score >= HESITATE_THRESHOLD or required_addressed or improved) else "reject"
            if score < HESITATE_THRESHOLD and not improved:
                decision = "reject"
            if negative_hits:
                decision = "reject"
            next_step = persona.jtbd.current_step
        else:
            decision = "reject"
            next_step = persona.jtbd.current_step

        # 正向「先诊断」话术：遮罩后无真实劝阻时，不得因未覆盖其 Outcome 而 reject
        if (
            "diagnosis_clarity" in active
            and not negative_hits
            and decision == "reject"
        ):
            decision = "hesitate"
            next_step = persona.jtbd.current_step

        # 「改善睡眠」价值主张：有 Outcome 命中至少犹豫；零重叠（如重症保命）→ 无关，勿 reject
        if "sleep_continuity" in active and not negative_hits and decision == "reject":
            decision = "hesitate" if improved else "na"
            next_step = persona.jtbd.current_step

        if improved:
            topic = "、".join(_outcome_short(i, outcomes) for i in improved[:2])
        elif hit_ids:
            topic = "、".join(name_map.get(h, h) for h in hit_ids[:2])
        else:
            topic = "、".join(intervention_label(a) for a in active[:2]) if active else "这个活动"

    reaction = _pick_reaction(persona, decision, topic)

    dom_codes = [d.code for d in persona.dominant_features]
    hit_dom = [h for h in hit_ids if h in dom_codes]

    # 意愿分：与决策绑定，并对「高重要度未解决」扣分，禁止核心顾虑未解却 10 分
    unresolved_high = [
        d for d in persona.jtbd.desired_outcomes
        if d.id in unresolved and d.importance >= 7
    ]
    if decision == "advance":
        willingness = 6 + min(3, int(score // 6))
        willingness -= len(unresolved_high)
        willingness = max(6, min(9, willingness))  # 推进最高 9，满分留给几乎无未解
        if not unresolved:
            willingness = min(10, willingness + 1)
    elif decision == "hesitate":
        willingness = 4 + min(2, int(score // 6))
        willingness -= len(unresolved_high)
        willingness = max(3, min(6, willingness))
    elif decision == "na":
        willingness = max(1, min(4, 2 + int(score // 8)))
    else:
        willingness = max(1, min(3, 2 - len(unresolved_high) // 2))

    # 最关键 Outcome 未解 → 绝不能显示高意愿推进感
    if required and required.id in unresolved:
        willingness = min(willingness, 5)
        if decision == "advance":
            decision = "hesitate"
            reaction = _pick_reaction(persona, decision, topic)
            next_step = persona.jtbd.current_step

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
                reasoning=_human_reasoning(
                    persona, decision, improved, unresolved, next_step, outcomes
                ),
            )
        )

    # 对外返回中文干预名，避免 family_participation 等内部键
    active_labels = [intervention_label(k) for k in active_global]
    return results, summary, hit_names, active_labels
