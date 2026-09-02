# 呼吸机消费者心智模拟系统 — JTBD 改造开发文档（Cursor 施工版 v3）

> **唯一事实源**。Cursor 通读本文档后即可独立完成改造。
> **改造对象**：`consumer-mind-sim`（FastAPI 后端 + 原生前端 + `data/factors.json` 维度数据库）。
> **数据底座**：548 条真实用户语料 → 7 主 Job + 14 子 Job + 22 决策维度 + 9 期望结果（Outcome）。

---

## 0. 改造目标（一句话）

把现有系统从「**维度 + persona 权重拼装**」升级为「**JTBD 任务本体驱动**」：

> 从不同患者/家庭起点出发，识别他们想完成的 **Job**、卡在哪个 **Step**、最在意哪项 **Outcome**、什么动作能解除关键**阻力（Force）**。

核心工程改动只有两条：
1. 为 persona 增加 **Job / Step / Outcome / Force** 四层状态；
2. 让 simulation 以「**是否推动任务进展**」而非「**命中几个关键词**」为判定依据。

其余数据、界面、记忆、验证机制都围绕这两条展开。

---

## 1. 现状盘点（改造前）

```
consumer-mind-sim/
├── SPEC.md                          # v2 施工版（本文档取代之）
├── README.md
├── data/
│   ├── factors.json                 # 17 维度（A1-A9, B1-B8），无 JTBD 字段
│   ├── personas.json                # 已生成心智
│   └── evolution.json               # 记忆/演化
├── backend/
│   ├── main.py                      # FastAPI + CORS
│   ├── config.py
│   ├── schemas.py                   # Factor / Persona / SimulateResult / MemoryEntry
│   ├── routes/
│   │   ├── factors.py               # GET/POST/PUT/DELETE /api/factors
│   │   ├── generate.py              # POST /api/generate
│   │   └── simulate.py              # POST /api/simulate
│   └── services/
│       ├── factor_store.py          # factors 读写
│       ├── persona_store.py         # personas 读写
│       ├── persona_archetypes.py    # 分群模板
│       ├── persona_coherence.py     # 逻辑一致性校验
│       ├── prompt.py                # 生成 prompt
│       ├── fallback_gen.py          # 规则回退生成
│       ├── llm.py                   # LLM 客户端
│       ├── llm_simulate.py          # LLM 仿真
│       ├── simulate.py              # 规则仿真（decide_for）
│       └── memory.py                # MemoryEntry / PersonaEvolution
└── frontend/
    ├── index.html / js/app.js       # 主界面
    ├── admin.html                   # 维度管理
    └── css/app.css
```

**现有核心逻辑（需改造）：**
- `schemas.py::Persona`：`segment / role / subject / family / mindset / dominant_features / factor_weights / blockers / drivers / react`。
- `simulate.py::decide_for`：`命中主导维度 ≥2 → advance`，外加敏感度加权、共鸣分阈值。
- `prompt.py::build_generation_prompt`：注入 factors → 生成 N 个 persona。
- `memory.py`：`MemoryEntry`（observation/reflection）+ 阶段推进。

---

## 2. JTBD 核心概念

| 概念 | 定义 | 数据文件 | 例子 |
|---|---|---|---|
| **Job（任务）** | 消费者真正想完成的事（功能/社会/情感） | `jobs.json` | J1 恢复连续无扰的睡眠 |
| **Sub-Job（子任务）** | Job 拆解成的 14 个具体步骤，按 5 阶段组织 | `jobs.json.sub_jobs` | h 解决面罩适配 |
| **Entry Situation（起点情境）** | 触发决策的具体事件 | `jobs.json` 字段 | 伴侣分房、AHI 确诊、开车打盹 |
| **Job Owner（任务发起者）** | 谁在雇佣这个 Job（决策者≠使用者） | `jobs.json` 字段 | 本人 / 伴侣 / 子女 |
| **Outcome（期望结果）** | 可判断「是否改善」的成功标准 | `outcomes.json` | O3 最小化设备不适导致用不下去的风险 |
| **Force（决策力量）** | 推动/吸引/焦虑/替代四类力 | `factors.json` 字段 | push / pull / anxiety / habit |
| **Step（当前步骤）** | 消费者卡在哪个子任务 | persona.jtbd.current_step | 确认可用性 |

**分层架构（自上而下）：**

```text
真实证据（548 条语料 / 访谈 / 一线）
  → Job（起点情境 + 核心 Job + Job Owner）
    → Sub-Job / Step（5 阶段 14 步）
      → Outcome（期望结果）+ Force（决策力量）
        → factors（22 维度，作为证据层）
          → Persona（任务层 + 情境层 + 记忆层）
            → Campaign 推演（被推进的 Step、解除的阻力、下一步）
```

---

## 3. 数据资产定义（完整，可直接落盘）

> 以下三个文件必须新增/重写到 `data/` 目录。Cursor 直接按本文档生成文件内容。

### 3.1 `data/jobs.json`（7 主 Job + 14 子 Job + 5 阶段）

