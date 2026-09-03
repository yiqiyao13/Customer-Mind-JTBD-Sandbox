const API = '';

let factors = [];
let personas = [];
let outcomes = [];
let jobTrees = [];
let jobsById = {};
let selectedId = null;
let lastSimResults = []; // 最近一次测试结果，用于画像↔反馈联动
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

function renderOutcomeCard(d, { simMark = '' } = {}) {
  const short = outcomeLabel(d.id);
  const full = outcomeName(d.id);
  const want = Number(d.importance) || 0;
  const have = Number(d.satisfaction) || 0;
  const gap = Math.max(0, want - have);
  const gapPct = (gap / 10) * 100;
  return `
    <article class="outcome-card">
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

async function loadOutcomes() {
  try {
    outcomes = await api('/api/outcomes');
  } catch {
    outcomes = [];
  }
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
        <span class="k">任务路径</span>
        <strong>${tree.id} ${tree.name}</strong>
        ${current ? `<span class="status">· 当前：${current}</span>` : ''}
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

async function loadPersonas() {
  personas = await api('/api/personas');
  if (typeof renderPersonaList === 'function') renderPersonaList();
  if (selectedId && typeof renderDetail === 'function') renderDetail();
}

function initEntryThemes() {
  const el = document.getElementById('entry-themes');
  if (!el) return;
  el.innerHTML = ENTRY_THEMES.map(t => `
    <span class="chip ${selectedEntryThemes.has(t) ? 'active' : ''}" data-theme="${t}">${t}</span>
  `).join('');
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
  chipGroup('filter-segments', ['关系驱动型','健康焦虑自用型','经济受限型','长期照护型','依从挣扎型'], 'segment');
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
    document.querySelector(`.result-card[data-pid="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function highlightLinkedResults() {
  document.querySelectorAll('.result-card').forEach(card => {
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
    return `
    <div class="persona-item ${p.id === selectedId ? 'active' : ''}" data-id="${p.id}">
      <div class="persona-item-top">
        <strong>${p.emoji} ${p.name}</strong>
        ${simTag}
      </div>
      <div class="meta">${p.id} · ${p.occupation || ''} · ${p.jtbd?.core_job || p.segment}</div>
      <div class="meta">当前：${p.jtbd?.current_step || p.osa?.stage || '—'}</div>
    </div>`;
  }).join('');
  el.querySelectorAll('.persona-item').forEach(item => {
    item.addEventListener('click', () => {
      selectPersona(item.dataset.id, { scrollTo: lastSimResults.length ? 'result' : 'detail' });
    });
  });
}

function outcomeName(id) {
  return outcomes.find(o => o.id === id)?.name || id;
}

/** 面向用户的短名：热力图列头、结果卡片用，避免只显示 O1/O2 */
function outcomeLabel(id) {
  const o = outcomes.find(x => x.id === id);
  if (!o) return id;
  if (o.label) return o.label;
  // 无 label 时从正式名里抽「」内短语，仍失败则退回 id
  const m = String(o.name || '').match(/「([^」]+)」/);
  return m ? m[1] : (o.name || id);
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
    el.innerHTML = '<div class="empty">← 从左侧选择一位消费者查看画像</div>';
    return;
  }
  const j = p.jtbd || {};
  const dos = (j.desired_outcomes || []).slice(0, 3);
  const forces = j.forces || {};
  const domHtml = p.dominant_features.map(d => {
    const f = factors.find(x => x.id === d.code);
    return `<div style="margin-bottom:0.4rem">${badgeGroup(f?.group || 'A')} ${f?.name || d.code} ${weightBar(d.weight)}</div>`;
  }).join('');

  const sim = getSimResult(p.id);
  const simPanel = sim ? `
    <div class="sim-link-panel" id="sim-link-panel">
      <div class="sim-link-head">
        <div class="task-label" style="margin:0">本次测试反馈</div>
        <span class="decision ${sim.decision}">${decisionLabel(sim.decision)}</span>
      </div>
      <p class="sim-link-reaction">${sim.reaction}</p>
      <p class="status" style="margin-top:0.4rem">
        已改善：${formatOutcomeList(sim.outcome_improved)} ·
        未解决：${formatOutcomeList(sim.unresolved_outcomes)}
        ${sim.next_step ? ` · 下一步：<strong>${sim.next_step}</strong>` : ''}
      </p>
      <button type="button" class="btn btn-ghost btn-sm" id="btn-jump-result">在结果区查看此卡 ↓</button>
    </div>
  ` : (lastSimResults.length ? `
    <div class="sim-link-panel muted">
      <p class="status">此人未出现在最近一次测试结果中。</p>
    </div>
  ` : '');

  el.innerHTML = `
    <div class="card-header" style="border:none;padding:0;margin-bottom:0.75rem">
      <h2><span class="dot"></span>${p.emoji} ${p.name}</h2>
      <div class="row" style="gap:0.5rem">
        <span class="status">${p.id}</span>
        <button class="btn btn-danger btn-sm" id="btn-reset-one-memory" data-id="${p.id}">清除记忆</button>
      </div>
    </div>

    ${simPanel}

    <div class="task-card">
      <div class="task-label">任务卡 · JTBD</div>
      <p><span class="k">起点情境</span> ${j.entry_situation || '—'}</p>
      <p><span class="k">谁在推动</span> ${j.job_owner || p.role} · <span class="k">正在做的事</span> ${j.core_job || j.job_id || '—'}</p>
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
                : (unresolved ? '<span class="oc-sim-mark no">本次未解决</span>' : '');
              return renderOutcomeCard(d, { simMark: mark });
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
      <p class="status" style="margin-top:0.5rem">证据：${(p.evidence_refs || ['synthetic']).join(' · ')}</p>
      ${p.mindset?.quote ? `<p class="quote">「${p.mindset.quote}」</p>` : ''}
    </div>

    <details class="demo-layer">
      <summary>人口学与维度权重（第二层）</summary>
      <p class="status" style="margin-top:0.5rem">${p.age}岁 · ${p.gender} · ${p.city} · ${p.occupation}</p>
      <p class="status">分群 ${p.segment} · 角色 ${p.role} · 对象 ${p.subject || '本人'}</p>
      <p class="status">家庭：${p.family || '—'} · OSA ${p.osa?.stage} / ${p.osa?.severity}</p>
      <div class="mind-box" style="margin-top:0.5rem">
        <p><strong>动机</strong> ${p.mindset?.core_motive}</p>
        <p style="margin-top:0.4rem"><strong>恐惧</strong> ${p.mindset?.fear}</p>
      </div>
      <p style="font-size:0.85rem;margin-top:0.75rem"><strong>主导关注</strong></p>
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
  const countEl = document.getElementById('result-count');
  if (countEl) countEl.textContent = '';
  const hm = document.getElementById('result-heatmap');
  if (hm) hm.innerHTML = '';
  const el = document.getElementById('result-grid');
  if (el) {
    el.innerHTML = `<div class="empty">${message || '运行 Campaign 测试后，逐人反馈将显示在这里'}</div>`;
  }
  const hitsEl = document.getElementById('campaign-hits');
  if (hitsEl) hitsEl.textContent = '';
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
  if (!outcomeIds.length) {
    el.innerHTML = `<p class="status">共 ${results.length} 人 · 本次未产出 Outcome 映射（可检查话术是否命中干预）</p>`;
    return;
  }
  const header = outcomeIds.map(o => {
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
    return `<tr class="hm-row${active}" data-pid="${r.persona_id}" title="点击查看 ${r.persona_name} 的画像"><th class="hm-name">${r.persona_name}</th>${cells}</tr>`;
  }).join('');
  el.innerHTML = `
    <p class="status" style="margin-bottom:0.4rem">消费者关注点对照（行=人 · 列=TA想达成的结果）· 共 ${results.length} 人 · <em>点击行可打开画像</em></p>
    <div class="heatmap-scroll">
      <table class="heatmap">
        <thead><tr><th class="hm-name">消费者</th>${header}</tr></thead>
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
  const n = lastSimResults.length;
  const countEl = document.getElementById('result-count');
  if (countEl) {
    const total = typeof personas !== 'undefined' ? personas.length : n;
    countEl.textContent = n
      ? (total && total !== n ? `本次 ${n} / 库中 ${total} 人` : `共 ${n} 人`)
      : '';
  }
  const hitsEl = document.getElementById('campaign-hits');
  if (hitsEl) {
    const parts = [];
    if (data.campaign_hits?.length) parts.push(`维度：${data.campaign_hits.join('、')}`);
    if (data.interventions?.length) parts.push(`干预：${data.interventions.join('、')}`);
    hitsEl.textContent = parts.join(' · ') || '点击下方卡片或热力图行，可联动打开画像';
  }
  renderHeatmap(lastSimResults);
  const el = document.getElementById('result-grid');
  if (!el) return;
  if (!lastSimResults.length) {
    el.innerHTML = '<div class="empty">运行测试后，结果将显示在这里</div>';
    renderPersonaList();
    return;
  }
  const mem = document.getElementById('use-memory')?.checked;
  const campaign = document.getElementById('campaign-text')?.value || '';
  el.innerHTML = lastSimResults.map(r => {
    const p = personas.find(x => x.id === r.persona_id);
    const job = p?.jtbd?.core_job || '';
    const step = p?.jtbd?.current_step || '';
    const motive = (p?.mindset?.core_motive || '').slice(0, 42);
    const active = r.persona_id === selectedId ? ' linked-active' : '';
    return `
    <div class="result-card${active}" data-pid="${r.persona_id}" role="button" tabindex="0" title="点击查看完整画像">
      <div class="row" style="justify-content:space-between;margin-bottom:0.45rem">
        <strong>${p?.emoji || ''} ${r.persona_name}</strong>
        <span class="decision ${r.decision}">${decisionLabel(r.decision)}</span>
      </div>
      ${job || step ? `<p class="result-persona-ctx">${job}${step ? ` · 卡在「${step}」` : ''}</p>` : ''}
      ${motive ? `<p class="result-persona-motive">${motive}${motive.length >= 42 ? '…' : ''}</p>` : ''}
      <p class="result-reaction">${r.reaction}</p>
      ${r.reasoning ? `<p class="status" style="font-style:italic;margin-top:0.4rem">💭 ${r.reasoning}</p>` : ''}
      <p class="status" style="margin-top:0.4rem">
        ${r.next_step ? `下一步：<strong>${r.next_step}</strong> · ` : ''}
        已改善：${formatOutcomeList(r.outcome_improved)} ·
        未解决：${formatOutcomeList(r.unresolved_outcomes)}
      </p>
      <p class="status" style="margin-top:0.35rem">意愿 ${r.willingness}/10 · ${r.mode === 'llm' ? 'LLM' : '规则'} · ${mem ? '有记忆' : '静态'} · <span class="link-hint">查看画像 →</span></p>
      <div class="verify-row">
        <span class="status">真实验证</span>
        <button class="btn btn-ghost btn-sm btn-verify" data-status="verified" data-pid="${r.persona_id}" data-decision="${r.decision}">已验证</button>
        <button class="btn btn-ghost btn-sm btn-verify" data-status="unverified" data-pid="${r.persona_id}" data-decision="${r.decision}">未验证</button>
        <button class="btn btn-ghost btn-sm btn-verify" data-status="opposite" data-pid="${r.persona_id}" data-decision="${r.decision}">方向相反</button>
      </div>
    </div>`;
  }).join('');

  el.querySelectorAll('.result-card').forEach(card => {
    card.addEventListener('click', (ev) => {
      if (ev.target.closest('.btn-verify')) return;
      selectPersona(card.dataset.pid, { scrollTo: 'detail' });
    });
    card.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        selectPersona(card.dataset.pid, { scrollTo: 'detail' });
      }
    });
  });

  el.querySelectorAll('.btn-verify').forEach(btn => {
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

  renderPersonaList();
  if (selectedId) renderDetail();
  else if (lastSimResults[0]) selectPersona(lastSimResults[0].persona_id, { scrollTo: 'detail' });
}

function updateSimModeHint() {
  const el = document.getElementById('sim-mode-hint');
  if (!el) return;
  const mem = document.getElementById('use-memory')?.checked;
  const llm = document.getElementById('use-llm-simulate')?.checked;
  if (mem && llm) el.textContent = '记忆 + 独立思考：参考过往经历，测后写入 JTBD 时间线。';
  else if (mem) el.textContent = '记忆 + 规则：写入时间线，按 Outcome/Force 推演。';
  else if (llm) el.textContent = '静态 + 独立思考：每次独立判断，不积累记忆。';
  else el.textContent = '静态 + 规则：以「是否推动任务进展」判定。';
}

async function downloadMemories() {
  const res = await fetch('/api/memories/export');
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
