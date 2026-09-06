const API = '';

let factors = [];
let personas = [];
let outcomes = [];
let jobTrees = [];
let jobsById = {};
let selectedId = null;
let lastSimResults = []; // 最近一次测试结果，用于画像↔反馈联动
/** 最近一次测试元信息，供 Excel 导出 */
let lastSimMeta = { campaign_hits: [], interventions: [], use_llm: false, use_memory: false };
const filters = { segment: new Set(), role: new Set(), stage: new Set(), factor: new Set() };
const selectedEntryThemes = new Set();

const ENTRY_THEMES = [
  '心血管风险',
  '伴侣睡眠受损',
  '日间功能与安全',
  '照护责任',
  '重症呼吸支持',
  '社交羞耻',
];

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function badgeGroup(g) {
  return `<span class="badge ${g}">${g}</span>`;
}

function weightBar(w) {
  const pct = Math.min(100, (w / 10) * 100);
  return `<div class="weight-bar"><span style="width:${pct}%"></span></div>`;
}

function gapBadge(importance, satisfaction) {
  const gap = Math.max(0, (importance || 0) - (satisfaction || 0));
  let cls = 'gap-ok';
  let text = '较平衡';
  if (gap >= 6) { cls = 'gap-hot'; text = '很急迫'; }
  else if (gap >= 4) { cls = 'gap-high'; text = '缺口大'; }
  else if (gap >= 2) { cls = 'gap-mid'; text = '还有差距'; }
  return `<span class="gap-badge ${cls}" title="在乎 − 满意 = ${gap}">${text} · 差 ${gap} 分</span>`;
}

function outcomeMeter(kind, value, label) {
  const v = Math.max(0, Math.min(10, Number(value) || 0));
  const pct = (v / 10) * 100;
  return `
    <div class="oc-meter ${kind}">
      <div class="oc-meter-top">
        <span class="oc-meter-label">${label}</span>
        <span class="oc-meter-val">${v}<small>/10</small></span>
      </div>
      <div class="oc-meter-track" role="meter" aria-valuenow="${v}" aria-valuemin="0" aria-valuemax="10" aria-label="${label}">
        <span class="oc-meter-fill" style="width:${pct}%"></span>
      </div>
    </div>
  `;
}

function renderOutcomeCard(d, { simMark = '', simState = '' } = {}) {
  const short = outcomeLabel(d.id);
  const full = outcomeName(d.id);
  const want = Number(d.importance) || 0;
  const have = Number(d.satisfaction) || 0;
  const gap = Math.max(0, want - have);
  const gapPct = (gap / 10) * 100;
  return `
    <article class="outcome-card${simState ? ` sim-${simState}` : ''}">
      <header class="outcome-card-head">
        <h4 class="outcome-card-title">${short}</h4>
        <div class="outcome-card-tags">
          ${simMark}
          ${gapBadge(want, have)}
        </div>
      </header>
      <div class="outcome-meters">
        ${outcomeMeter('want', want, '有多在乎')}
        ${outcomeMeter('have', have, '现在满意')}
        <div class="oc-gap-viz" title="还差多少才满意">
          <div class="oc-meter-top">
            <span class="oc-meter-label">满意缺口</span>
            <span class="oc-meter-val gap">${gap}<small> 分</small></span>
          </div>
          <div class="oc-meter-track oc-gap-track">
            <span class="oc-meter-fill oc-gap-fill" style="width:${gapPct}%"></span>
          </div>
        </div>
      </div>
      <p class="outcome-card-desc">${full}</p>
    </article>
  `;
}

function forceChip(label, ids) {
  if (!ids?.length) return '';
  const names = {
    push: '推动力',
    pull: '吸引力',
    anxiety: '顾虑',
    alt: '替代方案',
  };
  const full = ids.map(id => factors.find(x => x.id === id)?.name || id).join('、');
  return `<span class="force-chip ${label}" title="${full}">${names[label] || label}：${full}</span>`;
}

async function loadFactors() {
  const db = await api('/api/factors');
  factors = db.factors;
  if (typeof renderFactors === 'function') renderFactors();
  if (typeof renderFactorFilters === 'function') renderFactorFilters();
}

async function loadPersonas() {
  personas = await api('/api/personas');
  return personas;
}

async function loadOutcomes() {
  try {
    outcomes = await api('/api/outcomes');
  } catch {
    outcomes = [];
  }
  // outcomes 晚到时补刷详情，避免标题/描述用短名 fallback 后卡住
  if (selectedId) renderDetail();
}

async function loadJobsMap(opts = {}) {
  const renderMap = opts.renderMap !== false;
  try {
    const data = await api('/api/jobs');
    jobTrees = data.job_trees || [];
    jobsById = Object.fromEntries((data.jobs || []).map(j => [j.id, j]));
    if (renderMap && typeof renderJobMap === 'function') renderJobMap();
  } catch {
    jobTrees = [];
    jobsById = {};
  }
}

function jobLabel(id) {
  const j = jobsById[id];
  return j ? `${j.name}` : id;
}

/** 把研发用的证据码转成市场可读文案 */
function evidenceLabel(refs) {
  if (!refs?.length) return '合成消费者原型';
  const KEY_MAP = {
    synthetic: '合成消费者原型',
    hypothesis: '假设样本',
    spouse_pusher_liu: '伴侣推动原型',
    spouse_shopkeeper: '伴侣推动·预算敏感',
    nurse_caregiver: '医护照护原型',
    filial_daughter: '子女照护原型',
    roommate_young: '室友影响原型',
    shame_self: '社交羞耻原型',
    doctor_self: '专业KOL样本',
    exec_self: '职场自用原型',
    retiree_struggle: '依从挣扎原型',
    elderly_self: '老年自用原型',
    als_caregiver: '重症照护原型',
  };
  const parts = refs.map(r => {
    if (KEY_MAP[r]) return KEY_MAP[r];
    if (/^[A-Za-z0-9_]+$/.test(r)) return '合成原型';
    return r;
  });
  return [...new Set(parts)].join(' · ');
}