```jsonc
{
  "version": "1.0",
  "stages": ["认知确诊", "决策选购", "启动适应", "长期依从", "价值确认"],
  "jobs": [
    {
      "id": "J1",
      "name": "恢复连续无扰的睡眠",
      "category": "功能",
      "entry_situations": ["鼾声震天被本人/家人察觉", "夜间憋醒", "睡眠碎片化", "白天疲惫"],
      "job_owners": ["本人", "伴侣"],
      "statement": "当我整夜被鼾声和憋醒打断、第二天疲惫不堪时，我需要恢复连续、安静的睡眠，让自己和家人睡个整觉。",
      "step_ids": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "m"],
      "outcome_ids": ["O1", "O3", "O4"],
      "evidence": "以前睡觉呼噜震天，夜里总憋气惊醒（语料占比 35.8%，196/548）"
    },
    {
      "id": "J2",
      "name": "恢复白天的精力与清醒",
      "category": "功能",
      "entry_situations": ["白天嗜睡", "开车等红灯睡着", "开会打盹", "精力下降"],
      "job_owners": ["本人"],
      "statement": "当疲劳和嗜睡开始影响我开车、工作或照顾家人时，我需要恢复可靠的白天状态，并确认投入能带来实际改善。",
      "step_ids": ["a", "b", "c", "d", "e", "m"],
      "outcome_ids": ["O2"],
      "evidence": "以前开车等红灯都能睡着（5.3%，29/548）"
    },
    {
      "id": "J3",
      "name": "消除睡梦中出事的健康风险",
      "category": "功能",
      "entry_situations": ["AHI/血氧确诊", "最长呼吸暂停数十秒", "高血压/心脏等共病", "担心猝死"],
      "job_owners": ["本人", "家人"],
      "statement": "当我确认 OSA 可能与心脏病复发或恶化有关时，我需要建立一项能坚持的夜间管理方式，以更有把握地控制长期健康风险。",
      "step_ids": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "m"],
      "outcome_ids": ["O1", "O2", "O7"],
      "evidence": "AHI54.7，血氧最低40多，最长呼吸暂停74秒（23.4%，128/548）"
    },
    {
      "id": "J4",
      "name": "维持呼吸功能保住生命（重症）",
      "category": "功能",
      "entry_situations": ["ALS/渐冻症", "DMD 肌营养不良", "慢阻肺呼吸衰竭", "夜间低氧血症"],
      "job_owners": ["本人", "子女"],
      "statement": "当呼吸肌无力威胁到我的生命时，我需要可靠的呼吸支持来维持肺功能、避免呼吸衰竭，争取更多时间。",
      "step_ids": ["a", "d", "e", "j", "k", "l", "n"],
      "outcome_ids": ["O9"],
      "evidence": "渐冻人唯一不能省的就是呼吸机（10.4%，57/548）"
    },
    {
      "id": "J5",
      "name": "修复/维系亲密关系",
      "category": "社会情感",
      "entry_situations": ["伴侣分房", "伴侣长期失眠", "关系冲突/濒临破裂"],
      "job_owners": ["伴侣", "本人"],
      "statement": "当伴侣的打鼾长期破坏我的睡眠、情绪和关系时，我需要帮助我们恢复安静且能持续的夜间生活，又不让照护变成冲突。",
      "step_ids": ["a", "b", "c", "d", "f", "g", "h", "m"],
      "outcome_ids": ["O4"],
      "evidence": "结婚就分房睡了、老公呼噜震天响（8.8%，48/548）"
    },
    {
      "id": "J6",
      "name": "消除打呼丢人的羞耻感",
      "category": "社会情感",
      "entry_situations": ["宿舍/合租尴尬", "被录音", "女性身份羞耻", "社交尊严受损"],
      "job_owners": ["本人"],
      "statement": "当打呼让我在社交中丢脸、被疏远时，我需要恢复体面和社交尊严，又不显得过度在意。",
      "step_ids": ["a", "c", "d", "f", "h"],
      "outcome_ids": ["O1", "O5"],
      "evidence": "大学住宿舍成了全寝公敌（4.0%，22/548）"
    },
    {
      "id": "J7",
      "name": "履行对亲人的照护责任（孝道）",
      "category": "社会情感",
      "entry_situations": ["父母打鼾憋气", "老人健康担忧", "隔代亲", "子女代购"],
      "job_owners": ["子女"],
      "statement": "当我担心父母因打鼾/呼吸问题睡不好、出健康风险时，我需要为他们找到能坚持使用的方案，尽到照护责任。",
      "step_ids": ["a", "b", "d", "e", "f", "g", "h", "i", "j", "n"],
      "outcome_ids": ["O5", "O1", "O2"],
      "evidence": "给老爹上了s10、孙女嫌弃爷爷打呼噜（12.4%，68/548）"
    }
  ],
  "sub_jobs": [
    {"id": "a", "name": "搞清楚是不是病", "stage": "认知确诊", "job_ids": ["J1","J2","J3","J4","J5","J6","J7"]},
    {"id": "b", "name": "拿权威证据", "stage": "认知确诊", "job_ids": ["J1","J2","J3","J5","J7"]},
    {"id": "c", "name": "被数据击穿侥幸", "stage": "认知确诊", "job_ids": ["J1","J2","J3","J5","J6"]},
    {"id": "d", "name": "搞懂呼吸机", "stage": "决策选购", "job_ids": ["J1","J2","J3","J4","J5","J6","J7"]},
    {"id": "e", "name": "预算内选对", "stage": "决策选购", "job_ids": ["J1","J2","J3","J4","J7"]},
    {"id": "f", "name": "确认能适应", "stage": "决策选购", "job_ids": ["J1","J3","J5","J6","J7"]},
    {"id": "g", "name": "熬过适应期", "stage": "启动适应", "job_ids": ["J1","J3","J5","J7"]},
    {"id": "h", "name": "解决面罩适配", "stage": "启动适应", "job_ids": ["J1","J3","J5","J6","J7"]},
    {"id": "i", "name": "调对参数", "stage": "启动适应", "job_ids": ["J1","J3","J7"]},
    {"id": "j", "name": "坚持每天戴", "stage": "长期依从", "job_ids": ["J3","J4","J7"]},
    {"id": "k", "name": "维护清洁", "stage": "长期依从", "job_ids": ["J4"]},
    {"id": "l", "name": "处理副作用", "stage": "长期依从", "job_ids": ["J4"]},
    {"id": "m", "name": "看到效果获得确认感", "stage": "价值确认", "job_ids": ["J1","J2","J3","J5"]},
    {"id": "n", "name": "远程照护", "stage": "价值确认", "job_ids": ["J4","J7"]}
  ]
}
```

