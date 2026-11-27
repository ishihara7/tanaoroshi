"""屋内の位置の基準点（アンカー）。アプリが、アンカーを読み取って、自分の位置を合わせるために使う。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import Anchor, User
from app.templating import templates

router = APIRouter()


def _to_dict(a: Anchor) -> dict:
    return {"token": a.anchor_token, "name": a.name, "floor": a.floor, "x_m": a.x_m, "y_m": a.y_m, "z_m": a.z_m,
            "facing_deg": a.facing_deg}


@router.get("/api/anchors")
def list_anchors(user: User = Depends(auth.current_user), session: Session = Depends(get_session)):
    """有効なアンカーの一覧（アプリが、事前に取り込んでおく）。"""
    # SQL Serverでは IS 1 が使えないため、is_(True) でなく == True とする
    rows = session.scalars(select(Anchor).where(Anchor.is_active == True).order_by(Anchor.floor, Anchor.name))  # noqa: E712
    return {"anchors": [_to_dict(a) for a in rows]}


@router.get("/api/anchors/{token}")
def get_anchor(token: str, user: User = Depends(auth.current_user), session: Session = Depends(get_session)):
    a = session.get(Anchor, token)
    if a is None or not a.is_active:
        return JSONResponse({"ok": False, "message": "このアンカーは無効です。"}, status_code=404)
    return _to_dict(a)


@router.get("/a/{token}", response_class=HTMLResponse)
def anchor_page(token: str, request: Request, user: User = Depends(auth.current_user),
                session: Session = Depends(get_session)):
    """アンカーのタグ（NFC／QR）に書くURL。アプリが入っていない端末で開いたときに、案内を出す。
    備品のタグ（/i/{トークン}）と同じく、未ログインならログインへ回し、ログイン後に戻る。"""
    a = session.get(Anchor, token)
    a = a if a is not None and a.is_active else None
    return templates.TemplateResponse(request, "anchor.html", {"user": user, "anchor": a}, status_code=200 if a else 404)
