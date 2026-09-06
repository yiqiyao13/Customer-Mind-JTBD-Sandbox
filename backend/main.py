from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import load_env
from routes import factors, generate, jobs, simulate
from services.persona_store import load_persisted_personas

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="呼吸机消费者心智模拟系统", version="3.0-jtbd")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(factors.router)
app.include_router(generate.router)
app.include_router(simulate.router)
app.include_router(jobs.router)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.on_event("startup")
def startup():
    env_path = load_env()
    load_persisted_personas()
    if env_path:
        print(f"✓ 已加载 DeepSeek 配置: {env_path}")


def _html(path: Path):
    if path.exists():
        return FileResponse(
            path,
            headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
        )
    return None


@app.get("/")
def index():
    page = _html(FRONTEND_DIR / "index.html")
    return page or {"message": "API running. Place frontend/index.html to enable UI."}


@app.get("/admin")
def admin_page():
    page = _html(FRONTEND_DIR / "admin.html")
    return page or {"message": "Admin page not found."}


@app.get("/jobs")
def jobs_page():
    page = _html(FRONTEND_DIR / "jobs.html")
    return page or {"message": "Jobs page not found."}


@app.get("/api/health")
def health():
    return {"status": "ok"}
