"""管理者向け：QRコードのラベル（QR＋管理番号）の印刷。"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import Asset, User
from app.routers.admin_master import tag_url
from app.services.assets import get_asset
from app.services.qr import label_qr, qr_svg_file
from app.templating import templates

router = APIRouter()

SIZES_MM = [20, 25, 30, 40, 50]  # QR本体の1辺（mm）。余白は、その外側に付く
DEFAULT_SIZE_MM = 30
CUT_MODES = ("grid", "box", "none")  # 裁断用の通し線／1枚ずつ囲む／なし
PAGE_WIDTH_MM = 190  # A4（210mm）から、左右の余白10mmずつを引いた幅
MAX_LABELS = 500


def _active_assets(session: Session) -> list[Asset]:
    return list(session.scalars(select(Asset).where(Asset.is_active == True).order_by(Asset.asset_no)))  # noqa: E712


def _select_page(request, session, user, *, error=None, status=200):
    return templates.TemplateResponse(request, "admin_labels.html", {
        "user": user, "assets": _active_assets(session), "sizes": SIZES_MM, "default_size": DEFAULT_SIZE_MM,
        "error": error}, status_code=status)


@router.get("/admin/labels", response_class=HTMLResponse)
def labels_page(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _select_page(request, session, user)


@router.post("/admin/labels/print", response_class=HTMLResponse)
def labels_print(request: Request, nos: list[str] = Form(default=[]), size_mm: int = Form(DEFAULT_SIZE_MM),
                 show_name: str = Form(""), cut: str = Form("grid"), csrf_token: str = Form(""),
                 user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    if not auth.check_csrf(request, csrf_token):
        return _select_page(request, session, user, error="画面の有効期限が切れました。もう一度お試しください。", status=400)
    if size_mm not in SIZES_MM:
        return _select_page(request, session, user, error="QRの大きさの指定が正しくありません。", status=400)
    if cut not in CUT_MODES:
        return _select_page(request, session, user, error="切り取り線の指定が正しくありません。", status=400)
    if not nos:
        return _select_page(request, session, user, error="印刷する備品を選んでください。", status=400)
    if len(nos) > MAX_LABELS:
        return _select_page(request, session, user, error=f"一度に印刷できるのは{MAX_LABELS}枚までです。分けて印刷してください。", status=400)

    wanted = set(nos)
    assets = [a for a in _active_assets(session) if a.asset_no in wanted]  # 廃棄済み・存在しない番号は除く
    labels = []
    for a in assets:
        q = label_qr(tag_url(request, a.tag_token), size_mm)
        # 管理番号の文字の大きさ（mm）：長い番号でも、ラベルの幅に収まるように調整する
        font_mm = max(2.4, min(4.5, q.total_mm * 1.5 / max(len(a.asset_no), 1)))
        labels.append({"asset": a, "qr": q, "font_mm": round(font_mm, 2)})
    # ラベルの大きさ（余白1mmずつを含む）。裁断用の通し線のために、全ラベルを同じ大きさにそろえる
    cell_w = round(max((l["qr"].total_mm for l in labels), default=0) + 2, 2)
    max_font = max((l["font_mm"] for l in labels), default=3)
    cell_h = round(cell_w + max_font * 1.3 + (max_font * 0.75 * 2.5 if show_name else 0) + 0.5, 2)
    columns = max(1, int(PAGE_WIDTH_MM // cell_w))
    return templates.TemplateResponse(request, "admin_labels_print.html", {
        "labels": labels, "size_mm": size_mm, "show_name": bool(show_name), "cut": cut,
        "cell_w": cell_w, "cell_h": cell_h, "columns": columns})


@router.get("/admin/assets/{asset_no}/qr.svg")
def asset_qr(asset_no: str, request: Request, user: User = Depends(auth.require_admin),
             session: Session = Depends(get_session)):
    asset = get_asset(session, asset_no)
    if asset is None:
        return RedirectResponse("/admin/assets", status_code=303)
    return Response(qr_svg_file(tag_url(request, asset.tag_token)), media_type="image/svg+xml",
                    headers={"Content-Disposition": f"inline; filename=qr_{asset.asset_no}.svg",
                             "Cache-Control": "no-store"})
