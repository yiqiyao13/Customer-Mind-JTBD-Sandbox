from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from config import get_model_name, llm_configured
from schemas import Factor, Persona, SimulateResult
from services.job_store import load_outcomes, resolve_step_name
from services.llm import _client
from services.memory import get_memory_context
from services.simulate import decide_for, identify_factors, _required_outcome


def _required_outcome_brief(persona: Persona) -> str:
    req = _required_outcome(persona)
    if not req:
        return "无"
    outcomes = {o.id: o.name for o in load_outcomes()}
    return f"{req.id} {outcomes.get(req.id, '')}（重要{req.importance}/满意{req.satisfaction}）"


def _voice_card(persona: Persona) -> str:
    """浓缩「这个人怎么说话、卡在哪」——逼模型写差异化反馈。"""
    j = persona.jtbd
    return f"""姓名：{persona.name}（{persona.age}岁/{persona.gender}/{persona.occupation}）
家庭：{persona.family}
决策角色：{persona.role} → 对象：{persona.subject}
分群/风格：{persona.segment} · {persona.decision_style}
核心任务：{j.job_id} {j.core_job}
当前卡点 Step：{j.current_step}
起点情境：{j.entry_situation}
关键 Outcome（必须优先谈）：{_required_outcome_brief(persona)}
推动力 push：{", ".join(j.forces.push) or "无"}
焦虑 anxiety：{", ".join(j.forces.anxiety) or "无"}
障碍 blockers：{"；".join(persona.blockers) or "无"}
驱动力 drivers：{"；".join(persona.drivers) or "无"}
本人原话口吻：「{persona.mindset.quote or "（无）"}」
恐惧：{persona.mindset.fear}
决策逻辑：{persona.mindset.decision_logic}
价格敏感：{persona.mindset.price_sensitivity}/10 · 品牌锚：{persona.mindset.brand_anchor}
"""


def _build_simulate_prompt(
    persona: Persona,
    campaign: str,
    factors: List[Factor],
    campaign_hit_ids: List[str],
    rule_hint: dict,
    memory_context: str = "",
) -> str:
    hit_names = [f.name for f in factors if f.id in campaign_hit_ids]
    hint = json.dumps(rule_hint, ensure_ascii=False)
    outcomes_brief = "\n".join(f"- {o.id} {o.name}" for o in load_outcomes())

    return f"""你正在扮演下面这位**唯一**的消费者。你的反馈必须听起来像 TA，而不能像「通用客户服务话术」。

【此人专属声音卡 —— 写 reaction 时必须用到其中至少 2 个具体细节】
{_voice_card(persona)}

【经历记忆】
{memory_context or "（第一次接触，无过往）"}

【Outcome 词典】
{outcomes_brief}

【营销话术】
{campaign}

【规则引擎初判（可不同意）】
{hint}
话术可能命中维度：{", ".join(hit_names) if hit_names else "无"}

【硬性写作禁令 — 违反则不合格】
1. **禁止**所有人共用的套话开头，例如：「医院义诊？」「还能试用？」「正好戳中我…」「这段话提到了…」
2. **禁止**复述话术原句当开头；用自己的生活场景开场（家庭/职业/当前 Step/恐惧）。
3. **禁止**空泛说「有点相关」「得再想想」而不点名自己的 Job/障碍。
4. reaction 必须出现：① 自己的身份或家庭关系 ② 当前卡点或关键 Outcome 顾虑 ③ 对这句话里**对自己有用/没用**的一点的具体判断。
5. 不同人关注点必须不同：伴侣推动者谈分房/催促冲突；子女谈老人配合；本人谈嗜睡/丢人/数据；重症谈保命可靠——不要人人都只谈「怕买了浪费」。
6. 若**关键 Outcome**未解决 → 不要判 advance；可 hesitate/reject，并说清还缺什么。
7. 若规则引擎已判 advance，且你认可关键缺口已被话术回应 → 保持 advance，不要无脑降成 hesitate。
8. 意愿分必须贴合文案：若你写「光说没用/没碰我的卡点」→ willingness ≤4，decision 不得为 advance。
9. reasoning 用内心独白，写「我卡在…，这句话只解决了…，没解决…」，不要写成营销分析报告。

【口吻示例（仅示意差异，勿照抄）】
- 伴侣型：「他再这样我真要搬次卧了……义诊可以，可面罩合不合适你们说清楚没有？」
- 子女型：「我妈认死理，医生说她才肯动。远程教不会的话我买了也白搭。」
- 司机本人：「开会打瞌睡差点出事。试用可以，但别跟我绕弯讲情怀，总价和耗材说清楚。」
- 专业验证：「补贴进口我听过，但算法口径和报告能不能对上临床？对不上我不会动。」

【输出】只输出一个 JSON 对象：
{{
  "reaction": "2-4句口语第一人称，必须带此人细节",
  "reasoning": "内心推理2句：改善了什么、还卡在什么",
  "decision": "advance|hesitate|na|reject",
  "activated_factors": ["维度中文名"],
  "willingness": 1,
  "outcome_improved": ["O3"],
  "unresolved_outcomes": ["O8"],
  "next_step": "当前或下一步子任务中文名（禁止填字母 id）"
}}
"""


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    raise ValueError("无法从 LLM 响应中提取 JSON 对象")