### 3.2 `data/outcomes.json`（9 Outcome）

> Outcome 必须写成「可判断是否改善的成功标准」，不是名词。

```jsonc
{
  "version": "1.0",
  "outcomes": [
    {"id": "O1", "name": "最小化「不确定是否生病/多严重」的不确定性", "factor_ids": ["A2","A3","A5","A11"]},
    {"id": "O2", "name": "最大化「治疗能改善健康/白天状态」的确认感", "factor_ids": ["B1","A4","A6"]},
    {"id": "O3", "name": "最小化「设备不适/漏气/噪音用不下去」的风险", "factor_ids": ["B2","B4","B9","B10"]},
    {"id": "O4", "name": "最大化「伴侣睡眠与家庭关系改善」的可预期性", "factor_ids": ["A1","A5"]},
    {"id": "O5", "name": "最小化「照护变成催促/冲突」的风险", "factor_ids": ["A8","B6","A1"]},
    {"id": "O6", "name": "最小化「首次投入+长期维护总成本」的不确定性", "factor_ids": ["A7","A9","B8","B5"]},
    {"id": "O7", "name": "最小化「长期无人指导/渠道不可信」的风险", "factor_ids": ["B3","B7"]},
    {"id": "O8", "name": "最小化「买了闲置浪费」的风险", "factor_ids": ["B11","A9","B4"]},
    {"id": "O9", "name": "最小化「重症呼吸支持不到位危及生命」的风险", "factor_ids": ["A10"]}
  ]
}
```

### 3.3 `data/factors.json`（22 维度 + JTBD 映射字段）

> 在现有 17 维度基础上新增 A10/A11/B9/B10/B11，并为**每条**追加 JTBD 字段：
> `jtbd_type`（统一 `outcome_evidence`）、`job_ids`、`outcome_ids`、`force_default`、`stage_scope`。
> **force 四类**：`push`（推动）/ `pull`（吸引）/ `anxiety`（焦虑阻力）/ `habit_or_alternative`（习惯或替代）。

