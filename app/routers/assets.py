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
from app.models import Asset, Category, Floor, Scan, User, utcnow
from app.services.geo import to_map_position
from app.templating import templates

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
    cats = {c.id: c.name for c in session.scalars(select(Category))}
    return templates.TemplateResponse(request, "assets_search.html", {
        "user": user, "q": q, "assets": session.scalars(stmt).all(), "cat_names": cats, "limit": SEARCH_LIMIT})


@router.get("/assets/{asset_no}", response_class=HTMLResponse)
def detail_page(asset_no: str, request: Request, user: User = Depends(auth.current_user),
                session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_no)
    if not _visible(asset, user):
        return RedirectResponse("/assets", status_code=303)
    category = session.get(Category, asset.category_id) if asset.category_id else None
    rows = session.execute(
        select(Scan, User.display_name).join(User, User.id == Scan.user_id, isouter=True)
        .where(Scan.asset_no == asset_no).order_by(Scan.id.desc()).limit(HISTORY_LIMIT)
    ).all()
    return templates.TemplateResponse(request, "asset_detail.html", {
        "user": user, "asset": asset, "category": category,
        "history": [(s, name or "（削除済み）") for s, name in rows]})


@router.get("/assets/{asset_no}/radar", response_class=HTMLResponse)
def radar_page(asset_no: str, request: Request, user: User = Depends(auth.current_user),
               session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_no)
    if asset is None or not asset.is_active:
        return RedirectResponse("/assets", status_code=303)
    data = {"lat": asset.current_lat, "lon": asset.current_lon, "accuracy": asset.current_accuracy_m}
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

    # 建物外の可能性：位置合わせ済みのフロア図が1つ以上あり、どの図の範囲（余白つき）にも入らない位置
    aligned = [f for f in session.scalars(select(Floor)) if f.is_aligned]
    outside = []
    if aligned:
        for a in active:
            if a.current_lat is None:
                continue
            if not any((p := to_map_position(f, a.current_lat, a.current_lon)) and p.inside for f in aligned):
                outside.append(a)
    return templates.TemplateResponse(request, "attention.html", {
        "user": user, "days": days, "stale": stale, "no_position": no_position,
        "outside": outside, "has_aligned": bool(aligned)})
