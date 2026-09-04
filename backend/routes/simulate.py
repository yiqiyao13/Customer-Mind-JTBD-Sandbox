from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from schemas import (
    ExportCampaignRequest,
    PersonaEvolution,
    SimulateRequest,
    SimulateResponse,
    VerificationRequest,
)
from services.export_campaign import build_campaign_workbook
from services.factor_store import load_factors_db
from services.llm_simulate import simulate_campaign_llm
from services.memory import (
    export_memory_bundle,
    import_memory_bundle,
    list_all_memories,
    record_campaign_experience,
    record_verification,
    reset_evolution,
    reset_persona_journey,
)
from services.persona_store import get_persona_by_id, get_personas, personas_write_meta, set_personas
from services.simulate import simulate_campaign

router = APIRouter(prefix="/api", tags=["personas", "simulate"])


@router.get("/personas", response_model=list)
def list_personas():
    return get_personas()


@router.post("/personas/reload")
def reload_personas_from_disk():
    """强制从 data/personas.json 重新加载（排查内存与磁盘不一致）。"""
    from services.persona_store import load_persisted_personas, personas_write_meta

    personas = load_persisted_personas()
    meta = personas_write_meta()
    meta["reloaded"] = True
    meta["count"] = len(personas)
    return meta


@router.get("/personas/meta")
def personas_meta():
    """排查人格库是否被覆盖：最近一次写盘原因与人数。"""
    return personas_write_meta()


@router.get("/personas/{persona_id}/memories", response_model=PersonaEvolution)
def persona_memories(persona_id: str):
    if not get_persona_by_id(persona_id):
        raise HTTPException(status_code=404, detail="心智不存在")
    return list_all_memories(persona_id)


@router.post("/export/campaign")
def export_campaign_excel(req: ExportCampaignRequest):
    """导出：行动话术 + 结果总览 + 反馈 + 画像 + 关注点矩阵。"""
    if not req.results:
        raise HTTPException(status_code=400, detail="暂无测试结果可导出，请先运行 Campaign 测试")
    personas = get_personas()
    try:
        data = build_campaign_workbook(
            campaign=req.campaign,
            results=req.results,
            personas=personas,
            campaign_hits=req.campaign_hits,
            interventions=req.interventions,
            use_llm=req.use_llm,
            use_memory=req.use_memory,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败：{e}") from e

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"MindSim_Campaign_{stamp}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/simulate", response_model=SimulateResponse)
async def run_simulate(req: SimulateRequest):
    personas = get_personas()
    if not personas:
        raise HTTPException(status_code=400, detail="请先生成心智")

    if not req.campaign.strip():
        raise HTTPException(status_code=400, detail="campaign 不能为空")

    factors = load_factors_db().factors
    use_llm = bool(req.use_llm) and not bool(getattr(req, "reproducible", False))

    try:
        if use_llm:
            results, summary, campaign_hits, interventions = await simulate_campaign_llm(
                req.campaign,
                personas,
                factors,
                req.persona_ids,
                req.use_memory,
                req.interventions,
            )
        else:
            results, summary, campaign_hits, interventions = simulate_campaign(
                req.campaign,
                personas,
                factors,
                req.persona_ids,
                req.interventions,
            )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"仿真失败: {e}")

    # 仅「有记忆」模式：写入经历、推动阶段 / JTBD step 变化
    if req.use_memory:
        persona_map = {p.id: p for p in personas}
        for result in results:
            persona = persona_map.get(result.persona_id)
            if persona:
                record_campaign_experience(persona, req.campaign, result)
        set_personas(list(persona_map.values()), reason="simulate_memory")

    return SimulateResponse(
        results=results,
        summary=summary,
        campaign_hits=campaign_hits,
        interventions=interventions,
    )


@router.post("/verify")
def verify_result(req: VerificationRequest):
    """真实验证回写：已验证 / 未验证 / 方向相反。"""
    if req.status not in ("verified", "unverified", "opposite"):
        raise HTTPException(status_code=400, detail="status 须为 verified|unverified|opposite")
    if not get_persona_by_id(req.persona_id):
        raise HTTPException(status_code=404, detail="心智不存在")
    entry = record_verification(
        req.persona_id,
        status=req.status,
        note=req.note,
        campaign=req.campaign,
        decision=req.decision,
    )
    return {"ok": True, "entry": entry.model_dump()}


@router.post("/memories/reset")
def reset_all_memories():
    """一键清除全部消费者记忆，并将决策阶段恢复为「察觉」。"""
    personas = get_personas()
    cleared = reset_evolution()
    for p in personas:
        reset_persona_journey(p)
    if personas:
        set_personas(personas, reason="memories_reset_all")


@router.post("/personas/{persona_id}/memories/reset")
def reset_persona_memories(persona_id: str):
    """清除单个消费者的记忆与阶段变化。"""
    persona = get_persona_by_id(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="心智不存在")
    cleared = reset_evolution(persona_id)
    reset_persona_journey(persona)
    personas = get_personas()
    set_personas(personas, reason=f"memories_reset_{persona_id}")


@router.get("/memories/export")
def export_memories():
    """下载记忆包（经历时间线 + 消费者阶段快照）。"""
    personas = get_personas()
    bundle = export_memory_bundle(personas)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"mindsim_memories_{stamp}.json"
    content = json.dumps(bundle, ensure_ascii=False, indent=2)
    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/memories/import")
async def import_memories(
    file: UploadFile = File(...),
    replace: bool = True,
):
    """上传记忆包并恢复。replace=true 覆盖现有记忆。"""
    try:
        raw = await file.read()
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}")

    try:
        stats = import_memory_bundle(data, replace=replace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    personas = get_personas()
    return {
        "ok": True,
        "replace": replace,
        **stats,
        "message": (
            f"已导入 {stats['imported_personas']} 位消费者的 "
            f"{stats['memory_entries']} 条记忆"
            + (f"，同步 {stats['personas_updated']} 人阶段" if stats["personas_updated"] else "")
        ),
    }