function isKolPersona(p) {
  const occ = p?.occupation || '';
  return /医生|主治|呼吸科|睡眠科/.test(occ) || (p?.evidence_refs || []).includes('doctor_self');
}

function renderJobMap() {
  const el = document.getElementById('jtbd-map');
  if (!el) return;
  if (!jobTrees.length) {
    el.innerHTML = '<div class="empty">任务地图加载中…</div>';
    return;
  }
  el.innerHTML = `
    <p class="status" style="margin-bottom:0.65rem">主任务（Job）→ 子任务（Step）。同一子任务可被多个主任务共用；选中消费者后，画像里会高亮 TA 当前所在步骤。</p>
    <div class="job-map-list">
      ${jobTrees.map(j => `
        <article class="job-map-card" data-job="${j.id}">
          <header class="job-map-head">
            <div>
              <span class="job-map-id">${j.id}</span>
              <strong class="job-map-title">${j.name}</strong>
              <span class="job-map-cat">${j.category || ''}</span>
            </div>
            <span class="status">${(j.job_owners || []).join(' / ') || '—'}</span>
          </header>
          <p class="job-map-stmt">${j.statement || ''}</p>
          <div class="job-map-stages">
            ${(j.stages || []).map(st => `
              <div class="job-stage">
                <div class="job-stage-name">${st.name}</div>
                <div class="job-steps">
                  ${(st.steps || []).map(s => `
                    <span class="job-step" data-step="${s.name}" title="${s.id}">${s.name}</span>
                  `).join('<span class="job-step-arrow">→</span>')}
                </div>
              </div>
            `).join('')}
          </div>
          <p class="status" style="margin-top:0.45rem">期望结果：${(j.outcome_ids || []).map(oid => outcomeLabel(oid)).join(' · ') || '—'}</p>
        </article>
      `).join('')}
    </div>
  `;
}

function renderPersonaJobPath(p) {
  const jid = p?.jtbd?.job_id;
  const tree = jobTrees.find(j => j.id === jid);
  const current = p?.jtbd?.current_step || '';
  if (!tree) {
    return `<p class="status">当前任务：${p?.jtbd?.core_job || '—'} · 步骤 ${current || '—'}</p>`;
  }
  const flat = (tree.steps || []);
  const idx = flat.findIndex(s => s.name === current);
  return `
    <div class="persona-job-path">
      <div class="persona-job-path-label">
        <span class="k">TA 要完成的任务</span>
        <strong>${tree.name}</strong>
        ${current ? `<span class="status">· 当前卡在：${current}</span>` : ''}
      </div>
      <div class="persona-job-steps">
        ${flat.map((s, i) => {
          let cls = 'job-step';
          if (i < idx) cls += ' done';
          if (i === idx) cls += ' current';
          return `<span class="${cls}" title="${s.stage}">${s.name}</span>${i < flat.length - 1 ? '<span class="job-step-arrow">→</span>' : ''}`;
        }).join('')}
      </div>
    </div>
  `;
}

function fillSampleCampaign() {
  const el = document.getElementById('campaign-text');
  if (!el) {
    alert('找不到话术输入框');
    return;
  }
  el.value = '瑞思迈 AirSense 11 限时优惠，支持30天试戴体验，医院睡眠中心同款，面罩免费适配，还有国补15%补贴，进口品质值得信赖。';
  el.focus();
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

function initEntryThemes() {
  const el = document.getElementById('entry-themes');
  if (!el) return;
  el.innerHTML = ENTRY_THEMES.map(t => {
    const on = selectedEntryThemes.has(t);
    return `<button type="button" class="chip ${on ? 'active is-selected' : ''}" data-theme="${t}" aria-pressed="${on ? 'true' : 'false'}">${t}</button>`;
  }).join('');
  el.querySelectorAll('.chip').forEach(c => {
    c.addEventListener('click', () => {
      const t = c.dataset.theme;
      if (selectedEntryThemes.has(t)) selectedEntryThemes.delete(t);
      else selectedEntryThemes.add(t);
      initEntryThemes();
    });
  });
}

function filteredPersonas() {
  return personas.filter(p => {
    if (filters.segment.size && !filters.segment.has(p.segment)) return false;
    if (filters.role.size && !filters.role.has(p.role)) return false;
    if (filters.stage.size && !filters.stage.has(p.osa?.stage)) return false;
    if (filters.factor.size) {
      const codes = new Set(p.dominant_features.map(d => d.code));
      for (const f of filters.factor) if (!codes.has(f)) return false;
    }
    return true;
  });
}

function chipGroup(containerId, values, key) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = values.map(v => `
    <span class="chip ${filters[key].has(v) ? 'active' : ''}" data-key="${key}" data-val="${v}">${v}</span>
  `).join('');
  el.querySelectorAll('.chip').forEach(c => {
    c.addEventListener('click', () => {
      const set = filters[c.dataset.key];
      if (set.has(c.dataset.val)) set.delete(c.dataset.val); else set.add(c.dataset.val);
      chipGroup(containerId, values, key);
      renderPersonaList();
    });
  });
}

function renderFactorFilters() {
  const enabled = factors.filter(f => f.enabled);
  chipGroup('filter-factors', enabled.map(f => f.id), 'factor');
  const el = document.getElementById('filter-factors');
  if (!el) return;
  el.querySelectorAll('.chip').forEach((c, i) => {
    c.textContent = enabled[i].name;
    c.dataset.val = enabled[i].id;
  });
}

