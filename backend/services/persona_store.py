from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from schemas import Persona

ROOT = Path(__file__).resolve().parents[2]
PERSONAS_PATH = ROOT / "data" / "personas.json"

_personas: List[Persona] = []


def load_persisted_personas() -> List[Persona]:
    global _personas
    if PERSONAS_PATH.exists():
        with open(PERSONAS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
            _personas = [Persona.model_validate(p) for p in raw]
    return _personas


def get_personas() -> List[Persona]:
    if not _personas:
        load_persisted_personas()
    return _personas


def set_personas(personas: List[Persona]) -> List[Persona]:
    global _personas
    _personas = personas
    PERSONAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PERSONAS_PATH, "w", encoding="utf-8") as f:
        json.dump([p.model_dump() for p in personas], f, ensure_ascii=False, indent=2)
    return _personas


def get_persona_by_id(persona_id: str) -> Optional[Persona]:
    for p in get_personas():
        if p.id == persona_id:
            return p
    return None
