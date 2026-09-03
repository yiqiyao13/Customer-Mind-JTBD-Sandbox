from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from schemas import MemoryEntry, Persona, PersonaEvolution, SimulateResult

ROOT = Path(__file__).resolve().parents[2]
EVOLUTION_PATH = ROOT / "data" / "evolution.json"

STAGE_ORDER = [
    "未察觉",
    "察觉",
    "就医确诊",
    "决策纠结",
    "购买",
    "适应",
    "依从习惯",
    "复购更换",
    "闲置转让",
]

_evolution: Dict[str, PersonaEvolution] = {}


def _load() -> Dict[str, PersonaEvolution]:
    global _evolution
    if EVOLUTION_PATH.exists():
        with open(EVOLUTION_PATH, encoding="utf-8") as f:
            raw = json.load(f)
            _evolution = {k: PersonaEvolution.model_validate(v) for k, v in raw.items()}
    return _evolution


def _save() -> None:
    EVOLUTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVOLUTION_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {k: v.model_dump() for k, v in _evolution.items()},
            f,
            ensure_ascii=False,
            indent=2,
        )


def get_evolution(persona_id: str) -> PersonaEvolution:
    if not _evolution:
        _load()
    if persona_id not in _evolution:
        _evolution[persona_id] = PersonaEvolution(persona_id=persona_id)
    return _evolution[persona_id]


def _importance_for_result(result: SimulateResult) -> int:
    base = {"advance": 8, "hesitate": 6, "reject": 7, "na": 3}.get(result.decision, 5)
    if result.willingness and result.willingness >= 8:
        base = min(10, base + 1)
    return base


def record_campaign_experience(
    persona: Persona,
    campaign: str,
    result: SimulateResult,
) -> MemoryEntry:
    evo = get_evolution(persona.id)
    evo.day += 1
    snippet = campaign[:80] + ("…" if len(campaign) > 80 else "")
    reasoning = f" 内心：{result.reasoning}" if result.reasoning else ""
    step_before = persona.jtbd.current_step
    content = (
        f"第{evo.day}天，看到营销话术「{snippet}」。"
        f"当时卡在「{step_before}」。"
        f"我的反应：{result.reaction}{reasoning}"
    )
    outcome_changes = [
        {"outcome_id": oid, "delta_satisfaction": 2} for oid in (result.outcome_improved or [])
    ] + [
        {"outcome_id": oid, "delta_satisfaction": 0}
        for oid in (result.unresolved_outcomes or [])
    ]
    force_changes = [
        {"factor_id": "", "force": "intervention", "delta": 1, "name": iv}
        for iv in (result.interventions or [])
    ]
    entry = MemoryEntry(
        id=f"m_{uuid.uuid4().hex[:8]}",
        day=evo.day,
        type="observation",
        content=content,
        importance=_importance_for_result(result),
        source="simulation",
        decision=result.decision,
        willingness=result.willingness,
        step_before=step_before,
        outcome_changes=outcome_changes,
        force_changes=force_changes,
    )
    evo.memories.append(entry)
    _maybe_advance_jtbd_step(persona, result)
    _maybe_advance_stage(persona, result)
    _maybe_reflect(evo)
    _save()
    return entry


def _maybe_advance_jtbd_step(persona: Persona, result: SimulateResult) -> None:
    """advance 时推进 current_step，并略微提升已改善 Outcome 的满意度。"""
    if result.decision != "advance":
        return
    if result.next_step and result.next_step != persona.jtbd.current_step:
        persona.jtbd.current_step = result.next_step
    for do in persona.jtbd.desired_outcomes:
        if do.id in (result.outcome_improved or []):
            do.satisfaction = min(10, do.satisfaction + 2)


def _maybe_advance_stage(persona: Persona, result: SimulateResult) -> None:
    """根据多次经历推动决策阶段（Day 1+ 人会变）。"""
    stage = persona.osa.stage
    if stage not in STAGE_ORDER:
        return
    idx = STAGE_ORDER.index(stage)

    evo = get_evolution(persona.id)
    recent = [m for m in evo.memories[-5:] if m.type == "observation"]
    advances = sum(1 for m in recent if m.decision == "advance")

    new_stage = stage
    if result.decision == "advance" and result.willingness and result.willingness >= 7:
        if stage in ("未察觉", "察觉") and advances >= 1:
            new_stage = "决策纠结"
        elif stage == "决策纠结" and advances >= 2:
            new_stage = "购买"
        elif stage == "购买":
            new_stage = "适应"
    elif result.decision == "hesitate" and stage == "未察觉":
        new_stage = "察觉"

    if new_stage != stage and STAGE_ORDER.index(new_stage) > idx:
        persona.osa.stage = new_stage
        if new_stage in ("就医确诊", "购买", "适应", "依从习惯"):
            persona.osa.diagnosed = True


def _maybe_reflect(evo: PersonaEvolution) -> None:
    """记忆积累到阈值时，合成高层信念（斯坦福 Reflection 简化版）。"""
    obs = [m for m in evo.memories if m.type == "observation"]
    if len(obs) < 3 or len(obs) % 3 != 0:
        return

    recent = obs[-3:]
    decisions = [m.decision for m in recent if m.decision]
    adv = decisions.count("advance")
    hes = decisions.count("hesitate")

    if adv >= 2:
        belief = "综合来看，我最近对呼吸机购买越来越心动，可能在近期做决定。"
    elif hes >= 2:
        belief = "综合来看，我仍在观望——话术听了不少，但核心顾虑还没被解决。"
    elif decisions.count("reject"):
        belief = "综合来看，我对这类营销越来越警惕，短期不太会行动。"
    else:
        belief = "综合来看，这件事还在我的关注边缘，没有强烈行动意愿。"

    if belief not in evo.reflections:
        evo.reflections.append(belief)
        evo.memories.append(
            MemoryEntry(
                id=f"r_{uuid.uuid4().hex[:8]}",
                day=evo.day,
                type="reflection",
                content=belief,
                importance=8,
                source="reflection",
            )
        )