```jsonc
{
  "version": "2.0",
  "factors": [
    // ============ A 组：购买决策触发 ============
    {"id":"A1","group":"A","name":"伴侣/室友因鼾声睡眠被剥夺，关系濒临崩溃","weight":9,
     "definition":"伴侣/室友/家人因鼾声分房、失眠、冲突，被迫考虑购买","keywords":["伴侣","老公","老婆","丈夫","妻子","室友","家人","另一半","分床","分房"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J5","J1"],"outcome_ids":["O4","O5"],"force_default":"push",
     "stage_scope":["察觉","就医确诊","决策纠结"]},
    {"id":"A2","group":"A","name":"智能手表/手环健康监测成为就医与购买的第一入口","weight":6,
     "definition":"智能手表/手环提示血氧呼吸异常，成为就医第一入口","keywords":["手表","可穿戴","手环","apple watch","智能手表","监测提示"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J3","J1"],"outcome_ids":["O1"],"force_default":"push",
     "stage_scope":["未察觉","察觉"]},
    {"id":"A3","group":"A","name":"AHI/血氧等量化确诊数据击穿「打鼾不是病」的侥幸","weight":6,
     "definition":"AHI、最低血氧、呼吸暂停时长等量化指标引发的恐惧","keywords":["ahi","血氧","呼吸暂停","监测数据","指标","多导"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J3","J1"],"outcome_ids":["O1"],"force_default":"push",
     "stage_scope":["察觉","就医确诊"]},
    {"id":"A4","group":"A","name":"白天嗜睡导致开车/开会危险，迫使正视睡眠问题","weight":8,
     "definition":"白天嗜睡、开车/工作打盹的安全焦虑","keywords":["白天","嗜睡","犯困","打盹","开车","疲劳"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J2","J3"],"outcome_ids":["O2"],"force_default":"push",
     "stage_scope":["察觉","就医确诊"]},
    {"id":"A5","group":"A","name":"夜间憋醒/呼吸暂停被本人或家人察觉","weight":9,
     "definition":"夜间憋醒、呼吸暂停、担心猝死","keywords":["夜间","窒息","憋气","憋醒","猝死","缺氧"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J3","J1","J5"],"outcome_ids":["O1","O4"],"force_default":"push",
     "stage_scope":["察觉","就医确诊"]},
    {"id":"A6","group":"A","name":"担心打鼾引发的血压/心脏/代谢等共病","weight":5,
     "definition":"高血压/糖尿病/心脏病等合并症与 OSA 关联","keywords":["高血压","糖尿病","心脏病","慢阻肺","共病","合并症"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J3"],"outcome_ids":["O2"],"force_default":"push",
     "stage_scope":["就医确诊","决策纠结"]},
    {"id":"A7","group":"A","name":"医保/国补/以旧换新等制度差异直接塑造购买决策","weight":6,
     "definition":"医保、政府补贴、以旧换新等政策红利","keywords":["国补","以旧换新","补贴","医保","惠民","政府","15%","政策"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3","J7"],"outcome_ids":["O6"],"force_default":"pull",
     "stage_scope":["决策纠结","购买"]},
    {"id":"A8","group":"A","name":"给长辈/孩子的孝心与隔代亲驱动，决策快比价弱","weight":6,
     "definition":"子女为父母购买、隔代亲推动","keywords":["父母","父亲","母亲","老人","长辈","孝心","爸妈"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J7"],"outcome_ids":["O5"],"force_default":"push",
     "stage_scope":["察觉","决策纠结","购买"]},
    {"id":"A9","group":"A","name":"二手低价/闲置转让充当低门槛试用渠道","weight":6,
     "definition":"二手市场降低试错门槛，作为入门渠道","keywords":["二手","闲置","翻新","回收","以租代买"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3"],"outcome_ids":["O6","O8"],"force_default":"habit_or_alternative",
     "stage_scope":["决策纠结","购买"]},
    {"id":"A10","group":"A","name":"ALS/DMD/慢阻肺等需呼吸支持，与治打鼾是两类需求","weight":10,
     "definition":"ALS/DMD/慢阻肺等需呼吸支持，与「治打鼾」是两类需求（新 Job）","keywords":["渐冻症","als","dmd","慢阻肺","肌营养不良","呼吸衰竭","呼吸支持","无创通气"],
     "enabled":true,"source":"语料提炼","note":"独立 J4 分支",
     "jtbd_type":"outcome_evidence","job_ids":["J4"],"outcome_ids":["O9"],"force_default":"push",
     "stage_scope":["就医确诊","长期依从"]},
    {"id":"A11","group":"A","name":"更年期/孕期/女性身份羞耻触发就医与购买","weight":7,
     "definition":"更年期雌激素下降/孕期体重/身份羞耻触发就医与购买","keywords":["孕期","孕晚期","更年期","雌激素","女生","女性"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J6","J3"],"outcome_ids":["O1"],"force_default":"anxiety",
     "stage_scope":["察觉","就医确诊"]},
    // ============ B 组：品牌选择 ============
    {"id":"B1","group":"B","name":"能否直观看到治疗效果数据，获得「确认感」","weight":7,
     "definition":"小程序同步睡眠数据、AHI 下降可视化带来的确认感","keywords":["数据","报告","同步","app","小程序","可视","监测记录"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J2","J3"],"outcome_ids":["O2"],"force_default":"pull",
     "stage_scope":["适应","依从习惯"]},
    {"id":"B2","group":"B","name":"面罩/头带等耗材适配度，决定能否坚持使用","weight":9,
     "definition":"面罩/头带舒适度与适配成本，决定依从/弃用","keywords":["面罩","头带","鼻枕","贴合","漏气","舒适","佩戴"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3","J5","J7"],"outcome_ids":["O3"],"force_default":"anxiety",
     "stage_scope":["启动适应","长期依从"]},
    {"id":"B3","group":"B","name":"售后口碑与召回事件是品牌信任的放大器/摧毁者","weight":8,
     "definition":"售后口碑、召回事件的信任影响","keywords":["售后","质保","保修","召回","维修","上门"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J3","J7"],"outcome_ids":["O7"],"force_default":"anxiety",
     "stage_scope":["决策纠结","长期依从"]},
    {"id":"B4","group":"B","name":"租赁/免费试戴显著降低决策风险与心理门槛","weight":7,
     "definition":"试戴、租赁、睡眠中心试戴（可医保）","keywords":["试戴","免费试","试用","租赁","可退","30天","无理由","体验"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3","J5"],"outcome_ids":["O3","O8"],"force_default":"pull",
     "stage_scope":["决策纠结","购买"]},
    {"id":"B5","group":"B","name":"进口价格锚定与国产替代之间的信任博弈","weight":10,
     "definition":"价格锚定 + 品牌信任博弈，品牌选择第一变量","keywords":["进口","国产","瑞思迈","resmed","飞利浦","伟康","鱼跃","瑞迈特","品牌"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3"],"outcome_ids":["O6"],"force_default":"anxiety",
     "stage_scope":["决策纠结","购买"]},
    {"id":"B6","group":"B","name":"名人公开使用呼吸机，降低「戴机丢人」心理门槛","weight":4,
     "definition":"名人/社会去污名化，降低心理门槛","keywords":["体面","小巧","隐形","好看","不丢人","颜值","名人","明星"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J6"],"outcome_ids":["O5"],"force_default":"pull",
     "stage_scope":["察觉","决策纠结"]},
    {"id":"B7","group":"B","name":"海淘/水货靠第三方工具+同侪验证建立渠道信任","weight":6,
     "definition":"官方/医院/水货/陌生渠道的信任差异","keywords":["三甲","医院","呼吸科","睡眠中心","挂号","医生","专家","睡眠门诊","海淘","代购"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J3","J7"],"outcome_ids":["O7"],"force_default":"anxiety",
     "stage_scope":["决策纠结","购买"]},
    {"id":"B8","group":"B","name":"预算约束与价格敏感度直接框定可选品牌","weight":7,
     "definition":"价格作为核心决策变量","keywords":["价格","原价","实付","降价","优惠","便宜","半价","包邮","特价","性价比","省钱","预算"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3","J7"],"outcome_ids":["O6"],"force_default":"anxiety",
     "stage_scope":["决策纠结","购买"]},
    {"id":"B9","group":"B","name":"无泡棉/消音棉老化等机器与耗材长期健康顾虑","weight":8,
     "definition":"无泡棉/消音棉老化/滤棉/纯净水/痘痘等机器与耗材长期健康顾虑","keywords":["泡棉","消音棉","无泡棉","滤棉","纯净水","痘痘","粉化","卫生"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3"],"outcome_ids":["O3"],"force_default":"anxiety",
     "stage_scope":["长期依从"]},
    {"id":"B10","group":"B","name":"出差/旅行/宿舍等移动场景对体积/续航/可托运的要求","weight":6,
     "definition":"出差/旅行/宿舍等移动场景对体积、续航、可托运的要求","keywords":["出差","旅行","托运","便携","mini","小巧","宿舍","飞机"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J2"],"outcome_ids":["O3"],"force_default":"pull",
     "stage_scope":["决策纠结","长期依从"]},
    {"id":"B11","group":"B","name":"担心「买了不用/戴不惯」闲置浪费，倾向先试后买/二手对冲","weight":8,
     "definition":"担心「买了不用/戴不惯」闲置浪费，倾向先试后买/租赁/二手对冲","keywords":["闲置","落灰","砸手里","买了不用","转卖","退货"],
     "enabled":true,"source":"语料提炼","note":"",
     "jtbd_type":"outcome_evidence","job_ids":["J1","J3"],"outcome_ids":["O8"],"force_default":"anxiety",
     "stage_scope":["决策纠结","购买"]}
  ]
}
```

