# -*- coding: utf-8 -*-
"""呼吸机消费者心智模拟系统 — 一键启动器。

打包为 exe 后，请与 backend / frontend / data 放在同一目录下双击运行。
关闭本窗口即可停止服务。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((HOST, port)) == 0


def find_python() -> str | None:
    """找到能 import uvicorn 的 Python（打包成 exe 后不能用 sys.executable）。"""
    candidates: list[str] = []

    if not getattr(sys, "frozen", False):
        candidates.append(sys.executable)

    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    # Windows 常见安装路径
    local = os.environ.get("LOCALAPPDATA", "")
    for extra in (
        Path(sys.base_prefix) / "python.exe" if hasattr(sys, "base_prefix") else None,
        Path(r"C:\Python312\python.exe"),
        Path(r"C:\Python311\python.exe"),
        Path(local) / "Programs" / "Python" / "Python312" / "python.exe",
        Path(local) / "Programs" / "Python" / "Python311" / "python.exe",
    ):
        if extra and Path(extra).is_file():
            candidates.append(str(extra))

    seen: set[str] = set()
    for cand in candidates:
        key = cand.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            check = subprocess.run(
                [cand, "-c", "import uvicorn, fastapi"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if check.returncode == 0:
                return cand
        except Exception:
            continue
    return None


def wait_ready(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(PORT):
            return True
        time.sleep(0.3)
    return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    root = app_root()
    backend = root / "backend"
    if not (backend / "main.py").is_file():
        print("=" * 50)
        print("找不到 backend\\main.py")
        print(f"请把本程序放在项目根目录（与 backend 同级）")
        print(f"当前目录: {root}")
        print("=" * 50)
        input("\n按回车退出...")
        return 1

    print("=" * 50)
    print("  呼吸机消费者心智模拟系统")
    print("  关闭本窗口 = 停止服务")
    print("=" * 50)
    print(f"项目目录: {root}")

    legacy_env = root.parent / "consumer_ai_sim" / ".env"
    local_env = root / ".env"
    if legacy_env.is_file():
        print(f"✓ 将使用配置: {legacy_env}")
    elif local_env.is_file():
        print(f"✓ 将使用配置: {local_env}")
    else:
        print("⚠ 未找到 .env（规则模式仍可用；LLM 需配置 DEEPSEEK_API_KEY）")

    if port_open(PORT):
        print(f"\n端口 {PORT} 已被占用，直接打开浏览器…")
        webbrowser.open(URL)
        print(f"地址: {URL}")
        print("（不会关闭已有服务；按回车仅退出本窗口）")
        input()
        return 0

    python = find_python()
    if not python:
        print("\n未找到已安装 uvicorn / fastapi 的 Python。")
        print("请先在本机执行: pip install uvicorn fastapi")
        input("\n按回车退出...")
        return 1

    print(f"Python: {python}")
    print(f"\n正在启动服务 → {URL}\n")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    proc = subprocess.Popen(
        [
            python,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=str(backend),
        creationflags=creationflags,
    )

    try:
        if wait_ready():
            print(f"✓ 启动成功，正在打开浏览器…\n")
            webbrowser.open(URL)
        else:
            print("⚠ 等待服务就绪超时，请稍后手动打开浏览器。")
            webbrowser.open(URL)

        print(f"工作台: {URL}")
        print(f"维度后台: {URL}/admin")
        print(f"Jobs 页: {URL}/jobs")
        print("\n按 Ctrl+C 或直接关闭窗口可停止服务。\n")
        proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("已退出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
