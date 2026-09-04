from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Factor(BaseModel):
    id: str
    group: str
    name: str
    weight: int = Field(ge=1, le=10)
    definition: str
    keywords: List[str]
    enabled: bool = True
    source: str = "语料提炼"
    note: str = ""
    jtbd_type: str = "outcome_evidence"
    job_ids: List[str] = Field(default_factory=list)
    outcome_ids: List[str] = Field(default_factory=list)
    force_default: str = "push"  # push | pull | anxiety | habit_or_alternative
    stage_scope: List[str] = Field(default_factory=list)


class FactorsDB(BaseModel):
    version: str = "2.0"
    factors: List[Factor]


class FactorCreate(BaseModel):
    id: str
    group: str
    name: str
    weight: int = Field(ge=1, le=10)
    definition: str
    keywords: List[str]
    enabled: bool = True
    source: str = "用户新增"
    note: str = ""
    jtbd_type: str = "outcome_evidence"
    job_ids: List[str] = Field(default_factory=list)
    outcome_ids: List[str] = Field(default_factory=list)
    force_default: str = "push"
    stage_scope: List[str] = Field(default_factory=list)


class FactorUpdate(BaseModel):
    group: Optional[str] = None
    name: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=1, le=10)
    definition: Optional[str] = None
    keywords: Optional[List[str]] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None
    jtbd_type: Optional[str] = None
    job_ids: Optional[List[str]] = None
    outcome_ids: Optional[List[str]] = None
    force_default: Optional[str] = None
    stage_scope: Optional[List[str]] = None


class Job(BaseModel):
    id: str
    name: str
    category: str = "功能"
    entry_situations: List[str] = Field(default_factory=list)
    job_owners: List[str] = Field(default_factory=list)
    statement: str = ""
    step_ids: List[str] = Field(default_factory=list)
    outcome_ids: List[str] = Field(default_factory=list)
    evidence: str = ""


class SubJob(BaseModel):
    id: str
    name: str
    stage: str
    job_ids: List[str] = Field(default_factory=list)


class Outcome(BaseModel):
    id: str
    name: str
    label: str = ""  # 面向用户的短名；空则前端从 name 截取
    factor_ids: List[str] = Field(default_factory=list)


class DesiredOutcome(BaseModel):
    id: str
    importance: int = Field(default=5, ge=1, le=10)
    satisfaction: int = Field(default=5, ge=1, le=10)


class ForceMap(BaseModel):
    push: List[str] = Field(default_factory=list)
    pull: List[str] = Field(default_factory=list)
    anxiety: List[str] = Field(default_factory=list)
    habit_or_alternative: List[str] = Field(default_factory=list)


class JTBDProfile(BaseModel):
    entry_situation: str = ""
    job_id: str = ""
    job_owner: str = ""
    core_job: str = ""
    job_statement: str = ""
    current_step: str = ""
    desired_outcomes: List[DesiredOutcome] = Field(default_factory=list)
    forces: ForceMap = Field(default_factory=ForceMap)


class DominantFeature(BaseModel):
    code: str
    weight: int


class OSAInfo(BaseModel):
    severity: str = "未确诊"
    ahi: str = "—"
    diagnosed: bool = False
    stage: str = "察觉"


class Mindset(BaseModel):
    core_motive: str = ""
    fear: str = ""
    decision_logic: str = ""
    price_sensitivity: int = Field(default=5, ge=1, le=10)
    brand_anchor: str = ""
    channel_preference: str = ""
    quote: str = ""


class ReactTemplates(BaseModel):
    advance: str = ""
    hesitate: str = ""
    reject: str = ""
    na: str = ""


class Persona(BaseModel):
    id: str
    name: str
    emoji: str = "👤"
    segment: str
    role: str
    subject: str = ""
    age: int
    gender: str
    city: str
    occupation: str
    family: str = ""
    income: str = ""
    osa: OSAInfo = Field(default_factory=OSAInfo)
    mindset: Mindset = Field(default_factory=Mindset)
    dominant_features: List[DominantFeature]
    factor_weights: Dict[str, int]
    blockers: List[str] = Field(default_factory=list)
    drivers: List[str] = Field(default_factory=list)
    decision_style: str = "理性"
    react: ReactTemplates = Field(default_factory=ReactTemplates)
    jtbd: JTBDProfile = Field(default_factory=JTBDProfile)
    evidence_refs: List[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    count: int = Field(ge=1, le=200)
    use_llm: Optional[bool] = None
    options: Dict[str, Any] = Field(default_factory=dict)
    entry_situations: Optional[List[str]] = None
    job_ids: Optional[List[str]] = None
    steps: Optional[List[str]] = None
    roles: Optional[List[str]] = None


class SimulateRequest(BaseModel):
    campaign: str
    persona_ids: Optional[List[str]] = None
    use_llm: bool = False
    use_memory: bool = False
    interventions: Optional[List[str]] = None
    objective: Optional[str] = None
    reproducible: bool = False  # True 时强制走规则引擎，保证同输入同输出


class SimulateResult(BaseModel):
    persona_id: str
    persona_name: str
    decision: str
    reaction: str
    hit_factors: List[str]
    hit_dominant: List[str]
    willingness: Optional[int] = None
    reasoning: Optional[str] = None
    activated_factors: List[str] = Field(default_factory=list)
    mode: str = "rule"
    outcome_improved: List[str] = Field(default_factory=list)
    unresolved_outcomes: List[str] = Field(default_factory=list)
    next_step: str = ""
    interventions: List[str] = Field(default_factory=list)
    verification: Optional[str] = None  # verified | unverified | opposite
    verification_note: str = ""


class SimulateResponse(BaseModel):
    results: List[SimulateResult]
    summary: Dict[str, int]
    campaign_hits: List[str]
    interventions: List[str] = Field(default_factory=list)


class ExportCampaignRequest(BaseModel):
    """将本次测试的行动话术、结果与对应画像打包导出 Excel。"""
    campaign: str = ""
    results: List[SimulateResult] = Field(default_factory=list)
    campaign_hits: List[str] = Field(default_factory=list)
    interventions: List[str] = Field(default_factory=list)
    use_llm: bool = False
    use_memory: bool = False


class MemoryEntry(BaseModel):
    id: str
    day: int
    type: str = "observation"  # observation | reflection
    content: str
    importance: int = Field(ge=1, le=10, default=5)
    source: str = ""  # campaign / reflection / social / observed / simulation
    decision: Optional[str] = None
    willingness: Optional[int] = None
    step_before: str = ""
    outcome_changes: List[dict] = Field(default_factory=list)
    force_changes: List[dict] = Field(default_factory=list)


class PersonaEvolution(BaseModel):
    persona_id: str
    day: int = 0
    memories: List[MemoryEntry] = Field(default_factory=list)
    reflections: List[str] = Field(default_factory=list)


class VerificationRequest(BaseModel):
    persona_id: str
    campaign: str = ""
    status: str  # verified | unverified | opposite
    note: str = ""
    decision: Optional[str] = None
