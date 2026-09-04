from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from schemas import Persona

ROOT = Path(__file__).resolve().parents[2]
PERSONAS_PATH = ROOT / "data" / "personas.json"

_personas: List[Persona] = []
_last_write_at: Optional[str] = None
_last_write_reason: str = ""
_loaded_mtime: float = 0.0


def _apply_coherence(personas: List[Persona]) -> List[Persona]:
    """加载/写盘前修复已知角色-Job-分群漂移（如室友误挂 J5）。"""
    try:
        from services.factor_store import get_enabled_factors
        from services.persona_coherence import fix_persona_coherence

        factors = get_enabled_factors()
    except Exception:
        return personas
    return [fix_persona_coherence(p, factors) for p in personas]


def load_persisted_personas() -> List[Persona]:
    global _personas, _last_write_at, _loaded_mtime
    if PERSONAS_PATH.exists():
        _loaded_mtime = PERSONAS_PATH.stat().st_mtime
        with open(PERSONAS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
            from services.job_store import resolve_step_name

            loaded: List[Persona] = []
            for item in raw:
                p = Persona.model_validate(item)
                if p.jtbd:
                    p.jtbd.current_step = resolve_step_name(
                        p.jtbd.current_step, p.jtbd.job_id
                    )
                loaded.append(p)
            _personas = _apply_coherence(loaded)
            # 若修复改变了结构，回写一次，避免下次又读到坏数据
            try:
                fixed_dump = [p.model_dump() for p in _personas]
                if fixed_dump != raw:
                    PERSONAS_PATH.write_text(
                        json.dumps(fixed_dump, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    _loaded_mtime = PERSONAS_PATH.stat().st_mtime
                    _last_write_at = datetime.now(timezone.utc).isoformat()
                    print(
                        f"[personas] coherence-fixed & saved {len(_personas)} → {PERSONAS_PATH}",
                        flush=True,
                    )
            except Exception as e:
                print(f"[personas] coherence fix save skipped: {e}", flush=True)
    return _personas


def get_personas() -> List[Persona]:
    """读取人格库；若磁盘文件被外部更新则自动重新加载，避免僵尸进程内存与磁盘脱节。"""
    global _personas
    if not _personas:
        return load_persisted_personas()
    try:
        if PERSONAS_PATH.exists() and PERSONAS_PATH.stat().st_mtime > _loaded_mtime + 0.01:
            print("[personas] disk mtime changed → reload", flush=True)
            return load_persisted_personas()
    except OSError:
        pass
    return _personas


def set_personas(personas: List[Persona], *, reason: str = "set_personas") -> List[Persona]:
    global _personas, _last_write_at, _last_write_reason, _loaded_mtime
    old_n = len(_personas)
    old_names = [p.name for p in _personas]
    personas = _apply_coherence(personas)
    _personas = personas
    PERSONAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PERSONAS_PATH, "w", encoding="utf-8") as f:
        json.dump([p.model_dump() for p in personas], f, ensure_ascii=False, indent=2)
    _loaded_mtime = PERSONAS_PATH.stat().st_mtime
    _last_write_at = datetime.now(timezone.utc).isoformat()
    _last_write_reason = reason
    new_names = [p.name for p in personas]
    print(
        f"[personas] WRITE reason={reason} count {old_n}→{len(personas)} "
        f"at {_last_write_at}",
        flush=True,
    )
    if old_names and new_names and old_names != new_names:
        print(
            f"[personas] roster changed: {old_names} → {new_names}",
            flush=True,
        )
    return _personas


def get_persona_by_id(persona_id: str) -> Optional[Persona]:
    for p in get_personas():
        if p.id == persona_id:
            return p
    return None


def personas_write_meta() -> dict:
    return {
        "count": len(get_personas()),
        "last_write_at": _last_write_at,
        "last_write_reason": _last_write_reason,
        "path": str(PERSONAS_PATH),
    }
