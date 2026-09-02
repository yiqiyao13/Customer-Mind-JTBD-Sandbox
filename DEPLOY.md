# 部署指南 · 腾讯云 Lighthouse

> 目标：把 `consumer-mind-sim` 部署到 `http://118.25.50.63/`，**5 步跑通**。

---

## 0. 前置条件（一次性）

- [x] 服务器已开：Docker CE 27.5.1（系统镜像预装）
- [x] 防火墙已放行：22（SSH）、80（HTTP）、443（HTTPS）
- [ ] **重置 ubuntu 密码**（控制台右上角「重置密码」按钮，建议改成纯字母数字，别带 `[` `]` `(` `)` `)` `.` 这种特殊字符）

> 改完密码后，把新密码告诉我（或贴到对话里）。我帮你 SSH 上去把代码推上去、构建、启动。

---

## 1. 服务器初始化（首次部署才需要）

SSH 登录后，依次执行：

```bash
# 安装 docker compose 插件（镜像已预装 Docker，本镜像缺 compose 插件）
sudo apt update
sudo apt install -y docker-compose-plugin

# 验证
docker compose version
# 应输出 Docker Compose version v2.x.x
```

---

## 2. 推送代码

我（助手）会通过 `scp` 把项目根目录（不含大文件）推上去。或者你也可以用 git。

```bash
# 在本地项目根目录打包（排除大文件）
cd C:\Users\yiqiy\Downloads\consumer_ai_sim\consumer-mind-sim
# 我用 scp 推送
```

服务器端落点：`/home/ubuntu/mindsim/`

---

## 3. 填 DeepSeek Key（可选）

LLM 仿真需要。不填也能跑，只是用本地 fallback 生成（也够用）。

```bash
cd /home/ubuntu/mindsim
cp .env.example .env
nano .env   # 把 DEEPSEEK_API_KEY 改成你的真 key
```

`.env` 不会被 commit，存于宿主机并挂载到容器 `/app/.env`。

---

## 4. 构建 + 启动

```bash
cd /home/ubuntu/mindsim
chmod +x deploy.sh
bash deploy.sh
```

执行流程：
1. （可选）`git pull`
2. `docker compose down`
3. `docker compose up -d --build`
4. 等待 + 10 次健康检查
5. 成功 → 打印 `http://118.25.50.63/`

---

## 5. 验证

打开浏览器访问 **http://118.25.50.63/**

- ✅ 看到「消费者心智模拟 · MindSim」工作台 = 跑通
- ✅ 点「生成消费者心智」按钮，10 秒内出 10 个消费者 = 全栈通

---

## 常用命令

```bash
# 看实时日志
docker compose logs -f

# 重启
docker compose restart

# 停止
docker compose down

# 重新构建（代码改了之后）
docker compose up -d --build

# 进入容器调试
docker compose exec mindsim bash

# 备份数据（personas/factors/jobs）
cp -r /home/ubuntu/mindsim/data ~/mindsim_data_$(date +%Y%m%d).bak
```

---

## 故障排查

| 现象 | 排查 |
|---|---|
| 访问 `http://118.25.50.63/` 打不开 | `docker compose ps` 看容器是否 running；`docker compose logs` 看启动报错 |
| 502 / 500 | 日志里看 Python 报错；`curl http://localhost/api/health` 测本机 |
| 数据不持久 | 检查 `./data` 是否在宿主机存在；`docker compose exec mindsim ls /app/data` |
| LLM 不工作 | `.env` 里 DEEPSEEK_API_KEY 是不是填了；容器里 `docker compose exec mindsim cat /app/.env` |

---

## 后续增强（按需）

- 🔐 加认证（邀请码 + 用户名密码）→ 我会给你出 `auth.py` + 登录页
- 🌐 加域名 + HTTPS → Nginx + Let's Encrypt
- 📊 加监控 → Prometheus + Grafana
- 🔄 持续部署 → GitHub Actions / GitLab CI

本次目标：先把 `http://118.25.50.63/` 跑起来。