def _keyword_overlap(a: str, b: str) -> float:
    wa = set(a.lower())
    wb = set(b.lower())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def retrieve_memories(persona_id: str, query: str, k: int = 5) -> List[MemoryEntry]:
    """斯坦福检索简化版：近期性 + 重要性 + 相关性；observed 优先于 simulation。"""
    evo = get_evolution(persona_id)
    if not evo.memories:
        return []

    now_idx = evo.day or 1
    scored: List[tuple[float, MemoryEntry]] = []
    for m in evo.memories:
        age = max(0, now_idx - m.day)
        recency = math.exp(-0.3 * age)
        importance = m.importance / 10.0
        relevance = _keyword_overlap(query, m.content)
        source_boost = 0.15 if m.source == "observed" else 0.0
        score = 0.30 * recency + 0.30 * importance + 0.25 * relevance + source_boost
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:k]]


def record_verification(
    persona_id: str,
    *,
    status: str,
    note: str = "",
    campaign: str = "",
    decision: Optional[str] = None,
) -> MemoryEntry:
    """真实验证回写：已验证 / 未验证 / 方向相反。"""
    evo = get_evolution(persona_id)
    evo.day += 1
    label = {"verified": "已验证", "unverified": "未验证", "opposite": "方向相反"}.get(
        status, status
    )
    content = f"真实验证：{label}。"
    if campaign:
        content += f" 相关 campaign：{campaign[:60]}。"
    if note:
        content += f" 证据：{note}"
    entry = MemoryEntry(
        id=f"v_{uuid.uuid4().hex[:8]}",
        day=evo.day,
        type="observation",
        content=content,
        importance=9 if status == "opposite" else 8,
        source="observed",
        decision=decision,
    )
    evo.memories.append(entry)
    _save()
    return entry


def get_memory_context(persona_id: str, query: str) -> str:
    """供 LLM 注入的「你最近的经历与信念」。"""
    evo = get_evolution(persona_id)
    retrieved = retrieve_memories(persona_id, query)
    lines = []
    if evo.reflections:
        lines.append("【已形成信念】")
        for r in evo.reflections[-3:]:
            lines.append(f"- {r}")
    if retrieved:
        lines.append("【相关经历（按记忆检索）】")
        for m in retrieved:
            tag = "反思" if m.type == "reflection" else f"第{m.day}天"
            lines.append(f"- ({tag}) {m.content}")
    if evo.day:
        lines.append(f"【当前旅程】已度过 {evo.day} 天，决策阶段以最新画像为准。")
    return "\n".join(lines) if lines else "（尚无经历，这是第一次接触此类信息）"


def list_all_memories(persona_id: str) -> PersonaEvolution:
    return get_evolution(persona_id)


def reset_evolution(persona_id: Optional[str] = None) -> int:
    """清除记忆，返回清除条目数。"""
    global _evolution
    if not _evolution:
        _load()
    if persona_id:
        evo = _evolution.pop(persona_id, None)
        cleared = len(evo.memories) if evo else 0
    else:
        cleared = sum(len(e.memories) for e in _evolution.values())
        _evolution = {}
    _save()
    return cleared


DEFAULT_STAGE_AFTER_RESET = "察觉"


def reset_persona_journey(persona: Persona) -> None:
    """清除记忆后，将决策阶段恢复为 Day 0 基准。"""
    persona.osa.stage = DEFAULT_STAGE_AFTER_RESET
    persona.osa.diagnosed = False


def export_memory_bundle(personas: List[Persona]) -> dict:
    """导出记忆 + 当前消费者快照（含阶段），便于下载备份。"""
    if not _evolution:
        _load()
    return {
        "version": "1.0",
        "type": "mindsim_memory_bundle",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "evolution": {k: v.model_dump() for k, v in _evolution.items()},
        "personas": [p.model_dump() for p in personas],
        "stats": {
            "persona_count": len(personas),
            "memory_entries": sum(len(e.memories) for e in _evolution.values()),
        },
    }


def import_memory_bundle(data: dict, *, replace: bool = True) -> dict:
    """
    上传并恢复记忆包。
    replace=True：覆盖现有记忆；False：与现有合并（同 persona_id 以导入为准）。
    """
    global _evolution
    if data.get("type") != "mindsim_memory_bundle":
        raise ValueError("无效的记忆包格式，需 type=mindsim_memory_bundle")

    raw_evo = data.get("evolution") or {}
    imported: Dict[str, PersonaEvolution] = {
        k: PersonaEvolution.model_validate(v) for k, v in raw_evo.items()
    }

    if not _evolution:
        _load()

    if replace:
        _evolution = imported
    else:
        _evolution.update(imported)

    _save()

    persona_updates = 0
    raw_personas = data.get("personas") or []
    if raw_personas:
        from services.persona_store import get_personas, set_personas

        updated_list = list(get_personas())
        id_to_idx = {p.id: i for i, p in enumerate(updated_list)}

        for raw in raw_personas:
            pid = raw.get("id")
            if pid not in id_to_idx:
                continue
            incoming = Persona.model_validate(raw)
            updated_list[id_to_idx[pid]] = incoming
            persona_updates += 1

        if persona_updates:
            set_personas(updated_list)

    return {
        "imported_personas": len(imported),
        "memory_entries": sum(len(e.memories) for e in imported.values()),
        "personas_updated": persona_updates,
    }

