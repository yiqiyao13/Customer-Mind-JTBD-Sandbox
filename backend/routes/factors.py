from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas import Factor, FactorCreate, FactorUpdate, FactorsDB
from services.factor_store import (
    add_factor,
    delete_factor,
    load_factors_db,
    update_factor,
)

router = APIRouter(prefix="/api/factors", tags=["factors"])


@router.get("", response_model=FactorsDB)
def list_factors():
    return load_factors_db()


@router.post("", response_model=Factor)
def create_factor(data: FactorCreate):
    try:
        return add_factor(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{factor_id}", response_model=Factor)
def edit_factor(factor_id: str, data: FactorUpdate):
    try:
        return update_factor(factor_id, data)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{factor_id}", response_model=Factor)
def remove_factor(factor_id: str):
    try:
        return delete_factor(factor_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
