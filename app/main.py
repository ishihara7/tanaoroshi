"""FastAPI 起動。機能は順次追加する。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import RedirectRequired
from app.config import load_settings
from app.db import Base, get_engine
from app.routers import account, admin, admin_csv, admin_master, assets, geo_test, tags
from app.services.seed import seed_categories

BASE_DIR = Path(__file__).resolve().parent
settings = load_settings()

if not settings.secret_key:
    # 秘密鍵なしではセッションの署名が意味をなさないため、起動させない
    raise RuntimeError("SECRET_KEY が設定されていません。.env またはアプリ設定に長いランダム文字列を設定してください。")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Phase 1 の途中までは create_all。スキーマが固まったら Alembic のマイグレーションに切り替える
    Base.metadata.create_all(get_engine())
    with Session(get_engine()) as s:
        seed_categories(s)
    yield


app = FastAPI(title="備品所在管理システム", lifespan=lifespan)

# ログイン状態は署名付きCookie（HttpOnly）。有効期間は既定30日、本番は Secure 属性あり
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_days * 24 * 3600,
    same_site="lax",
    https_only=settings.cookie_secure,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(account.router)
app.include_router(admin.router)
app.include_router(admin_master.router)
app.include_router(tags.router)
app.include_router(assets.router)
app.include_router(admin_csv.router)
app.include_router(geo_test.router)


@app.exception_handler(RedirectRequired)
async def redirect_handler(_: Request, exc: RedirectRequired):
    return RedirectResponse(exc.url, status_code=303)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
