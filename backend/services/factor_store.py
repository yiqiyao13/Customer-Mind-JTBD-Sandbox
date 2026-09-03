from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from schemas import Factor, FactorCreate, FactorUpdate, FactorsDB

ROOT = Path(__file__).resolve().parents[2]
FACTORS_PATH = ROOT / "data" / "factors.json"


def load_factors_db() -> FactorsDB:
    with open(FACTORS_PATH, encoding="utf-8") as f:
        return FactorsDB.model_validate(json.load(f))


def save_factors_db(db: FactorsDB) -> None:
    FACTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FACTORS_PATH, "w", encoding="utf-8") as f:
        json.dump(db.model_dump(), f, ensure_ascii=False, indent=2)


def get_enabled_factors() -> List[Factor]:
    return [f for f in load_factors_db().factors if f.enabled]


def get_factor_by_id(factor_id: str) -> Optional[Factor]:
    for f in load_factors_db().factors:
        if f.id == factor_id:
            return f
    return None


def add_factor(data: FactorCreate) -> Factor:
    db = load_factors_db()
    if any(f.id == data.id for f in db.factors):
        raise ValueError(f"维度编码 {data.id} 已存在")
    factor = Factor(**data.model_dump())
    db.factors.append(factor)
    save_factors_db(db)
    return factor


def update_factor(factor_id: str, data: FactorUpdate) -> Factor:
    db = load_factors_db()
    for i, f in enumerate(db.factors):
        if f.id == factor_id:
            updated = f.model_copy(update={k: v for k, v in data.model_dump().items() if v is not None})
            db.factors[i] = updated
            save_factors_db(db)
            return updated
    raise KeyError(f"维度 {factor_id} 不存在")


def delete_factor(factor_id: str) -> Factor:
    db = load_factors_db()
    for i, f in enumerate(db.factors):
        if f.id == factor_id:
            updated = f.model_copy(update={"enabled": False})
            db.factors[i] = updated
            save_factors_db(db)
            return updated
    raise KeyError(f"维度 {factor_id} 不存在")
