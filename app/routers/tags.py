"""備品タグの着地ページ。タッチすると、その瞬間の位置を1回だけ取得して記録する。"""
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import Asset, Scan, User, utcnow
from app.templating import templates

router = APIRouter()

DEDUPE_SECONDS = 10  # 同じ人が同じ備品を続けて読み込んだときは、1件にまとめる（再読み込み対策）


EMPLOYEE_NO_RE = re.compile(r"[A-Za-z0-9]{1,20}")  # 社員番号：半角英数字、20文字まで（全角は通さない）


class ScanPayload(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    altitude: float | None = None
    error_message: str = Field(default="", max_length=200)
    employee_no: str = Field(default="", max_length=40)  # 記録した人の社員番号（氏名は扱わない）


def _find_asset(session: Session, token: str) -> Asset | None:
    asset = session.scalar(select(Asset).where(Asset.tag_token == token))
    return asset if asset and asset.is_active else None  # 廃棄済みのタグは使えない


@router.get("/i/{token}", response_class=HTMLResponse)
def tag_page(token: str, request: Request, user: User = Depends(auth.current_user),
             session: Session = Depends(get_session)):
    # 未ログインなら、ログイン後にこのURLへ戻る（current_user が処理する）
    asset = _find_asset(session, token)
    if asset is None:
        return templates.TemplateResponse(request, "tag.html", {"user": user, "asset": None, "token": token}, status_code=404)
    return templates.TemplateResponse(
        request, "tag.html", {"user": user, "asset": asset, "token": token}
    )


@router.post("/i/{token}/scan")
def tag_scan(token: str, payload: ScanPayload, request: Request, user: User = Depends(auth.current_user),
             session: Session = Depends(get_session)):
    if not auth.check_csrf(request, request.headers.get("x-csrf-token")):
        return JSONResponse({"ok": False, "message": "画面の有効期限が切れました。再読み込みしてください。"}, status_code=403)
    asset = _find_asset(session, token)
    if asset is None:
        return JSONResponse({"ok": False, "message": "このタグは無効です。"}, status_code=404)

    employee_no = payload.employee_no.strip()
    if not EMPLOYEE_NO_RE.fullmatch(employee_no):
        return JSONResponse({"ok": False, "message": "社員番号は、半角英数字（20文字まで）で入力してください。"}, status_code=400)

    now = utcnow()
    has_position = payload.latitude is not None and payload.longitude is not None
    # 共通のアカウントを使うことがあるため、同じ社員番号の連続した読み込みだけを、1件にまとめる
    recent = session.scalar(
        select(Scan).where(Scan.asset_no == asset.asset_no, Scan.employee_no == employee_no,
                           Scan.created_at > now - timedelta(seconds=DEDUPE_SECONDS))
        .order_by(Scan.id.desc())
    )
    if recent is not None:
        return {"ok": True, "deduped": True, "position": recent.latitude is not None}

    session.add(Scan(
        asset_no=asset.asset_no, user_id=user.id, employee_no=employee_no,
        latitude=payload.latitude if has_position else None,
        longitude=payload.longitude if has_position else None,
        accuracy_m=payload.accuracy_m if has_position else None,
        altitude=payload.altitude if has_position else None,
        error_message=payload.error_message,
        user_agent=request.headers.get("user-agent", "")[:300],
    ))
    # 最後に確認した時刻は、位置が取れなくても更新する。位置は、取れたときだけ更新する
    asset.last_seen_at = now
    if has_position:
        asset.current_lat, asset.current_lon = payload.latitude, payload.longitude
        asset.current_accuracy_m = payload.accuracy_m
    session.commit()
    return {"ok": True, "deduped": False, "position": has_position}