function initFilters() {
  chipGroup('filter-segments', ['关系驱动型','健康焦虑自用型','专业验证型','场景干扰型','经济受限型','长期照护型','依从挣扎型'], 'segment');
  chipGroup('filter-roles', ['本人','伴侣(推动者)','家人推动者(伴侣)','子女(为父母)','伴侣照护者','本人(室友影响)'], 'role');
  chipGroup('filter-stages', ['未察觉','察觉','就医确诊','决策纠结','购买','适应','依从习惯','复购更换','闲置转让'], 'stage');
}

function getSimResult(personaId) {
  return lastSimResults.find(r => r.persona_id === personaId) || null;
}

function selectPersona(id, { scrollTo = 'detail' } = {}) {
  if (!id) return;
  selectedId = id;
  renderPersonaList();
  renderDetail();
  highlightLinkedResults();
  if (scrollTo === 'detail') {
    document.getElementById('persona-detail')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } else if (scrollTo === 'result') {
    document.querySelector(`.result-row[data-pid="${id}"], .result-card[data-pid="${id}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function highlightLinkedResults() {
  document.querySelectorAll('.result-row, .result-card').forEach(card => {
    card.classList.toggle('linked-active', card.dataset.pid === selectedId);
  });
  document.querySelectorAll('.heatmap tbody tr[data-pid]').forEach(tr => {
    tr.classList.toggle('linked-active', tr.dataset.pid === selectedId);
  });
}

function decisionLabel(d) {
  return ({ advance: '推进', hesitate: '犹豫', na: '无关', reject: '拒绝' })[d] || d;
}

function renderPersonaList() {
  const list = filteredPersonas();
  const el = document.getElementById('persona-list');
  if (!el) return;
  if (!list.length) {
    el.innerHTML = '<div class="empty">暂无心智 — 请先生成</div>';
    return;
  }
  el.innerHTML = list.map(p => {
    const sim = getSimResult(p.id);
    const simTag = sim
      ? `<span class="list-sim-tag ${sim.decision}">${decisionLabel(sim.decision)}</span>`
      : '';
    const kol = isKolPersona(p) ? '<span class="kol-tag">专业样本</span>' : '';
    return `
    <div class="persona-item ${p.id === selectedId ? 'active' : ''}" data-id="${p.id}" title="点击查看完整画像">
      <div class="persona-item-top">
        <strong>${p.emoji} ${p.name}</strong>
        ${kol}
        ${simTag}
      </div>
      <div class="meta">${p.occupation || '—'} · ${p.jtbd?.core_job || p.segment}</div>
      <div class="meta">${p.role || ''} · 卡在「${p.jtbd?.current_step || p.osa?.stage || '—'}」</div>
    </div>`;
  }).join('');
  el.querySelectorAll('.persona-item').forEach(item => {
    item.addEventListener('click', () => {
      selectPersona(item.dataset.id, { scrollTo: 'detail' });
    });
  });
}

/** 兜底短名：即使 /api/outcomes 尚未加载，也绝不把 O3 亮给市场部 */
const OUTCOME_LABELS = {
  O1: '搞清严不严重',
  O2: '疗效/数据可核对',
  O3: '戴得住用不下去',
  O4: '伴侣睡眠/关系',
  O5: '照护不伤感情',
  O6: '总花费心里有数',
  O7: '售后渠道靠得住',
  O8: '别买了闲置',
  O9: '重症呼吸支持到位',
  O10: '体面不丢人',
};

/** 完整描述兜底：outcomes 尚未加载时不能回退到短名，否则标题/描述会重复 */
const OUTCOME_NAMES = {
  O1: '最小化「不确定是否生病/多严重」的不确定性',
  O2: '最大化「疗效改善与算法报告可验证、可核对」的确认感',
  O3: '最小化「设备不适/漏气/噪音用不下去」的风险',
  O4: '最大化「伴侣睡眠与家庭关系改善」的可预期性',
  O5: '最小化「照护变成催促/冲突」的风险',
  O6: '最小化「首次投入+长期维护总成本」的不确定性',
  O7: '最小化「长期无人指导/渠道不可信」的风险',
  O8: '最小化「买了闲置浪费」的风险',
  O9: '最小化「重症呼吸支持不到位危及生命」的风险',
  O10: '最小化「治疗过程被嘲笑/社交形象受损」的风险',
};

const INTERVENTION_LABELS = {
  hospital_endorsement: '医院/专家背书',
  data_visibility: '数据可见',
  trial: '试戴/试用',
  mask_fit_support: '面罩适配支持',
  family_participation: '家庭共同参与',
  filial_care: '孝道照护',
  financing: '分期/补贴/优惠',
  trade_in: '以旧换新',
  after_sales: '售后保障',
  life_support: '重症呼吸支持',
  shame_relief: '减轻社交压力',
  material_hygiene: '材质与卫生',
};

function interventionLabel(id) {
  return INTERVENTION_LABELS[id] || id;
}

function renderBoostChips(ids, size = '') {
  return (ids || []).map(k =>
    `<span class="boost-chip${size ? ` ${size}` : ''}">${interventionLabel(k)}</span>`
  ).join('');
}

/** Campaign 区：助力点是工作人员主看项，维度降为次要补充 */
function renderCampaignHitPanel(data) {
  const ints = data?.interventions || [];
  const hits = data?.campaign_hits || [];
  if (!ints.length && !hits.length) {
    return '<p class="status">点击下方卡片或热力图行，可联动打开画像</p>';
  }
  const boost = ints.length
    ? `<div class="boost-banner">
        <div class="boost-kicker">工作人员重点核对</div>
        <div class="boost-banner-inner">
          <div class="boost-banner-head">
            <strong>识别到的助力点</strong>
            <span class="boost-count">${ints.length}</span>
          </div>
          <p class="boost-hint">话术命中的卖点 · 先看有没有打到关键卡点</p>
          <div class="boost-chips">${renderBoostChips(ints)}</div>
        </div>
      </div>`
    : `<div class="boost-banner is-empty">
        <div class="boost-kicker">工作人员重点核对</div>
        <div class="boost-banner-inner">
          <div class="boost-banner-head"><strong>识别到的助力点</strong></div>
          <p class="boost-hint">本次话术未识别到结构化助力点</p>
        </div>
      </div>`;
  const factorHits = hits.length
    ? `<div class="factor-hits">
        <span class="factor-hits-label">命中维度</span>
        <div class="factor-hit-chips">${hits.map(h => `<span class="factor-hit-chip">${h}</span>`).join('')}</div>
      </div>`
    : '';
  return boost + factorHits;
}

function renderPersonaBoost(ids, globalIds) {
  if (ids?.length) {
    return `<div class="persona-boost">
      <span class="persona-boost-kicker">助力点</span>
      <div class="persona-boost-body">
        <span class="persona-boost-label">对此人生效</span>
        <div class="boost-chips">${renderBoostChips(ids)}</div>
      </div>
    </div>`;
  }
  if (globalIds?.length) {
    return `<div class="persona-boost is-miss">
      <span class="persona-boost-kicker">助力点</span>
      <div class="persona-boost-body">
        <span class="persona-boost-label">对此人未生效</span>
        <span class="os-empty">话术助力点没有打到此人卡点</span>
      </div>
    </div>`;
  }
  return '';
}

function outcomeChipList(ids, emptyText) {
  if (!ids?.length) return `<span class="os-empty">${emptyText}</span>`;
  return ids.map(id => `<span class="os-chip">${outcomeLabel(id)}</span>`).join('');
}

function renderOutcomeStatus(sim) {
  const improved = sim?.outcome_improved || [];
  const unresolved = sim?.unresolved_outcomes || [];
  const next = String(sim?.next_step || '').trim();
  return `<div class="outcome-status" role="group" aria-label="已改善、未改善与下一步">
    <div class="os-card yes${improved.length ? '' : ' is-empty'}">
      <div class="os-card-label">已改善 <span class="os-count">${improved.length}</span></div>
      <div class="os-card-body">${outcomeChipList(improved, '本次没有改善项')}</div>
    </div>
    <div class="os-card no${unresolved.length ? '' : ' is-empty'}">
      <div class="os-card-label">未改善 <span class="os-count">${unresolved.length}</span></div>
      <div class="os-card-body">${outcomeChipList(unresolved, '没有未改善项')}</div>
    </div>
    <div class="os-card next${next ? '' : ' is-empty'}">
      <div class="os-card-label">下一步</div>
      <div class="os-card-body">${next ? `<span class="os-next-step">${next}</span>` : '<span class="os-empty">未给出</span>'}</div>
    </div>
  </div>`;
}

function compactStatusRow(kind, label, items, emptyText) {
  const chips = items.length
    ? items.map(text => `<span class="os-pill ${kind}">${text}</span>`).join('')
    : `<span class="os-pill muted">${emptyText}</span>`;
  return `<div class="os-compact-row ${kind}">
    <span class="os-compact-k">${label}</span>
    <div class="os-compact-chips">${chips}</div>
  </div>`;
}

function renderOutcomeStatusCompact(sim) {
  const improved = (sim?.outcome_improved || []).map(outcomeLabel);
  const unresolved = (sim?.unresolved_outcomes || []).map(outcomeLabel);
  const next = String(sim?.next_step || '').trim();
  return `<div class="os-compact">
    ${compactStatusRow('yes', '已改善', improved, '无')}
    ${compactStatusRow('no', '未改善', unresolved, '无')}
    ${compactStatusRow('next', '下一步', next ? [next] : [], '—')}
  </div>`;
}

function renderResultBoostLine(ids) {
  if (!ids?.length) return '';
  return `<div class="rr-boost-line">
    <span class="rr-boost-k">助力点</span>
    <div class="boost-chips">${renderBoostChips(ids)}</div>
  </div>`;
}

function outcomeName(id) {
  return outcomes.find(o => o.id === id)?.name || OUTCOME_NAMES[id] || id;
}

/** 面向用户的短名：热力图列头、结果卡片用，避免只显示 O1/O2 */
function outcomeLabel(id) {
  const key = String(id || '').trim();
  // 已知 ID 一律优先用中文短名，避免 outcomes 未加载或字段异常时露出 O3
  if (OUTCOME_LABELS[key]) return OUTCOME_LABELS[key];
  const o = outcomes.find(x => x.id === key);
  if (o?.label) return o.label;
  if (o?.name) {
    const m = String(o.name).match(/「([^」]+)」/);
    return m ? m[1] : o.name;
  }
  return key || id;
}

function formatOutcomeList(ids) {
  if (!ids?.length) return '无';
  return ids.map(id => outcomeLabel(id)).join('、');
}

function renderDetail() {
  const p = personas.find(x => x.id === selectedId);
  const el = document.getElementById('persona-detail');
  if (!el) return;
  if (!p) {
    el.innerHTML = '<div class="empty">← 点击左侧消费者，立刻查看画像（不必先跑 Campaign）</div>';
    return;
  }
  const j = p.jtbd || {};
  const dos = (j.desired_outcomes || []).slice(0, 3);
  const forces = j.forces || {};
  const domHtml = (p.dominant_features || []).map(d => {
    const f = factors.find(x => x.id === d.code);
    return `<div style="margin-bottom:0.4rem">${badgeGroup(f?.group || 'A')} ${f?.name || d.code} ${weightBar(d.weight)}</div>`;
  }).join('') || '<p class="status">暂无维度权重</p>';

  const sim = getSimResult(p.id);
  const simPanel = sim ? `
    <div class="sim-link-panel" id="sim-link-panel">
      <div class="sim-link-head">
        <div class="task-label" style="margin:0">本次测试反馈</div>
        <span class="decision ${sim.decision}">${decisionLabel(sim.decision)}</span>
      </div>
      ${renderPersonaBoost(sim.interventions, lastSimMeta.interventions)}
      ${renderOutcomeStatus(sim)}
      <p class="sim-link-reaction">${sim.reaction}</p>
      ${sim.reasoning ? `<p class="sim-link-reason">${sim.reasoning}</p>` : ''}
      <p class="status sim-link-meta">意愿 <strong>${sim.willingness}/10</strong> · ${sim.mode === 'llm' ? 'LLM' : '规则'}</p>
      <div class="verify-row sim-link-verify">
        <span class="status">真实验证</span>
        <button class="btn btn-ghost btn-sm btn-verify" data-status="verified" data-pid="${p.id}" data-decision="${sim.decision}">已验证</button>
        <button class="btn btn-ghost btn-sm btn-verify" data-status="unverified" data-pid="${p.id}" data-decision="${sim.decision}">未验证</button>
        <button class="btn btn-ghost btn-sm btn-verify" data-status="opposite" data-pid="${p.id}" data-decision="${sim.decision}">方向相反</button>
      </div>
      <button type="button" class="btn btn-ghost btn-sm" id="btn-jump-result">在总览矩阵/卡片中定位 ↓</button>
    </div>
  ` : (lastSimResults.length ? `
    <div class="sim-link-panel muted">
      <p class="status">此人未出现在最近一次测试结果中。可在下方总览区查看其他人，或重新运行测试。</p>
    </div>
  ` : `
    <div class="sim-link-panel muted">
      <p class="status">点左侧人名即可看画像。运行上方「Campaign 测试」后，<strong>此人的话术反馈会直接显示在这里</strong>（下方矩阵作多人总览）。</p>
    </div>
  `);

  const roommateNote = /室友/.test(p.role || '') || /室友/.test(p.subject || '')
    ? `<p class="status highlight-note">情境说明：TA 是被室友鼾声影响的<strong>被动受害者</strong>，任务是恢复自己的睡眠，并非本人打鼾求治。</p>`
    : '';
  const kolNote = isKolPersona(p)
    ? `<p class="status highlight-note">样本说明：这是<strong>专业 KOL 型样本</strong>（${p.occupation}），用于测专业话术，不宜当作普通消费者占比。</p>`
    : '';

  el.innerHTML = `
    <div class="card-header" style="border:none;padding:0;margin-bottom:0.75rem">
      <h2><span class="dot"></span>${p.emoji} ${p.name}${isKolPersona(p) ? ' <span class="kol-tag">专业样本</span>' : ''}</h2>
      <div class="row" style="gap:0.5rem">
        <button class="btn btn-danger btn-sm" id="btn-reset-one-memory" data-id="${p.id}">清除记忆</button>
      </div>
    </div>

    <div class="demo-summary">
      <strong>${p.age}岁 · ${p.gender} · ${p.city} · ${p.occupation || '—'}</strong>
      <span class="status">${p.segment} · ${p.role} · 对象 ${p.subject || '本人'}</span>
      <span class="status">家庭：${p.family || '—'} · 阶段 ${p.osa?.stage || '—'} / ${p.osa?.severity || '—'}</span>
    </div>

    ${roommateNote}
    ${kolNote}
    ${simPanel}

    <div class="task-card">
      <div class="task-label">任务卡</div>
      <p><span class="k">起点情境</span> ${j.entry_situation || '—'}</p>
      <p><span class="k">谁在推动</span> ${j.job_owner || p.role} · <span class="k">正在做的事</span> ${j.core_job || jobLabel(j.job_id) || '—'}</p>
      <p><span class="k">当前卡在</span> <strong>${j.current_step || '—'}</strong></p>
      ${renderPersonaJobPath(p)}
      <p class="job-statement">${j.job_statement || p.mindset?.core_motive || ''}</p>
      <div class="outcome-list">
        <div class="outcome-list-label">TA 最在乎什么</div>
        <p class="outcome-list-hint">色条越长越在乎；满意越短、缺口越大，话术越该优先打。</p>
        ${(
          [...dos]
            .sort((a, b) => (b.importance - b.satisfaction) - (a.importance - a.satisfaction))
            .map(d => {
              const improved = sim?.outcome_improved?.includes(d.id);
              const unresolved = sim?.unresolved_outcomes?.includes(d.id);
              const mark = improved
                ? '<span class="oc-sim-mark yes">本次已改善</span>'
                : (unresolved ? '<span class="oc-sim-mark no">本次未改善</span>' : '');
              const simState = improved ? 'yes' : (unresolved ? 'no' : '');
              return renderOutcomeCard(d, { simMark: mark, simState });
            })
            .join('')
        ) || '<p class="status">暂无期望结果</p>'}
      </div>
      <div class="force-row">
        ${forceChip('push', forces.push)}
        ${forceChip('pull', forces.pull)}
        ${forceChip('anxiety', forces.anxiety)}
        ${forceChip('alt', forces.habit_or_alternative)}
      </div>
      <p class="status" style="margin-top:0.5rem">样本来源：${evidenceLabel(p.evidence_refs)}</p>
      ${p.mindset?.quote ? `<p class="quote">「${p.mindset.quote}」</p>` : ''}
    </div>

    <details class="demo-layer" open>
      <summary>动机、恐惧与维度权重</summary>
      <div class="mind-box" style="margin-top:0.5rem">
        <p><strong>动机</strong> ${p.mindset?.core_motive || '—'}</p>
        <p style="margin-top:0.4rem"><strong>恐惧</strong> ${p.mindset?.fear || '—'}</p>
        <p style="margin-top:0.4rem"><strong>决策逻辑</strong> ${p.mindset?.decision_logic || '—'}</p>
      </div>
      <p style="font-size:0.85rem;margin-top:0.75rem"><strong>主导关注维度</strong></p>
      ${domHtml}
    </details>

    <div id="memory-timeline" class="mind-box memory-box" style="margin-top:0.75rem">
      <strong>经历时间线</strong>（加载中…）
    </div>
  `;
  loadMemories(p.id);
  document.getElementById('btn-jump-result')?.addEventListener('click', () => {
    selectPersona(p.id, { scrollTo: 'result' });
  });
  bindVerifyButtons(document.getElementById('persona-detail'), document.getElementById('campaign-text')?.value || '');
  document.getElementById('btn-reset-one-memory')?.addEventListener('click', async (ev) => {
    ev.stopPropagation();
    if (!confirm(`确定清除 ${p.name} 的记忆？`)) return;
    try {
      await api(`/api/personas/${p.id}/memories/reset`, { method: 'POST' });
      personas = await api('/api/personas');
      renderDetail();
      renderPersonaList();
    } catch (e) {
      alert(e.message);
    }
  });
}

function bindVerifyButtons(root, campaign) {
  if (!root) return;
  root.querySelectorAll('.btn-verify').forEach(btn => {
    if (btn.dataset.bound === '1') return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      const note = prompt('可选：输入短证据（销售/退货/停用等）', '') || '';
      try {
        await api('/api/verify', {
          method: 'POST',
          body: JSON.stringify({
            persona_id: btn.dataset.pid,
            campaign,
            status: btn.dataset.status,
            note,
            decision: btn.dataset.decision,
          }),
        });
        btn.textContent = '✓ ' + btn.textContent;
        btn.disabled = true;
      } catch (e) {
        alert(e.message);
      }
    });
  });
}

async function loadMemories(personaId) {
  const box = document.getElementById('memory-timeline');
  if (!box) return;
  try {
    const evo = await api(`/api/personas/${personaId}/memories`);
    if (!evo.memories?.length) {
      box.innerHTML = '<strong>经历时间线</strong><p class="status" style="margin-top:0.4rem">尚无经历。勾选「消费者有记忆」后测试，这里会记录 JTBD 步骤变化。</p>';
      return;
    }
    const refl = (evo.reflections || []).map(r => `<li>💡 ${r}</li>`).join('');
    const mems = evo.memories.slice().reverse().slice(0, 6).map(m =>
      `<li>${m.type === 'reflection' ? '💡' : `Day ${m.day}`} ${m.content}${m.step_before ? ` <span class="status">(当时 Step: ${m.step_before})</span>` : ''}</li>`
    ).join('');
    box.innerHTML = `
      <strong>经历时间线</strong> <span class="status">· ${evo.day} 天</span>
      ${refl ? `<ul style="margin:0.5rem 0 0;padding-left:1.1rem;font-size:0.82rem">${refl}</ul>` : ''}
      <ul style="margin:0.5rem 0 0;padding-left:1.1rem;font-size:0.82rem">${mems}</ul>
    `;
  } catch {
    box.innerHTML = '<p class="status">经历加载失败</p>';
  }
}

function clearResults(message) {
  lastSimResults = [];
  lastSimMeta = { campaign_hits: [], interventions: [], use_llm: false, use_memory: false };
  const countEl = document.getElementById('result-count');
  if (countEl) countEl.textContent = '';
  const hm = document.getElementById('result-heatmap');
  if (hm) hm.innerHTML = '';
  const summaryEl = document.getElementById('result-summary');
  if (summaryEl) { summaryEl.hidden = true; summaryEl.innerHTML = ''; }
  const el = document.getElementById('result-grid');
  if (el) {
    el.className = 'result-list';
    el.innerHTML = `<div class="empty">${message || '运行 Campaign 测试后，逐人反馈将显示在这里'}</div>`;
  }
  const hitsEl = document.getElementById('campaign-hits');
  if (hitsEl) hitsEl.innerHTML = '';
  const exportBtn = document.getElementById('btn-export-excel');
  if (exportBtn) exportBtn.disabled = true;
  renderPersonaList();
  if (selectedId) renderDetail();
}

function renderHeatmap(results) {
  const el = document.getElementById('result-heatmap');
  if (!el) return;
  if (!results?.length) {
    el.innerHTML = '';
    return;
  }
  const outcomeIds = [...new Set(results.flatMap(r => [
    ...(r.outcome_improved || []),
    ...(r.unresolved_outcomes || []),
  ]))];
  const headerOutcomes = outcomeIds.map(o => {
    const short = outcomeLabel(o);
    const full = outcomeName(o);
    return `<th class="hm-col" title="${full}（${o}）"><span class="hm-label">${short}</span></th>`;
  }).join('');
  const rows = results.map(r => {
    const cells = outcomeIds.map(oid => {
      const tip = outcomeLabel(oid);
      if ((r.outcome_improved || []).includes(oid)) {
        return `<td class="hm-yes" title="${tip} · 已改善">改善</td>`;
      }
      if ((r.unresolved_outcomes || []).includes(oid)) {
        return `<td class="hm-no" title="${tip} · 尚未解决">未解</td>`;
      }
      return '<td class="hm-na">—</td>';
    }).join('');
    const active = r.persona_id === selectedId ? ' linked-active' : '';
    const dec = r.decision || '';
    const decLabel = decisionLabel(dec);
    const w = r.willingness != null ? `${r.willingness}/10` : '';
    return `<tr class="hm-row${active}" data-pid="${r.persona_id}" title="点击查看 ${r.persona_name} 的画像">
      <th class="hm-name">${r.persona_name}</th>
      <td class="hm-decision ${dec}" title="判定：${decLabel}${w ? ` · 意愿 ${w}` : ''}"><span class="hm-dec-tag ${dec}">${decLabel}</span>${w ? `<small class="hm-w">${w}</small>` : ''}</td>
      ${cells}
    </tr>`;
  }).join('');
  const outcomeHint = outcomeIds.length
    ? '· 右侧列为关注点改善/未解'
    : '· 本次未产出 Outcome 映射';
  el.innerHTML = `
    <p class="status" style="margin-bottom:0.4rem">消费者对照（行=人 · <strong>判定</strong>在人名右侧）· 共 ${results.length} 人 ${outcomeHint} · <em>点击行可打开画像</em></p>
    <div class="heatmap-scroll">
      <table class="heatmap">
        <thead><tr><th class="hm-name">消费者</th><th class="hm-decision-h">判定</th>${headerOutcomes}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
  el.querySelectorAll('tr.hm-row').forEach(tr => {
    tr.addEventListener('click', () => selectPersona(tr.dataset.pid, { scrollTo: 'detail' }));
  });
}

function renderResults(data) {
  lastSimResults = data.results || [];
  lastSimMeta = {
    campaign_hits: data.campaign_hits || [],
    interventions: data.interventions || [],
    use_llm: !!document.getElementById('use-llm-simulate')?.checked,
    use_memory: !!document.getElementById('use-memory')?.checked,
  };
  const exportBtn = document.getElementById('btn-export-excel');
  if (exportBtn) exportBtn.disabled = !lastSimResults.length;
  const n = lastSimResults.length;
  const countEl = document.getElementById('result-count');
  if (countEl) {
    const total = typeof personas !== 'undefined' ? personas.length : n;
    countEl.textContent = n
      ? (total && total !== n ? `本次 ${n} / 库中 ${total} 人` : `共 ${n} 人`)
      : '';
  }
  const hitsEl = document.getElementById('campaign-hits');
  if (hitsEl) hitsEl.innerHTML = renderCampaignHitPanel(data);
  renderHeatmap(lastSimResults);
  const summaryEl = document.getElementById('result-summary');
  const el = document.getElementById('result-grid');
  if (!el) return;
  if (!lastSimResults.length) {
    el.innerHTML = '<div class="empty">运行测试后，结果将显示在这里</div>';
    if (summaryEl) { summaryEl.hidden = true; summaryEl.innerHTML = ''; }
    renderPersonaList();
    return;
  }

  const counts = { advance: 0, hesitate: 0, reject: 0, na: 0 };
  lastSimResults.forEach(r => { if (counts[r.decision] != null) counts[r.decision]++; });
  if (summaryEl) {
    summaryEl.hidden = false;
    summaryEl.innerHTML = `
      <span class="rs-chip advance">推进 <strong>${counts.advance}</strong></span>
      <span class="rs-chip hesitate">犹豫 <strong>${counts.hesitate}</strong></span>
      <span class="rs-chip reject">拒绝 <strong>${counts.reject}</strong></span>
      <span class="rs-chip na">无关 <strong>${counts.na}</strong></span>
      <span class="rs-hint">点人名 → 画像；点「展开」→ 看完整反馈</span>
    `;
  }

  const mem = document.getElementById('use-memory')?.checked;
  const campaign = document.getElementById('campaign-text')?.value || '';
  el.className = 'result-list';
  el.innerHTML = lastSimResults.map(r => {
    const p = personas.find(x => x.id === r.persona_id);
    const job = p?.jtbd?.core_job || '';
    const step = p?.jtbd?.current_step || '';
    const snip = String(r.reaction || '').replace(/\s+/g, ' ').trim();
    const snipShort = snip.length > 72 ? `${snip.slice(0, 72)}…` : snip;
    const active = r.persona_id === selectedId ? ' linked-active' : '';
    const willPct = Math.max(0, Math.min(100, (Number(r.willingness) || 0) * 10));
    return `
    <article class="result-row${active}" data-pid="${r.persona_id}">
      <div class="result-row-main">
        <button type="button" class="result-row-id" data-open-persona="${r.persona_id}" title="打开画像">
          <span class="rr-emoji">${p?.emoji || ''}</span>
          <span class="rr-name">${r.persona_name}</span>
        </button>
        <span class="decision ${r.decision}">${decisionLabel(r.decision)}</span>
        <div class="rr-will" title="意愿 ${r.willingness}/10">
          <span class="rr-will-num">${r.willingness}<small>/10</small></span>
          <span class="rr-will-track"><span class="rr-will-fill ${r.decision}" style="width:${willPct}%"></span></span>
        </div>
        <p class="rr-snip">${snipShort || '（无反馈文案）'}</p>
        <button type="button" class="btn btn-ghost btn-sm rr-toggle" aria-expanded="false">展开</button>
      </div>
      <div class="result-row-signals">
        ${renderResultBoostLine(r.interventions)}
        ${renderOutcomeStatusCompact(r)}
      </div>
      <div class="result-row-detail" hidden>
        ${job || step ? `<p class="result-persona-ctx">${job}${step ? ` · 卡在「${step}」` : ''}</p>` : ''}
        <p class="result-reaction">${r.reaction || ''}</p>
        ${r.reasoning ? `<p class="rr-reason">${r.reasoning}</p>` : ''}
        ${renderPersonaBoost(r.interventions, lastSimMeta.interventions)}
        ${renderOutcomeStatus(r)}
        <p class="status" style="margin-top:0.3rem">${r.mode === 'llm' ? 'LLM' : '规则'} · ${mem ? '有记忆' : '静态'}</p>
        <div class="verify-row">
          <span class="status">真实验证</span>
          <button class="btn btn-ghost btn-sm btn-verify" data-status="verified" data-pid="${r.persona_id}" data-decision="${r.decision}">已验证</button>
          <button class="btn btn-ghost btn-sm btn-verify" data-status="unverified" data-pid="${r.persona_id}" data-decision="${r.decision}">未验证</button>
          <button class="btn btn-ghost btn-sm btn-verify" data-status="opposite" data-pid="${r.persona_id}" data-decision="${r.decision}">方向相反</button>
        </div>
      </div>
    </article>`;
  }).join('');

  el.querySelectorAll('[data-open-persona]').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      selectPersona(btn.dataset.openPersona, { scrollTo: 'detail' });
    });
  });
  el.querySelectorAll('.result-row').forEach(row => {
    row.addEventListener('click', (ev) => {
      if (ev.target.closest('.btn-verify, .rr-toggle, [data-open-persona]')) return;
      selectPersona(row.dataset.pid, { scrollTo: 'detail' });
    });
  });
  el.querySelectorAll('.rr-toggle').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const row = btn.closest('.result-row');
      const detail = row?.querySelector('.result-row-detail');
      if (!detail) return;
      const open = detail.hidden;
      detail.hidden = !open;
      btn.textContent = open ? '收起' : '展开';
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      row.classList.toggle('is-open', open);
    });
  });

  bindVerifyButtons(el, campaign);

  renderPersonaList();
  if (selectedId) renderDetail();
  else if (lastSimResults[0]) selectPersona(lastSimResults[0].persona_id, { scrollTo: 'detail' });
}

