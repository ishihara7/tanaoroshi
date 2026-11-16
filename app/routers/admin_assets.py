"""管理者向け：備品の管理（登録・編集・タグ用URL・廃棄）。"""
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.config import load_settings
from app.db import get_session
from app.models import Asset, User
from app.services.assets import ASSET_NO_RE, ASSET_NO_RULE, get_asset
from app.templating import templates

router = APIRouter()

CSRF_ERROR = "画面の有効期限が切れました。もう一度お試しください。"


def _page(request: Request, name: str, user: User, status: int = 200, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, **ctx}, status_code=status)


def tag_url(request: Request, token: str) -> str:
    """タグ（NFC・QR）に入れるURL。管理番号ではなく、ランダムなトークンを使う。"""
    scheme = "https" if load_settings().cookie_secure else request.url.scheme
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}/i/{token}"


def _new_token(session: Session) -> str:
    while True:
        token = secrets.token_urlsafe(9)  # 12文字
        if not session.scalar(select(Asset.asset_no).where(Asset.tag_token == token)):
            return token


def _assets_page(request, session, user, *, q="", show_all=False, error=None, status=200):
    stmt = select(Asset).order_by(Asset.asset_no)
    if not show_all:
        stmt = stmt.where(Asset.is_active == True)  # noqa: E712（SQL Server では IS 1 と書けない）
    if q:
        stmt = stmt.where((Asset.asset_no.contains(q)) | (Asset.name.contains(q)))
    return _page(request, "admin_assets.html", user, status, assets=session.scalars(stmt).all(),
                 q=q, show_all=show_all, error=error)


@router.get("/admin/assets", response_class=HTMLResponse)
def assets_page(request: Request, q: str = "", all: int = 0,
                user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _assets_page(request, session, user, q=q.strip(), show_all=bool(all))


@router.post("/admin/assets")
def asset_create(request: Request, asset_no: str = Form(""), name: str = Form(""),
                 note: str = Form(""), csrf_token: str = Form(""),
                 user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    if not auth.check_csrf(request, csrf_token):
        return _assets_page(request, session, user, error=CSRF_ERROR, status=400)
    asset_no, name, note = asset_no.strip(), name.strip(), note.strip()
    if not ASSET_NO_RE.fullmatch(asset_no):
        return _assets_page(request, session, user, error=f"管理番号は、{ASSET_NO_RULE}で入力してください。", status=400)
    if not (1 <= len(name) <= 100) or len(note) > 500:
        return _assets_page(request, session, user, error="名称は1〜100文字、備考は500文字以内にしてください。", status=400)
    if get_asset(session, asset_no):
        return _assets_page(request, session, user, error="その管理番号は、すでに登録されています（大文字・小文字は区別しません）。", status=400)
    session.add(Asset(asset_no=asset_no, name=name, note=note, tag_token=_new_token(session)))
    session.commit()
    return RedirectResponse(f"/admin/assets/{asset_no}", status_code=303)


def _asset_page(request, session, user, asset, *, error=None, saved=False, status=200):
    return _page(request, "admin_asset_edit.html", user, status, asset=asset,
                 url=tag_url(request, asset.tag_token), error=error, saved=saved)


@router.get("/admin/assets/{asset_no}", response_class=HTMLResponse)
def asset_edit_page(asset_no: str, request: Request, saved: int = 0,
                    user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    asset = get_asset(session, asset_no)
    if asset is None:
        return RedirectResponse("/admin/assets", status_code=303)
    return _asset_page(request, session, user, asset, saved=bool(saved))


@router.post("/admin/assets/{asset_no}")
def asset_update(asset_no: str, request: Request, name: str = Form(""), note: str = Form(""),
                 csrf_token: str = Form(""),
                 user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    asset = get_asset(session, asset_no)
    if asset is None:
        return RedirectResponse("/admin/assets", status_code=303)
    if not auth.check_csrf(request, csrf_token):
        return _asset_page(request, session, user, asset, error=CSRF_ERROR, status=400)
    name, note = name.strip(), note.strip()
    if not (1 <= len(name) <= 100) or len(note) > 500:
        return _asset_page(request, session, user, asset, error="名称は1〜100文字、備考は500文字以内にしてください。", status=400)
    asset.name, asset.note = name, note
    session.commit()
    return RedirectResponse(f"/admin/assets/{asset_no}?saved=1", status_code=303)


@router.post("/admin/assets/{asset_no}/reissue")
def asset_reissue(asset_no: str, request: Request, csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    """タグ（NFC・QR）のURLを作り直す。古いタグ・ラベルは無効になる（貼り替えが必要）。"""
    asset = get_asset(session, asset_no)
    if asset is None or not auth.check_csrf(request, csrf_token):
        return RedirectResponse("/admin/assets", status_code=303)
    asset.tag_token = _new_token(session)
    session.commit()
    return RedirectResponse(f"/admin/assets/{asset_no}?saved=1", status_code=303)


@router.post("/admin/assets/{asset_no}/dispose")
def asset_dispose(asset_no: str, request: Request, csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    """廃棄（台帳から非表示）／戻す。履歴は残る。"""
    asset = get_asset(session, asset_no)
    if asset is None or not auth.check_csrf(request, csrf_token):
        return RedirectResponse("/admin/assets", status_code=303)
    asset.is_active = not asset.is_active
    session.commit()
    return RedirectResponse(f"/admin/assets/{asset_no}?saved=1", status_code=303)
