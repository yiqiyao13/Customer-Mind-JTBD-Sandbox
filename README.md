# 呼吸机消费者心智模拟系统

按 **JTBD 改造开发文档 v3**（`SPEC.md`）实现的 Web 系统：

> **Job 本体驱动**（7 主 Job + 14 子 Job + 9 Outcome）+ **22 决策维度证据层** + 自设 N 生成心智 + Campaign 仿真（以「是否推动任务进展」判定）。

---



## 环境要求



- **Python** 3.10+

- **浏览器**：Chrome / Edge / Firefox 等现代浏览器

- **DeepSeek API Key**（可选）：不配置也能用规则模式；配置后可使用 LLM 生成心智与独立思考推演



---



## 环境配置



### 方式一：复用现有脚本配置（推荐）



若你已在旧项目 `consumer_ai_sim/` 中配置过 DeepSeek，**无需再配一份**。本系统启动时会自动读取：



```

consumer_ai_sim/.env

```



典型内容示例：



```env

DEEPSEEK_API_KEY=sk-xxxxxxxx

DEEPSEEK_MODEL=deepseek/deepseek-v4-flash

DEEPSEEK_BASE_URL=https://api.deepseek.com

```



启动成功后，终端会显示类似：



```

✓ 将使用现有配置: ...\consumer_ai_sim\.env

✓ 已加载 DeepSeek 配置: ...\consumer_ai_sim\.env

```



### 方式二：为本项目单独配置



在 `consumer-mind-sim/` 下复制模板：



```powershell

cd consumer-mind-sim

copy .env.example .env

```



编辑 `.env` 填入 Key。若两个 `.env` 都存在，**优先使用** `consumer-mind-sim/.env`，再合并 `consumer_ai_sim/.env` 中未设置的项。



### 环境变量说明



| 变量 | 必填 | 默认值 | 说明 |

|------|:----:|--------|------|

| `DEEPSEEK_API_KEY` | 否* | — | DeepSeek API 密钥；不填则走规则回退 |

| `DEEPSEEK_MODEL` | 否 | `deepseek-v4-flash` | 模型名，支持 `deepseek/deepseek-v4-flash` 写法 |

| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | API 地址 |



\* 不填 Key 时：生成心智、Campaign 测试仍可用，但需取消勾选「LLM 生成 / 独立思考」。



---



## 如何打开（启动服务）



### 方法一：一键启动（Windows 推荐）



```powershell

cd c:\Users\yiqiy\Downloads\consumer_ai_sim\consumer-mind-sim

.\start.ps1

```



### 方法二：手动启动



**首次运行**（安装依赖）：



```powershell

cd consumer-mind-sim\backend

pip install -r requirements.txt

```



**每次启动**：



```powershell

cd consumer-mind-sim\backend

uvicorn main:app --reload --port 8000

```



看到 `Uvicorn running on http://127.0.0.1:8000` 即表示成功。



### 停止服务



在运行服务的终端按 **`Ctrl + C`**。



---



## 打开界面



服务启动后，用浏览器访问：



| 页面 | 地址 | 用途 |

|------|------|------|

| **工作台（首页）** | http://127.0.0.1:8000 | 生成消费者、Campaign 测试、查看画像与结果 |

| **维度后台** | http://127.0.0.1:8000/admin | 管理决策维度（新增 / 启停 / 权重） |



首页右上角 **「⚙ 维度后台」** 可跳转至后台；后台可 **「← 返回工作台」**。



若样式未更新，使用 **Ctrl + F5** 强制刷新缓存。



---



## 使用流程



```

① 启动服务 → ② 浏览器打开工作台 → ③ 生成心智 → ④ 测试 Campaign

```



1. **生成消费者**：首页顶部输入数量 N → 点「生成消费者心智」（可选勾选 LLM 生成）

2. **Campaign 测试**：粘贴营销话术 → 选择模式 → 点「运行测试」

   - **独立思考（LLM）**：个性化反馈 + 内心推理（需 API Key）

   - **消费者有记忆**：每次测试写入经历，下次会参考过往（模拟多次触达）

3. **查看画像**：左侧列表选人 → 右侧看详情与经历时间线