---

## 4. 代码改造规格（逐文件）

> 顺序即实施顺序。每步给出「改什么 + 关键代码/字段」，Cursor 直接照做。

### 4.1 `backend/schemas.py` — 新增 JTBD 数据模型

**改动**：`Factor` 增加 JTBD 字段；`Persona` 增加 `jtbd`；新增 `Job`/`SubJob`/`Outcome`/`DesiredOutcome`/`ForceMap`；`SimulateResult`/`MemoryEntry` 增加结构化字段。

```python
# --- Factor 追加字段 ---
class Factor(BaseModel):
    # ...现有字段...
    jtbd_type: str = "outcome_evidence"
    job_ids: List[str] = Field(default_factory=list)
    outcome_ids: List[str] = Field(default_factory=list)
    force_default: str = "push"  # push | pull | anxiety | habit_or_alternative
    stage_scope: List[str] = Field(default_factory=list)

# --- 新增 Job 本体模型 ---
class Job(BaseModel):
    id: str
    name: str
    category: str = "功能"          # 功能 | 社会情感
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
    factor_ids: List[str] = Field(default_factory=list)

# --- Persona 追加 jtbd 对象 ---
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
    current_step: str = ""           # 子 Job 名，如「确认能适应」
    desired_outcomes: List[DesiredOutcome] = Field(default_factory=list)
    forces: ForceMap = Field(default_factory=ForceMap)

class Persona(BaseModel):
    # ...现有字段...
    jtbd: JTBDProfile = Field(default_factory=JTBDProfile)
    evidence_refs: List[str] = Field(default_factory=list)   # SOC-xxx / INT-xxx / synthetic

# --- SimulateResult 追加 ---
class SimulateResult(BaseModel):
    # ...现有字段...
    outcome_improved: List[str] = Field(default_factory=list)
    unresolved_outcomes: List[str] = Field(default_factory=list)
    next_step: str = ""

# --- MemoryEntry 追加结构化字段 ---
class MemoryEntry(BaseModel):
    # ...现有字段...
    step_before: str = ""
    outcome_changes: List[dict] = Field(default_factory=list)  # [{outcome_id, delta_satisfaction}]
    force_changes: List[dict] = Field(default_factory=list)    # [{factor_id, force, delta}]
```