_BANNED_OPENERS = (
    "医院义诊",
    "还能试用",
    "正好戳中",
    "这段话提到了",
    "这通电话提到了",
)


def _looks_generic(reaction: str) -> bool:
    if not reaction or len(reaction) < 12:
        return True
    return any(reaction.startswith(b) or b in reaction[:20] for b in _BANNED_OPENERS)


def _looks_positive(text: str) -> bool:
    markers = ("想了解", "可以试试", "正好", "推进", "靠谱", "愿意", "心动", "不错")
    return any(m in (text or "") for m in markers)


def _looks_negative(text: str) -> bool:
    markers = ("没用", "光说", "没碰", "别跟我", "不对口", "不相关", "跑题", "听着抵触", "不会往下")
    return any(m in (text or "") for m in markers)


def _sanitize_llm_result(
    *,
    decision: str,
    willingness: int,
    reaction: str,
    reasoning: str,
    improved: List[str],
    unresolved: List[str],
    next_step: str,
    rule_decision: str,
    rule_reaction: str,
    rule_w: int,
    rule_improved: List[str],
    rule_unresolved: List[str],
    rule_next: str,
    required_id: str = "",
) -> tuple[str, int, str, str, List[str], List[str], str]:
    """对齐意愿分/标签/字段，消除自相矛盾；双向门控避免一面倒犹豫。"""
    # 1) improved ∩ unresolved 互斥：优先保留 improved
    improved = list(dict.fromkeys(improved))
    unresolved = [x for x in dict.fromkeys(unresolved) if x not in set(improved)]
    if not improved and not unresolved:
        improved, unresolved = list(rule_improved), list(rule_unresolved)

    rule_core_ok = (not required_id) or (required_id in set(rule_improved))
    llm_core_ok = (not required_id) or (required_id in set(improved))

    # 2a) 单向：规则不能推进时，LLM 不得硬 advance
    if rule_decision in ("hesitate", "reject", "na") and decision == "advance":
        decision = rule_decision

    # 2b) 反向：规则已推进且关键缺口已回应时，禁止 LLM 无脑降成 hesitate
    if (
        rule_decision == "advance"
        and decision == "hesitate"
        and rule_core_ok
        and not _looks_negative(reaction)
    ):
        decision = "advance"
        if required_id and required_id not in improved:
            improved = list(dict.fromkeys([*improved, required_id]))
            unresolved = [x for x in unresolved if x != required_id]

    # 2c) 文案强烈否定时，不得维持高意愿 advance
    if _looks_negative(reaction) or _looks_negative(reasoning):
        if decision == "advance" and not llm_core_ok:
            decision = "hesitate"
        willingness = min(int(willingness), 4)

    # 3) 意愿分与标签绑定（统一阈值，避免同分不同标签）
    bands = {
        "advance": (6, 10),
        "hesitate": (3, 7),
        "na": (1, 5),
        "reject": (1, 3),
    }
    lo, hi = bands.get(decision, (1, 10))
    willingness = max(lo, min(hi, int(willingness)))
    # 与规则分靠近，但保留 LLM 文案带来的下调空间
    blend = 0.55 if decision == rule_decision else 0.35
    willingness = int(round((willingness * (1 - blend)) + (rule_w * blend)))
    willingness = max(lo, min(hi, willingness))
    if _looks_negative(reaction):
        willingness = min(willingness, 4 if decision != "reject" else 2)

    # 4) 文案与意愿不得打架
    if willingness <= 2 and _looks_positive(reaction):
        reaction = rule_reaction
        if not reasoning:
            reasoning = f"意愿很低（{willingness}/10），按规则侧「{rule_decision}」口径重述。"
    if decision == "reject" and _looks_positive(reaction) and willingness <= 3:
        reaction = rule_reaction

    if not next_step:
        next_step = rule_next

    return decision, willingness, reaction, reasoning, improved, unresolved, next_step


