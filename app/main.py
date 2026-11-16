"""FastAPI 起動。機能は順次追加する。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import Base, get_engine
from app.routers import geo_test

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Phase 0 のみ。Phase 1 から Alembic のマイグレーションに切り替える
    Base.metadata.create_all(get_engine())
    yield


app = FastAPI(title="備品所在管理システム", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(geo_test.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
