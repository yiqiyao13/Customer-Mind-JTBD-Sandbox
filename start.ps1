# 启动呼吸机消费者心智模拟 Web 系统
# 自动复用上级目录 consumer_ai_sim/.env 中的 DeepSeek 配置，无需单独配 key
Set-Location $PSScriptRoot\backend
$legacyEnv = Join-Path $PSScriptRoot "..\consumer_ai_sim\.env"
if (Test-Path $legacyEnv) {
    Write-Host "✓ 将使用现有配置: $legacyEnv"
} elseif (Test-Path "..\.env") {
    Write-Host "✓ 将使用: ..\.env"
} else {
    Write-Host "⚠ 未找到 .env，请配置 consumer_ai_sim\.env 中的 DEEPSEEK_API_KEY"
}
uvicorn main:app --reload --port 8000