function updateSimModeHint() {
  const el = document.getElementById('sim-mode-hint');
  if (!el) return;
  const mem = document.getElementById('use-memory')?.checked;
  const llm = document.getElementById('use-llm-simulate')?.checked;
  if (mem && llm) {
    el.textContent = '记忆 + 独立思考：参考过往经历；LLM 文案可能略有波动，判定已与规则门控对齐。';
  } else if (mem) {
    el.textContent = '记忆 + 规则：写入时间线，按 Outcome/Force 推演；同一输入结果稳定。';
  } else if (llm) {
    el.textContent = '独立思考：反馈文案更口语；关闭此项则走规则引擎（分数/标签更稳定）。';
  } else {
    el.textContent = '规则模式：以「是否推动任务进展」判定，同一输入结果稳定。';
  }
}

async function downloadMemories() {
  const res = await fetch(API + '/api/memories/export');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  const blob = await res.blob();
  let filename = 'mindsim_memories.json';
  const disp = res.headers.get('Content-Disposition') || '';
  const m = disp.match(/filename="?([^";]+)"?/);
  if (m) filename = m[1];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** 将本次行动话术 + 画像 + 反馈 + 判定结果打包为 Excel 下载 */
async function exportCampaignExcel() {
  if (!lastSimResults.length) {
    throw new Error('暂无测试结果，请先运行 Campaign 测试');
  }
  const res = await fetch(API + '/api/export/campaign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      campaign: document.getElementById('campaign-text')?.value || '',
      results: lastSimResults,
      campaign_hits: lastSimMeta.campaign_hits || [],
      interventions: lastSimMeta.interventions || [],
      use_llm: !!lastSimMeta.use_llm,
      use_memory: !!lastSimMeta.use_memory,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    throw new Error(typeof detail === 'string' ? detail : (detail?.[0]?.msg || res.statusText));
  }
  const blob = await res.blob();
  let filename = 'MindSim_Campaign.xlsx';
  const disp = res.headers.get('Content-Disposition') || '';
  const m = disp.match(/filename="?([^";]+)"?/);
  if (m) filename = m[1];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderFactors() {
  const el = document.getElementById('factor-list');
  if (!el) return;
  const groups = {};
  factors.forEach(f => {
    if (!groups[f.group]) groups[f.group] = [];
    groups[f.group].push(f);
  });
  el.innerHTML = Object.entries(groups).map(([g, items]) => `
    <div class="group-title">${g} 组 · ${g === 'A' ? '购买触发' : '品牌选择'}</div>
    ${items.map(f => `
      <div class="factor-row">
        <div>${badgeGroup(f.group)}</div>
        <div>
          <strong>${f.id}</strong> ${f.name}
          <div class="status" style="margin-top:0.2rem">${f.definition}</div>
          <div class="status">力：${f.force_default || '—'} · 关联任务：${
            (f.job_ids || []).length
              ? (f.job_ids || []).map(id => `<span class="job-chip" title="${id}">${jobLabel(id)}</span>`).join(' ')
              : '—'
          }</div>
          ${weightBar(f.weight)}
        </div>
        <label class="toggle-label"><input type="checkbox" data-toggle="${f.id}" ${f.enabled ? 'checked' : ''} /> 启用</label>
      </div>
    `).join('')}
  `).join('');

  el.querySelectorAll('[data-toggle]').forEach(cb => {
    cb.addEventListener('change', async () => {
      await api(`/api/factors/${cb.dataset.toggle}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled: cb.checked }),
      });
      await loadFactors();
    });
  });
}