### 4.2 新建 `backend/services/job_store.py` — 加载 Job/Outcome 本体

```python
from pathlib import Path
import json
from schemas import Job, SubJob, Outcome

ROOT = Path(__file__).resolve().parents[2]

def load_jobs() -> List[Job]:
    data = json.loads((ROOT / "data" / "jobs.json").read_text(encoding="utf-8"))
    return [Job.model_validate(j) for j in data["jobs"]]

def load_sub_jobs() -> List[SubJob]:
    data = json.loads((ROOT / "data" / "jobs.json").read_text(encoding="utf-8"))
    return [SubJob.model_validate(s) for s in data["sub_jobs"]]

def load_outcomes() -> List[Outcome]:
    data = json.loads((ROOT / "data" / "outcomes.json").read_text(encoding="utf-8"))
    return [Outcome.model_validate(o) for o in data["outcomes"]]
```

### 4.3 `backend/services/prompt.py` — 生成顺序改为「先 Job 再人设」

**核心变化**：生成 prompt 注入 jobs/outcomes，约束生成器「先选 Job → 选 desired outcomes → 选 forces → 再生成人口学」。

```python
def build_generation_prompt(count, factors, jobs, sub_jobs, outcomes) -> str:
    return f"""你是消费者心智画像生成器。基于以下 JTBD 任务本体与维度数据库，生成 {count} 个呼吸机消费者心智。

【任务本体 jobs】(id/名称/起点情境/发起者/statement/步骤)
{json.dumps([j.model_dump() for j in jobs], ensure_ascii=False, indent=2)}

【期望结果 outcomes】(id/成功标准)
{json.dumps([o.model_dump() for o in outcomes], ensure_ascii=False, indent=2)}

【决策维度 factors】(id/名称/权重/定义/force_default/job_ids/outcome_ids)
{json.dumps([f.model_dump() for f in factors], ensure_ascii=False, indent=2)}

【生成顺序 — 严格按此，禁止反向拼装】
1. 先从 jobs 中选一个 entry_situation、job_owner、core_job 和当前 job_step（子任务名）；
2. 为该 job_step 选 3-5 条 desired_outcomes，给出 importance（重要性）与 satisfaction（当前满意度）；
3. 从 factors 中选有证据关联的 push / pull / anxiety / habit_or_alternative 四类 force；
4. 再生成与上述任务一致的人口学、家庭、疾病情境；
5. 最后生成第一人称 react 模板，不得引入 facts 之外的新临床/行为事实；
6. 输出 evidence_refs；无真实来源时标 synthetic / hypothesis。

【覆盖要求】覆盖的对象是 Job × Entry Situation × Step，而非每个 factor 都做成一个人。{count} 个人要尽量覆盖 7 个 Job 与不同 job_owner（本人/伴侣/子女）。

【输出】只输出一个 JSON 数组，不要其他文字：
[ {{ ...persona 对象（含 jtbd 字段）... }} ]
"""
```

### 4.4 `backend/services/fallback_gen.py` — 规则回退按 Job 采样

**改动**：离线回退时，先按 Job 权重采样 `job_id` + `job_owner`，再选 2-4 个 `force_default` 维度的 factor 作 dominant_features，最后拼人口学。保证 `jtbd` 字段完整、编码合法（在 jobs/outcomes/factors 内）。

关键点：`jtbd.current_step` 从所选 Job 的 `step_ids` 中取一个；`desired_outcomes` 从 `job.outcome_ids` 取 3-5 个赋 importance/satisfaction。

### 4.5 `backend/services/simulate.py` — 替换 `decide_for`（**核心**）

**改造前**：命中主导维度 ≥2 → advance。

**改造后**：Campaign 先映射为 intervention claims → 映射为 outcome 改善 + force 变化 → 计算「关键 Outcome 是否改善」+「Pull+Push 是否 > Anxiety+Alternative」→ 输出 advance/hesitate/reject + 下一步。

新增 **intervention 映射表**（campaign 结构化属性 → 影响的 outcome/force）：

