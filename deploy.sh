#!/usr/bin/env bash
# 在腾讯云服务器上执行：bash deploy.sh
# 作用：拉代码（可选）→ 重新构建 → 启动 → 健康检查
set -e

APP_DIR="/home/ubuntu/mindsim"
cd "$APP_DIR"

echo "==> [1/4] 拉取最新代码（若已配 git；否则跳过）"
if [ -d ".git" ]; then
  git pull --rebase || { echo "git pull 失败，继续构建"; }
else
  echo "    （非 git 仓库，跳过）"
fi

echo "==> [2/4] 停掉旧容器"
docker compose down || true

echo "==> [3/4] 重新构建并启动"
docker compose up -d --build

echo "==> [4/4] 等待启动并健康检查"
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
    echo ""
    echo "✅ 部署成功！"
    echo "   健康检查: $(curl -s http://localhost/api/health)"
    echo "   访问地址: http://118.25.50.63/"
    echo "   查看日志: docker compose logs -f"
    exit 0
  fi
  echo "    等待中... ($i/10)"
done

echo ""
echo "❌ 健康检查失败，查看日志："
docker compose logs --tail=80
exit 1
