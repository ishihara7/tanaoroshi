"""備品の検索・詳細（移動履歴）・レーダー・要確認リスト。ログインした全員が使える。"""
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.config import load_settings
from app.db import get_session
from app.models import Asset, Scan, User, utcnow
from app.services.assets import get_asset
from app.templating import jst, templates

router = APIRouter()

SEARCH_LIMIT = 100
HISTORY_LIMIT = 50


def _visible(asset: Asset | None, user: User) -> bool:
    """廃棄済みの備品は、管理者だけが見られる。"""
    return asset is not None and (asset.is_active or user.role == "admin")


@router.get("/assets", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", user: User = Depends(auth.current_user),
                session: Session = Depends(get_session)):
    q = q.strip()[:100]
    stmt = select(Asset).where(Asset.is_active == True).order_by(Asset.name, Asset.asset_no).limit(SEARCH_LIMIT)  # noqa: E712
    if q:
        stmt = stmt.where((Asset.asset_no.contains(q)) | (Asset.name.contains(q)))
    return templates.TemplateResponse(request, "assets_search.html", {
        "user": user, "q": q, "assets": session.scalars(stmt).all(), "limit": SEARCH_LIMIT})


@router.get("/assets/{asset_no}", response_class=HTMLResponse)
def detail_page(asset_no: str, request: Request, user: User = Depends(auth.current_user),
                session: Session = Depends(get_session)):
    asset = get_asset(session, asset_no)
    if not _visible(asset, user):
        return RedirectResponse("/assets", status_code=303)
    # 記録者は、社員番号だけを表示する（氏名・アカウント名は、出さない）
    history = session.scalars(
        select(Scan).where(Scan.asset_no == asset.asset_no).order_by(Scan.id.desc()).limit(HISTORY_LIMIT)
    ).all()
    return templates.TemplateResponse(request, "asset_detail.html", {"user": user, "asset": asset, "history": history})


@router.get("/assets/{asset_no}/radar", response_class=HTMLResponse)
def radar_page(asset_no: str, request: Request, user: User = Depends(auth.current_user),
               session: Session = Depends(get_session)):
    asset = get_asset(session, asset_no)
    if asset is None or not asset.is_active:
        return RedirectResponse("/assets", status_code=303)
    data = {"lat": asset.current_lat, "lon": asset.current_lon, "accuracy": asset.current_accuracy_m,
            "seen": jst(asset.last_seen_at)}
    return templates.TemplateResponse(request, "radar.html", {
        "user": user, "asset": asset,
        # </script> を含む文字列で、ページが壊れないようにする
        "radar_json": json.dumps(data).replace("<", "\\u003c")})


@router.get("/attention", response_class=HTMLResponse)
def attention_page(request: Request, user: User = Depends(auth.current_user),
                   session: Session = Depends(get_session)):
    days = load_settings().attention_days
    limit = utcnow() - timedelta(days=days)
    active = session.scalars(select(Asset).where(Asset.is_active == True).order_by(Asset.name)).all()  # noqa: E712

    stale = [a for a in active if a.last_seen_at is None or a.last_seen_at < limit]
    no_position = [a for a in active if a.current_lat is None]
    return templates.TemplateResponse(request, "attention.html", {
        "user": user, "days": days, "stale": stale, "no_position": no_position})