```python
INTERVENTION_MAP = {
    "hospital_endorsement": {"outcomes": ["O1", "O7"], "forces": [("B7", "pull")]},
    "data_visibility":     {"outcomes": ["O2"],        "forces": [("B1", "pull")]},
    "trial":               {"outcomes": ["O3", "O8"],  "forces": [("B4", "pull")]},
    "mask_fit_support":    {"outcomes": ["O3"],        "forces": [("B2", "anxiety", -2)]},
    "family_participation":{"outcomes": ["O4", "O5"],  "forces": [("A1", "push")]},
    "financing":           {"outcomes": ["O6"],        "forces": [("B8", "anxiety", -1)]},
    "trade_in":            {"outcomes": ["O6"],        "forces": [("A9", "habit_or_alternative")]},
    "after_sales":         {"outcomes": ["O7"],        "forces": [("B3", "anxiety", -2)]},
}
```

`decide_for` 新伪代码：

```python
def decide_for(persona, campaign, factors, outcomes, interventions):
    # 1. 识别 campaign 命中的 interventions（关键词→结构化，见 4.5b）
    active = detect_interventions(campaign)

    # 2. 计算每个 desired_outcome 是否被改善
    score = 0
    improved = []
    unresolved = []
    for do in persona.jtbd.desired_outcomes:
        if any(outcome_improved(do.id, active)):
            score += do.importance * evidence_strength(do.id, active)
            improved.append(do.id)
        else:
            unresolved.append(do.id)

    # 3. force balance：pull+push vs anxiety+habit
    for f in persona.jtbd.forces["pull"]:
        if activated(f, active): score += factor_weight(f)
    for f in persona.jtbd.forces["push"]:
        if activated(f, active): score += factor_weight(f)
    for f in persona.jtbd.forces["anxiety"]:
        if not addressed(f, active): score -= factor_weight(f)
    for f in persona.jtbd.forces["habit_or_alternative"]:
        if raises_switching_cost(f, active): score -= factor_weight(f)

    # 4. 关键 Outcome 是否被解决（required_outcome = 满意度最低且 importance 最高的）
    required = min(persona.jtbd.desired_outcomes, key=lambda d: d.satisfaction / d.importance)
    required_addressed = required.id in improved

    if score >= ADVANCE_THRESHOLD and required_addressed:
        decision, next_step = "advance", next_step_of(persona.jtbd.current_step)
    elif score >= HESITATE_THRESHOLD:
        decision, next_step = "hesitate", persona.jtbd.current_step
    else:
        decision, next_step = "reject", persona.jtbd.current_step

    return decision, improved, unresolved, next_step, willingness(score)
```

**关键约束**：`required_addressed` 必须满足。例如「面罩不适导致用不下去」（O3 为关键 Outcome）的人，单纯医院背书不应判 advance——它增加可信度，但未解决 O3。

**4.5b 识别层**：保留现有 `identify_factors`（关键词命中 factors），同时新增 `detect_interventions`（关键词→结构化 intervention），二者并存：factors 命中用于 force 层面解释，interventions 用于 outcome 层面判定。

### 4.6 `backend/services/llm_simulate.py` — LLM 仿真注入 Job 本体

**改动**：LLM 仿真时注入 persona 完整 `jtbd` + jobs/outcomes，要求输出 `{reaction, decision, activated_factors, outcome_improved, unresolved_outcomes, next_step}`。规则引擎保持为离线回退。

### 4.7 `backend/services/memory.py` — 记忆改为可校准 JTBD 事件

**改动**：`record_campaign_experience` 在写入 MemoryEntry 时，额外记录 `step_before`、`outcome_changes`、`force_changes`（来自 SimulateResult）。阶段推进逻辑从「advance 计数」升级为「current_step 是否向前迁移」。

```python
entry = MemoryEntry(
    # ...现有字段...
    step_before=persona.jtbd.current_step,
    outcome_changes=[{"outcome_id": o, "delta_satisfaction": d} for o, d in improved_deltas],
    force_changes=[{"factor_id": f, "force": force, "delta": d} for f, force, d in force_deltas],
)
```

检索时按「当前 Job + 当前 Step + 本次 campaign 相关」检索 3-5 条，注入 LLM。真实观察（销售/退货/停用/二手）`source` 标 `observed`，优先级高于 `simulation`。

### 4.8 路由 `backend/routes/`

- 新建 `routes/jobs.py`：`GET /api/jobs`、`GET /api/outcomes`、`GET /api/sub_jobs`（供前端筛选与生成器调用）。
- `routes/generate.py`：`POST /api/generate` 入参增加 `entry_situations`、`job_ids`、`steps`、`roles`（可指定要测试的起点情境，而非只输入 N）。
- `routes/simulate.py`：`POST /api/simulate` 入参增加 `interventions`（结构化干预）、`objective`（任务目标）；出参增加 `outcome_improved`、`unresolved_outcomes`、`next_step`。
- `main.py`：注册新路由。

### 4.9 前端 `frontend/`

1. **生成区新增「从什么问题开始」筛选器**：心血管风险 / 伴侣睡眠受损 / 日间功能与安全 / 照护责任 / 重症呼吸支持。
2. **Persona 详情第一屏换成「任务卡」**：起点情境 → Job 发起者 → 核心 Job → 当前 Step → 前三条 Outcome → Push/Pull/Anxiety/Alternative → 证据原话；人口学与 factor_weights 收到第二层。
3. **Campaign 结果页增加「驱动因素热力图」**：行=persona，列=Outcome/Force，显示改善/未解决。
4. **增加「真实验证回写」入口**：对模拟结果标记「已验证/未验证/方向相反」+ 输入短证据。