4. **管理维度**：进入 `/admin` 新增或启停维度

### 记忆管理（生成栏下方）

| 按钮 | 作用 |
|------|------|
| **下载记忆** | 导出 JSON（经历 + 阶段快照），如 `mindsim_memories_20260824_200000.json` |
| **上传记忆** | 从 JSON 恢复（覆盖当前）；需已有对应 ID 的消费者 |
| **清除全部记忆** | 清空时间线，阶段恢复「察觉」 |
| **清除记忆**（详情页） | 仅清除当前选中消费者 |

> 重新「生成消费者心智」也会自动清空旧记忆。

---



## 目录结构



```

consumer-mind-sim/

├── SPEC.md                 # 开发文档

├── start.ps1               # Windows 一键启动

├── .env.example            # 环境变量模板（可选）

├── data/

│   ├── factors.json        # 17 维度数据库（可增补）

│   ├── personas.json       # 最近一次生成的心智

│   └── evolution.json      # 消费者记忆与阶段（有记忆模式）

├── backend/

│   ├── main.py             # FastAPI 入口

│   ├── config.py           # 环境变量加载（复用 consumer_ai_sim/.env）

│   ├── routes/             # factors / generate / simulate

│   └── services/           # LLM、规则回退、记忆、推演

└── frontend/

    ├── index.html          # 工作台首页

    ├── admin.html          # 维度后台

    ├── css/app.css         # ResMed 风格样式

    └── js/app.js           # 公共逻辑

```



---



## API



| 方法 | 路径 | 说明 |

|------|------|------|

| GET | `/api/factors` | 维度库全量 |

| POST | `/api/factors` | 新增维度 |

| PUT | `/api/factors/{id}` | 编辑/启停 |

| DELETE | `/api/factors/{id}` | 禁用维度 |

| POST | `/api/generate` | `{count, use_llm?}` 生成 N 个心智 |

| GET | `/api/personas` | 当前心智列表 |

| GET | `/api/personas/{id}/memories` | 某人的经历时间线 |

| GET | `/api/memories/export` | 下载记忆包 JSON |

| POST | `/api/memories/import` | 上传记忆包（表单 `file`） |

| POST | `/api/memories/reset` | 清除全部记忆 |

| POST | `/api/personas/{id}/memories/reset` | 清除单人记忆 |

| POST | `/api/simulate` | `{campaign, use_llm?, use_memory?}` Campaign 推演 |



---



## 与旧版 `consumer_ai_sim` 的关系



| 项目 | 用途 |

|------|------|

| `consumer_ai_sim/` | 批量 PI 仿真、Excel 账本（命令行） |

| `consumer-mind-sim/` | 维度驱动心智 + Campaign Web 测试 |



两套并行；**DeepSeek 配置共用** `consumer_ai_sim/.env`，无需重复填写。



---



## 常见问题



**Q：没有 API Key 能用吗？**  

能。取消勾选「LLM 生成」「独立思考」，使用规则模式，功能完整。



**Q：端口 8000 被占用怎么办？**  

改用其他端口，例如：`uvicorn main:app --reload --port 8080`，浏览器访问 `http://127.0.0.1:8080`。



**Q：记忆存在哪里？**  

`data/evolution.json`；「下载记忆」另存为 `mindsim_memories_*.json` 备份。

**Q：如何把记忆换到另一台电脑？**  

原机器点「下载记忆」→ 新机器生成消费者后点「上传记忆」（按 persona ID 匹配恢复）。

**Q：如何确认 Key 已生效？**  

启动时终端出现 `✓ 已加载 DeepSeek 配置`；勾选 LLM 相关选项后生成/测试不应报 Key 错误。



---



## 验收对照（SPEC §10）



1. 往 `data/factors.json` 加维度 → 生成/识别/筛选自动纳入

2. 网页输入任意 N → 生成对应数量心智

3. `dominant_features` / `factor_weights` 编码均来自维度库

4. 详情页展示人口学、OSA、心智模型、主导维度

5. Campaign → 逐人差异化反馈 + advance/hesitate/na 标签

6. UI 可新增/启停维度并即时生效