def _persona_seed(persona: Persona) -> int:
    return sum(ord(c) for c in (persona.id + persona.name)) % 1000


def _simulate_one_sync(
    persona: Persona,
    campaign: str,
    factors: List[Factor],
    campaign_hit_ids: List[str],
    rule_hint: dict,
    memory_context: str = "",
    interventions: Optional[List[str]] = None,
) -> SimulateResult:
    client = _client()
    if client is None:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")

    prompt = _build_simulate_prompt(
        persona, campaign, factors, campaign_hit_ids, rule_hint, memory_context
    )
    # 低温度 + 固定种子：降低同人两次漂移；文案仍可由人设细节区分
    seed = _persona_seed(persona)
    temp = 0.35
    resp = client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {
                "role": "system",
                "content": (
                    f"你只扮演{persona.name}，用其职业与家庭口吻说话。"
                    "禁止套话模板，禁止和其他客户说一样的开场。"
                    "willingness 必须与 decision 一致：advance≥6，hesitate 3-7，reject≤3。"
                    "outcome_improved 与 unresolved_outcomes 不得出现同一项。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temp,
        max_tokens=1024,
        seed=seed,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = resp.choices[0].message.content or ""
    raw = _extract_json_object(content)

    decision = str(raw.get("decision", "hesitate")).lower().split()[0]
    if decision not in ("advance", "hesitate", "na", "reject"):
        decision = "hesitate"

    name_map = {f.id: f.name for f in factors}
    (
        rule_decision,
        rule_reaction,
        hits,
        hit_dom,
        rule_w,
        rule_improved,
        rule_unresolved,
        rule_next,
        active,
    ) = decide_for(
        persona,
        campaign,
        factors,
        hit_ids=campaign_hit_ids,
        interventions=interventions,
    )

    reaction = str(raw.get("reaction", "")).strip()
    reasoning = str(raw.get("reasoning", "")).strip()

    # 套话 / 太空 → 回退到规则引擎的人设反应，避免全员同款
    if _looks_generic(reaction):
        reaction = rule_reaction
        if not reasoning:
            reasoning = (
                f"按我的任务「{persona.jtbd.core_job}」、卡点「{persona.jtbd.current_step}」判断；"
                f"规则侧倾向 {rule_decision}。"
            )
        decision = rule_decision

    improved = [str(x) for x in raw.get("outcome_improved", [])] or list(rule_improved)
    unresolved = [str(x) for x in raw.get("unresolved_outcomes", [])] or list(rule_unresolved)
    next_step = str(raw.get("next_step") or rule_next or persona.jtbd.current_step)
    next_step = resolve_step_name(next_step, persona.jtbd.job_id)

    try:
        willingness = int(raw.get("willingness", rule_w or 5))
    except (TypeError, ValueError):
        willingness = rule_w or 5

    req = _required_outcome(persona)
    decision, willingness, reaction, reasoning, improved, unresolved, next_step = _sanitize_llm_result(
        decision=decision,
        willingness=willingness,
        reaction=reaction,
        reasoning=reasoning,
        improved=improved,
        unresolved=unresolved,
        next_step=next_step,
        rule_decision=rule_decision,
        rule_reaction=rule_reaction,
        rule_w=rule_w,
        rule_improved=rule_improved,
        rule_unresolved=rule_unresolved,
        rule_next=rule_next,
        required_id=(req.id if req else ""),
    )

    # 去掉业务界面不该出现的内部编码
    if (not reasoning) or any(
        x in reasoning
        for x in ("Force balance", "Outcome 门控", "O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8", "O9")
    ):
        from services.simulate import _human_reasoning

        try:
            reasoning = _human_reasoning(
                persona, decision, improved, unresolved, next_step, load_outcomes()
            )
        except Exception:
            reasoning = (
                f"话术对上了部分顾虑；"
                f"{'仍有未解开心结，先观望。' if unresolved else '可以先往下一步走。'}"
            )

    return SimulateResult(
        persona_id=persona.id,
        persona_name=persona.name,
        decision=decision,
        reaction=reaction,
        hit_factors=[name_map[h] for h in hits if h in name_map],
        hit_dominant=[name_map[h] for h in hit_dom if h in name_map],
        willingness=willingness,
        reasoning=reasoning,
        activated_factors=[str(x) for x in raw.get("activated_factors", [])],
        mode="llm",
        outcome_improved=improved,
        unresolved_outcomes=unresolved,
        next_step=next_step,
        interventions=active,
    )


async def simulate_persona_llm(
    persona: Persona,
    campaign: str,
    factors: List[Factor],
    campaign_hit_ids: List[str],
    rule_hint: dict,
    memory_context: str = "",
    interventions: Optional[List[str]] = None,
) -> SimulateResult:
    return await asyncio.to_thread(
        _simulate_one_sync,
        persona,
        campaign,
        factors,
        campaign_hit_ids,
        rule_hint,
        memory_context,
        interventions,
    )


async def simulate_campaign_llm(
    campaign: str,
    personas: List[Persona],
    factors: List[Factor],
    persona_ids: List[str] | None = None,
    use_memory: bool = False,
    interventions: Optional[List[str]] = None,
) -> tuple[List[SimulateResult], dict, List[str], List[str]]:
    if not llm_configured():
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY，无法使用 LLM 独立思考模式（请检查 consumer_ai_sim/.env）"
        )

    enabled = [f for f in factors if f.enabled]
    campaign_hits = identify_factors(campaign, enabled)
    hit_names = [f.name for f in enabled if f.id in campaign_hits]

    targets = personas
    if persona_ids:
        id_set = set(persona_ids)
        targets = [p for p in personas if p.id in id_set]

    tasks = []
    active_global: List[str] = []
    for persona in targets:
        (
            decision,
            _,
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
        )
        if not active_global:
            active_global = active
        rule_hint = {
            "suggested_decision": decision,
            "willingness_hint": willingness,
            "keyword_hits": hit_names,
            "dominant_hits": [f.name for f in enabled if f.id in hit_dom],
            "outcome_improved": improved,
            "unresolved_outcomes": unresolved,
            "next_step": next_step,
            "interventions": active,
            "must_mention": [
                persona.role,
                persona.jtbd.current_step,
                persona.blockers[:1],
            ],
        }
        mem_ctx = get_memory_context(persona.id, campaign) if use_memory else ""
        tasks.append(
            simulate_persona_llm(
                persona,
                campaign,
                enabled,
                campaign_hits,
                rule_hint,
                mem_ctx,
                interventions,
            )
        )

    results = await asyncio.gather(*tasks)
    summary = {"advance": 0, "hesitate": 0, "na": 0, "reject": 0}
    for r in results:
        summary[r.decision] = summary.get(r.decision, 0) + 1
    from services.simulate import intervention_label

    active_labels = [intervention_label(k) for k in active_global]
    return list(results), summary, hit_names, active_labels