---

## 5. 分阶段实施计划（含验证）

| 阶段 | 交付 | 验收/验证 |
|---|---|---|
| **P0-A 数据层** | 重写 `data/factors.json`（22 维度+JTBD 字段）；新增 `jobs.json`、`outcomes.json` | 三个 JSON 可被解析；22 个 factor 均有 `job_ids`/`outcome_ids`/`force_default`；7 Job、9 Outcome、14 SubJob |
| **P0-B 模型层** | `schemas.py` 新增 JTBD 模型；`factor_store.py` 兼容新字段；新建 `job_store.py` | `Factor.model_validate` 通过；`load_jobs()` 返回 7 条 |
| **P0-C 生成层** | `prompt.py` + `fallback_gen.py` 改为「先 Job 再人设」 | 生成的心智含 `jtbd` 字段；`job_id` 在 jobs 内；`desired_outcomes` 的 id 在 outcomes 内 |
| **P1 仿真层** | `simulate.py::decide_for` 改为 Outcome/Force balance；`llm_simulate.py` 同步 | 「面罩不适」用户 + 纯医院背书 → 不判 advance；「试戴+面罩支持」→ 判 advance |
| **P1 结果层** | `SimulateResult` 增加 outcome/next_step；前端热力图 | 结果页显示改善 Outcome 与未解决阻力 |
| **P2 记忆层** | `MemoryEntry` 结构化；真实观察回写 | 多轮 campaign 后 `current_step` 向前迁移可解释 |
| **P2 治理层** | jobs/outcomes 管理 API + 后台维护 | 可增删改 Job/Outcome 并生效 |

**回归验证命令（改造后必须通过）：**

```bash
cd consumer-mind-sim/backend
python -c "from services.job_store import load_jobs, load_outcomes; print(len(load_jobs()), len(load_outcomes()))"   # 期望 7 9
python -c "from services.factor_store import load_factors; print(len([f for f in load_factors() if f.enabled]))"     # 期望 22
python -c "from schemas import Persona; import json; p=Persona.model_validate(json.loads('{...}'))"                    # 含 jtbd 字段
```

---

## 6. 验收标准（改造完成定义）

1. **Job 本体可维护**：`jobs.json` 新增/编辑 Job，生成器与仿真自动纳入，无需改代码。
2. **维度可扩展**：`factors.json` 新增维度（含 JTBD 映射），采样池/识别/UI 权重条自动纳入。
3. **先 Job 再人设**：每个心智的 `jtbd.job_id` 来自 jobs；`dominant_features`/`factor_weights` 编码来自 factors；`desired_outcomes` 的 id 来自 outcomes。
4. **决策可解释**：`decide_for` 输出「改善的 Outcome + 未解决的阻力 + 下一步」，而非仅「命中几个关键词」。
5. **关键 Outcome 门控**：未解决 persona 关键 Outcome 的 campaign 不会被误判为 advance。
6. **记忆可校准**：MemoryEntry 记录 outcome/force 变化；真实观察优先级高于仿真。

---

## 7. 真实语料资产接入（可选，但推荐）

三份真实语料文件已具备，建议接入方式：

| 文件 | 用途 | 接入位置 |
|---|---|---|
| `消费者呼吸机购买JTBD数据库.xlsx`（548 条，含主 Job/子 Job/未满足需求） | 作为 `evidence_refs` 证据库 + persona 语料来源 | `data/evidence/`（可转 JSON） |
| `呼吸机购买决策驱动因素_语料表.xlsx`（22 维度×3 语料） | factors 的 `definition`/`note` 溯源依据 | 已体现在 `factors.json` |
| `消费者心智模拟系统：JTBD 改造建议.md` | 本改造的审阅依据 | 已吸收进本文档 |

**建议**：把 548 条语料转成 `data/evidence.json`（`[{id:"SOC-001", job_id, sub_job_id, outcome_ids, quote, source}]`），生成器在输出 `evidence_refs` 时引用，仿真结果页可回显证据原话。

---

## 8. 附录：已知坑（沿用 SPEC v2）

| 坑 | 规避 |
|---|---|
| DeepSeek v4 thinking 占满 token 致 content 空 | `extra_body={"thinking":{"type":"disabled"}}` |
| LLM 返回非纯 JSON | 正则提取最外层 `[]`/`{}` + `json.loads`，失败重试 |
| 多人串行太慢 | `asyncio.gather` 并发 |
| Windows GBK 报 UnicodeEncodeError | `sys.stdout.reconfigure(encoding='utf-8')`；文件 utf-8 |
| 新增维度编码冲突 | 生成时校验 id 唯一 |

---

*文档完。一句话：**维度是证据层，Job 才是顶层业务资产；仿真以「是否推动任务进展」而非「命中几个关键词」判定。** Cursor 按第 5 章顺序施工即可。*
