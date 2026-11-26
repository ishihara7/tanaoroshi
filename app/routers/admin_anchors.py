"""管理者向け：アンカー（位置合わせの基準点）の登録・編集、QRのダウンロード。

QRを読むと /a/{token} が開く（案内ページは routers/anchors.py）。アプリ向けの取得APIも、そちらにある。
"""
import math
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.config import load_settings
from app.db import get_session
from app.models import Anchor, User
from app.services.qr import qr_svg_file
from app.templating import templates

router = APIRouter()

CSRF_ERROR = "画面の有効期限が切れました。もう一度お試しください。"
MAX_COORD_M = 10000  # フロア図の位置の上限（m）
FLOOR_RULE = "階は、-9〜99の整数（0を除く。地下は負の数）にしてください。"


def anchor_url(request: Request, token: str) -> str:
    """アンカーのQRに入れるURL。アプリは、/a/ で始まるURLを、アンカーとして扱う。"""
    scheme = "https" if load_settings().cookie_secure else request.url.scheme
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}/a/{token}"


def _new_token(session: Session) -> str:
    while True:
        token = "A" + secrets.token_hex(5)  # 11文字（CLIの add-anchor と同じ形式）
        if session.get(Anchor, token) is None:
            return token


def _parse(name: str, floor: str, x: str, y: str, facing: str):
    """入力を検証する。誤りがあれば、(None, メッセージ)。向きは、空なら未設定（NULL）。"""
    name = name.strip()
    if not 1 <= len(name) <= 100:
        return None, "名前は1〜100文字にしてください。"
    try:
        f = int(floor)
        xs, ys = float(x or 0), float(y or 0)
        fd = float(facing) if facing.strip() else None
    except ValueError:
        return None, "階は整数、位置と向きは数値で入力してください。"
    if not -9 <= f <= 99 or f == 0:
        return None, FLOOR_RULE
    if not all(math.isfinite(v) for v in (xs, ys)) or abs(xs) > MAX_COORD_M or abs(ys) > MAX_COORD_M:
        return None, f"位置は、±{MAX_COORD_M}m以内の数値にしてください。"
    if fd is not None and not math.isfinite(fd):
        return None, "向きは、数値で入力してください。"
    return {"name": name, "floor": f, "x_m": xs, "y_m": ys, "facing_deg": None if fd is None else fd % 360}, None


def _list_page(request, session, user, *, error=None, status=200):
    anchors = session.scalars(select(Anchor).order_by(Anchor.floor, Anchor.name)).all()
    return templates.TemplateResponse(request, "admin_anchors.html", {"user": user, "anchors": anchors, "error": error},
                                      status_code=status)


def _edit_page(request, user, anchor, *, error=None, saved=False, status=200):
    return templates.TemplateResponse(request, "admin_anchor_edit.html", {
        "user": user, "anchor": anchor, "url": anchor_url(request, anchor.anchor_token), "error": error, "saved": saved},
        status_code=status)


@router.get("/admin/anchors", response_class=HTMLResponse)
def anchors_page(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _list_page(request, session, user)


@router.post("/admin/anchors")
def anchor_create(request: Request, name: str = Form(""), floor: str = Form("1"), x: str = Form("0"), y: str = Form("0"),
                  facing_deg: str = Form(""), csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    if not auth.check_csrf(request, csrf_token):
        return _list_page(request, session, user, error=CSRF_ERROR, status=400)
    data, err = _parse(name, floor, x, y, facing_deg)
    if err:
        return _list_page(request, session, user, error=err, status=400)
    a = Anchor(anchor_token=_new_token(session), **data)
    session.add(a)
    session.commit()
    return RedirectResponse(f"/admin/anchors/{a.anchor_token}", status_code=303)


@router.get("/admin/anchors/{token}", response_class=HTMLResponse)
def anchor_edit_page(token: str, request: Request, saved: int = 0, user: User = Depends(auth.require_admin),
                     session: Session = Depends(get_session)):
    a = session.get(Anchor, token)
    if a is None:
        return RedirectResponse("/admin/anchors", status_code=303)
    return _edit_page(request, user, a, saved=bool(saved))


@router.post("/admin/anchors/{token}")
def anchor_update(token: str, request: Request, name: str = Form(""), floor: str = Form("1"), x: str = Form("0"),
                  y: str = Form("0"), facing_deg: str = Form(""), csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    a = session.get(Anchor, token)
    if a is None:
        return RedirectResponse("/admin/anchors", status_code=303)
    if not auth.check_csrf(request, csrf_token):
        return _edit_page(request, user, a, error=CSRF_ERROR, status=400)
    data, err = _parse(name, floor, x, y, facing_deg)
    if err:
        return _edit_page(request, user, a, error=err, status=400)
    for k, v in data.items():
        setattr(a, k, v)
    session.commit()
    return RedirectResponse(f"/admin/anchors/{a.anchor_token}?saved=1", status_code=303)


@router.post("/admin/anchors/{token}/toggle")
def anchor_toggle(token: str, request: Request, csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    """使わなくする／使えるように戻す（QRは変わらない）。"""
    a = session.get(Anchor, token)
    if a is None or not auth.check_csrf(request, csrf_token):
        return RedirectResponse("/admin/anchors", status_code=303)
    a.is_active = not a.is_active
    session.commit()
    return RedirectResponse(f"/admin/anchors/{a.anchor_token}?saved=1", status_code=303)


@router.get("/admin/anchors/{token}/qr.svg")
def anchor_qr(token: str, request: Request, download: int = 0, user: User = Depends(auth.require_admin),
              session: Session = Depends(get_session)):
    a = session.get(Anchor, token)
    if a is None:
        return RedirectResponse("/admin/anchors", status_code=303)
    disposition = "attachment" if download else "inline"
    return Response(qr_svg_file(anchor_url(request, a.anchor_token)), media_type="image/svg+xml",
                    headers={"Content-Disposition": f"{disposition}; filename=anchor_{a.anchor_token}.svg", "Cache-Control": "no-store"})
