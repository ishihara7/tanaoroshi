"""管理者向け：棚卸アプリの端末の登録（設定用のQRの発行）と、端末の一覧・無効化。

QRに入れるのは、パスワードではなく、短時間・1回だけ使える設定コード。アプリが読み取ると、端末専用のトークンを受け取る。
"""
import base64

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.config import load_settings
from app.db import get_session
from app.models import DeviceToken, User
from app.services import devices
from app.services.qr import qr_svg_file
from app.templating import templates

router = APIRouter()

CSRF_ERROR = "画面の有効期限が切れました。もう一度お試しください。"


def setup_url(request: Request, code: str) -> str:
    """設定用QRに入れるURL。アプリは、このURLから、サーバーのアドレスと設定コードを読み取る。"""
    scheme = "https" if load_settings().cookie_secure else request.url.scheme
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}/setup/{code}"


def _page(request, session, user, *, error=None, status=200):
    users = session.scalars(select(User).where(User.is_active == True).order_by(User.login_id)).all()  # noqa: E712
    names = {u.id: u.login_id for u in session.scalars(select(User))}
    devs = session.scalars(select(DeviceToken).order_by(DeviceToken.id.desc())).all()
    return templates.TemplateResponse(request, "admin_devices.html", {
        "user": user, "users": users, "devices": devs, "names": names, "minutes": devices.CODE_MINUTES, "error": error},
        status_code=status)


@router.get("/admin/devices", response_class=HTMLResponse)
def devices_page(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _page(request, session, user)


@router.post("/admin/devices/enroll", response_class=HTMLResponse)
def device_enroll(request: Request, user_id: int = Form(0), label: str = Form(""), csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    """設定用のQRを発行する。このページを閉じると、QRは二度と表示できない（コードは保存していない）。"""
    if not auth.check_csrf(request, csrf_token):
        return _page(request, session, user, error=CSRF_ERROR, status=400)
    target = session.get(User, user_id)
    if target is None or not target.is_active:
        return _page(request, session, user, error="ユーザーを選んでください。", status=400)
    code = devices.issue_code(session, target.id, label)
    svg = qr_svg_file(setup_url(request, code))
    resp = templates.TemplateResponse(request, "admin_device_qr.html", {
        "user": user, "target": target, "label": label.strip(), "minutes": devices.CODE_MINUTES,
        "qr": "data:image/svg+xml;base64," + base64.b64encode(svg).decode()})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/admin/devices/{device_id}/revoke")
def device_revoke(device_id: int, request: Request, csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    """端末を無効にする（紛失したとき）。その端末は、すぐに使えなくなる。"""
    if auth.check_csrf(request, csrf_token):
        devices.revoke(session, device_id)
    return RedirectResponse("/admin/devices", status_code=303)


@router.get("/setup/{code}", response_class=HTMLResponse)
def setup_landing(code: str, request: Request):
    """設定用QRを、カメラなどで読んだときの画面。設定は、棚卸アプリで読み取って行う（ここでは、コードを使わない）。"""
    return templates.TemplateResponse(request, "setup.html", {"user": None})
