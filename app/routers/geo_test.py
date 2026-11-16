"""位置情報テストページ。GPSの誤差を各フロアで測るための一時的なページ。

本番ではアクセス制限をかけるか、削除する（ログインなしで書き込めるため）。
"""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import GeoTest

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


class GeoPayload(BaseModel):
    label: str = Field(default="", max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    altitude: float | None = None
    error_message: str = Field(default="", max_length=200)


@router.get("/test/geo")
def geo_page(request: Request, id: str = "", session: Session = Depends(get_session)):
    rows = session.scalars(select(GeoTest).order_by(GeoTest.id.desc()).limit(30)).all()
    return templates.TemplateResponse(request, "geo_test.html", {"label": id[:100], "rows": rows})


@router.post("/test/geo")
def geo_save(payload: GeoPayload, request: Request, session: Session = Depends(get_session)):
    row = GeoTest(
        label=payload.label,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_m=payload.accuracy_m,
        altitude=payload.altitude,
        error_message=payload.error_message,
        user_agent=request.headers.get("user-agent", "")[:300],
    )
    session.add(row)
    session.commit()
    return {"id": row.id}
