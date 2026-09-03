"""从 14 个原型抽取 JTBD 结构槽位，供 LLM 创造全新人格（不复制预设姓名/故事）。"""
from __future__ import annotations

import random
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.persona_archetypes import PERSONA_ARCHETYPES, pick_archetypes

CITY_TIERS = ["一线城市", "二线城市", "三线城市", "四线城市"]
OCCUPATION_HINTS = [
    "服务业",
    "制造业",
    "物流运输",
    "互联网",
    "金融",
    "教育",
    "医疗护理",
    "个体经营",
    "公职",
    "零售",
]
LIFE_TEXTURES = [
    "刚换工作、压力变大",
    "家里有二孩、睡眠被切碎",
    "配偶异地、独自照护",
    "父母同住、三代一屋",
    "合租/宿舍、隐私有限",
    "刚做完体检、指标亮红灯",
    "朋友刚因睡眠问题住院、产生触动",
    "公司出差多、作息混乱",
]


@dataclass
class PersonaBlueprint:
    """单个生成槽位：只约束 Job/角色骨架，不携带预设故事正文。"""

    slot_index: int
    persona_id: str
    job_id: str
    segment: str
    role_hint: str
    subject_hint: str
    entry_situation: str
    job_owner: str
    stage: str
    patient_severity: str
    current_step_id: str
    desired_outcome_ids: List[str]
    dominant_factor_hints: List[str]
    force_hints: Dict[str, List[str]] = field(default_factory=dict)
    city_tier: str = "二线城市"
    occupation_hint: str = "服务业"
    life_texture: str = ""
    creativity_seed: str = ""

    def to_prompt_dict(self) -> dict:
        return {
            "slot_index": self.slot_index,
            "persona_id": self.persona_id,
            "job_id": self.job_id,
            "segment": self.segment,
            "role_hint": self.role_hint,
            "subject_hint": self.subject_hint,
            "entry_situation": self.entry_situation,
            "job_owner": self.job_owner,
            "stage": self.stage,
            "patient_severity": self.patient_severity,
            "current_step_id": self.current_step_id,
            "desired_outcome_ids": self.desired_outcome_ids,
            "dominant_factor_hints": self.dominant_factor_hints,
            "force_hints": self.force_hints,
            "city_tier": self.city_tier,
            "occupation_hint": self.occupation_hint,
            "life_texture": self.life_texture,
            "creativity_seed": self.creativity_seed,
        }


def archetype_seed_names() -> set[str]:
    return {a.get("seed_name", "") for a in PERSONA_ARCHETYPES if a.get("seed_name")}


def build_blueprints(
    count: int,
    *,
    job_ids: Optional[List[str]] = None,
    entry_situations: Optional[List[str]] = None,
) -> List[PersonaBlueprint]:
    """按 Job 轮询分配结构槽；人口学与具体故事留给 LLM 随机创造。"""
    archetypes = pick_archetypes(
        count, job_ids=job_ids, entry_situations=entry_situations
    )
    rng = random.Random(secrets.token_hex(8))
    blueprints: List[PersonaBlueprint] = []

    for i, arch in enumerate(archetypes[:count]):
        jt = arch.get("jtbd") or {}
        forces = jt.get("forces") or {}
        blueprints.append(
            PersonaBlueprint(
                slot_index=i + 1,
                persona_id=f"P{i + 1:02d}" if i + 1 < 100 else f"P{i + 1:03d}",
                job_id=jt.get("job_id", ""),
                segment=arch.get("segment", ""),
                role_hint=arch.get("role", ""),
                subject_hint=arch.get("subject", ""),
                entry_situation=jt.get("entry_situation", ""),
                job_owner=jt.get("job_owner", ""),
                stage=arch.get("stage", "察觉"),
                patient_severity=arch.get("patient_severity", "未确诊"),
                current_step_id=jt.get("current_step_id", ""),
                desired_outcome_ids=list(jt.get("desired_outcome_ids") or [])[:5],
                dominant_factor_hints=list(arch.get("dominant") or [])[:4],
                force_hints={
                    "push": list(forces.get("push") or []),
                    "pull": list(forces.get("pull") or []),
                    "anxiety": list(forces.get("anxiety") or []),
                    "habit_or_alternative": list(forces.get("habit_or_alternative") or []),
                },
                city_tier=rng.choice(CITY_TIERS),
                occupation_hint=rng.choice(OCCUPATION_HINTS),
                life_texture=rng.choice(LIFE_TEXTURES),
                creativity_seed=secrets.token_hex(4),
            )
        )
    return blueprints
