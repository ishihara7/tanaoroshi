"""管理者向け：備品の種別、フロア図、備品の管理。"""
import io
import re
import secrets
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, storage
from app.config import load_settings
from app.db import get_session
from app.models import Asset, Category, Floor, User
from app.services.assets import ASSET_NO_RE, ASSET_NO_RULE, get_asset
from app.templating import templates

router = APIRouter()

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 8000
CSRF_ERROR = "画面の有効期限が切れました。もう一度お試しください。"


def _page(request: Request, name: str, user: User, status: int = 200, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, **ctx}, status_code=status)


def tag_url(request: Request, token: str) -> str:
    """タグに書き込むURL（管理番号ではなく、ランダムなトークンを使う）。"""
    scheme = "https" if load_settings().cookie_secure else request.url.scheme
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}/i/{token}"


# =============== 備品の種別 ===============
def _categories_page(request, session, user, *, error=None, status=200):
    cats = session.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()
    return _page(request, "admin_categories.html", user, status, categories=cats, error=error)


@router.get("/admin/categories", response_class=HTMLResponse)
def categories_page(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _categories_page(request, session, user)


@router.post("/admin/categories")
def category_add(request: Request, name: str = Form(""), csrf_token: str = Form(""),
                 user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    name = name.strip()
    if not auth.check_csrf(request, csrf_token):
        return _categories_page(request, session, user, error=CSRF_ERROR, status=400)
    if not (1 <= len(name) <= 50):
        return _categories_page(request, session, user, error="種別名は1〜50文字で入力してください。", status=400)
    if session.scalar(select(Category.id).where(Category.name == name)):
        return _categories_page(request, session, user, error="その種別は、すでにあります。", status=400)
    last = session.scalar(select(Category.sort_order).order_by(Category.sort_order.desc())) or 0
    session.add(Category(name=name, sort_order=last + 1))
    session.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/admin/categories/{cat_id}/toggle")
def category_toggle(cat_id: int, request: Request, csrf_token: str = Form(""),
                    user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    cat = session.get(Category, cat_id)
    if not auth.check_csrf(request, csrf_token) or cat is None:
        return _categories_page(request, session, user, error=CSRF_ERROR, status=400)
    cat.is_active = not cat.is_active
    session.commit()
    return RedirectResponse("/admin/categories", status_code=303)


# =============== フロア図 ===============
def _read_image(upload: UploadFile) -> tuple[bytes, str, int, int]:
    """アップロードされた画像を検証して (中身, 拡張子, 幅, 高さ) を返す。問題があれば ValueError。"""
    data = upload.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise ValueError("画像ファイルを選んでください。")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("画像は10MB以下にしてください。")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        fmt, (w, h) = img.format, img.size
    except (UnidentifiedImageError, OSError):
        raise ValueError("画像として読み込めませんでした。PNG か JPEG を選んでください。")
    if fmt not in ("PNG", "JPEG"):
        raise ValueError("PNG か JPEG の画像を選んでください。")
    if max(w, h) > MAX_IMAGE_PIXELS:
        raise ValueError(f"画像が大きすぎます（長辺{MAX_IMAGE_PIXELS}px以下）。")
    return data, ".png" if fmt == "PNG" else ".jpg", w, h


def _parse_alignment(tl_lat, tl_lon, br_lat, br_lon):
    """4つとも空なら未登録（None）、4つとも入っていれば検証して返す。"""
    raw = [v.strip() for v in (tl_lat, tl_lon, br_lat, br_lon)]
    if not any(raw):
        return None
    try:
        a, b, c, d = (float(v) for v in raw)
    except ValueError:
        raise ValueError("位置合わせの緯度・経度は、4つとも数値で入力してください。")
    if not (-90 <= a <= 90 and -90 <= c <= 90 and -180 <= b <= 180 and -180 <= d <= 180):
        raise ValueError("緯度は-90〜90、経度は-180〜180の範囲で入力してください。")
    if not (a > c and b < d):
        raise ValueError("左上は右下より北（緯度が大きい）かつ西（経度が小さい）にしてください。")
    return a, b, c, d


def _floors_page(request, session, user, *, error=None, status=200):
    floors = session.scalars(select(Floor).order_by(Floor.building, Floor.sort_order, Floor.id)).all()
    return _page(request, "admin_floors.html", user, status, floors=floors, error=error)


@router.get("/admin/floors", response_class=HTMLResponse)
def floors_page(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _floors_page(request, session, user)


@router.post("/admin/floors")
def floor_create(request: Request, building: str = Form(""), floor_label: str = Form(""),
                 sort_order: int = Form(0), image: UploadFile = File(...), csrf_token: str = Form(""),
                 user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    if not auth.check_csrf(request, csrf_token):
        return _floors_page(request, session, user, error=CSRF_ERROR, status=400)
    building, floor_label = building.strip(), floor_label.strip()
    if not (1 <= len(building) <= 50 and 1 <= len(floor_label) <= 20):
        return _floors_page(request, session, user, error="建物名（50文字以内）と階（20文字以内）を入力してください。", status=400)
    try:
        data, ext, w, h = _read_image(image)
    except ValueError as e:
        return _floors_page(request, session, user, error=str(e), status=400)
    name = f"floors/{uuid.uuid4().hex}{ext}"
    storage.save(name, data)
    floor = Floor(building=building, floor_label=floor_label, sort_order=sort_order,
                  image_path=name, image_width=w, image_height=h)
    session.add(floor)
    session.commit()
    return RedirectResponse(f"/admin/floors/{floor.id}", status_code=303)


def _floor_page(request, session, user, floor, *, error=None, saved=False, status=200):
    return _page(request, "admin_floor_edit.html", user, status, floor=floor, error=error, saved=saved)


@router.get("/admin/floors/{floor_id}", response_class=HTMLResponse)
def floor_edit_page(floor_id: int, request: Request, saved: int = 0,
                    user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    floor = session.get(Floor, floor_id)
    if floor is None:
        return RedirectResponse("/admin/floors", status_code=303)
    return _floor_page(request, session, user, floor, saved=bool(saved))


@router.post("/admin/floors/{floor_id}")
def floor_update(floor_id: int, request: Request, building: str = Form(""), floor_label: str = Form(""),
                 sort_order: int = Form(0), tl_lat: str = Form(""), tl_lon: str = Form(""),
                 br_lat: str = Form(""), br_lon: str = Form(""), image: UploadFile | None = File(None),
                 csrf_token: str = Form(""),
                 user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    floor = session.get(Floor, floor_id)
    if floor is None:
        return RedirectResponse("/admin/floors", status_code=303)
    if not auth.check_csrf(request, csrf_token):
        return _floor_page(request, session, user, floor, error=CSRF_ERROR, status=400)
    building, floor_label = building.strip(), floor_label.strip()
    if not (1 <= len(building) <= 50 and 1 <= len(floor_label) <= 20):
        return _floor_page(request, session, user, floor, error="建物名（50文字以内）と階（20文字以内）を入力してください。", status=400)
    try:
        alignment = _parse_alignment(tl_lat, tl_lon, br_lat, br_lon)
        new_image = _read_image(image) if image is not None and image.filename else None
    except ValueError as e:
        return _floor_page(request, session, user, floor, error=str(e), status=400)

    floor.building, floor.floor_label, floor.sort_order = building, floor_label, sort_order
    floor.tl_lat, floor.tl_lon, floor.br_lat, floor.br_lon = alignment if alignment else (None,) * 4
    if new_image:
        data, ext, w, h = new_image
        name = f"floors/{uuid.uuid4().hex}{ext}"
        storage.save(name, data)
        floor.image_path, floor.image_width, floor.image_height = name, w, h
    session.commit()
    return RedirectResponse(f"/admin/floors/{floor.id}?saved=1", status_code=303)


@router.get("/floors/{floor_id}/image")
def floor_image(floor_id: int, user: User = Depends(auth.current_user), session: Session = Depends(get_session)):
    """フロア図の画像（ログインしている人だけ。ストレージは非公開で、アプリ経由で配信）。"""
    floor = session.get(Floor, floor_id)
    data = storage.load(floor.image_path) if floor and floor.image_path else None
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type=storage.media_type_of(floor.image_path),
                    headers={"Cache-Control": "private, max-age=300"})


# =============== 備品 ===============
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
    cats = session.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()
    return _page(request, "admin_assets.html", user, status, assets=session.scalars(stmt).all(),
                 categories=cats, cat_names={c.id: c.name for c in cats}, q=q, show_all=show_all, error=error)


@router.get("/admin/assets", response_class=HTMLResponse)
def assets_page(request: Request, q: str = "", all: int = 0,
                user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _assets_page(request, session, user, q=q.strip(), show_all=bool(all))


@router.post("/admin/assets")
def asset_create(request: Request, asset_no: str = Form(""), name: str = Form(""),
                 category_id: str = Form(""), note: str = Form(""), csrf_token: str = Form(""),
                 user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    if not auth.check_csrf(request, csrf_token):
        return _assets_page(request, session, user, error=CSRF_ERROR, status=400)
    asset_no, name, note = asset_no.strip(), name.strip(), note.strip()
    if not ASSET_NO_RE.fullmatch(asset_no):
        return _assets_page(request, session, user, error=f"管理番号は、{ASSET_NO_RULE}で入力してください。", status=400)
    if not (1 <= len(name) <= 100) or len(note) > 500:
        return _assets_page(request, session, user, error="名称は1〜100文字、備考は500文字以内にしてください。", status=400)
    cat_id = int(category_id) if category_id.isdigit() and session.get(Category, int(category_id)) else None
    if get_asset(session, asset_no):
        return _assets_page(request, session, user, error="その管理番号は、すでに登録されています（大文字・小文字は区別しません）。", status=400)
    session.add(Asset(asset_no=asset_no, name=name, category_id=cat_id, note=note, tag_token=_new_token(session)))
    session.commit()
    return RedirectResponse(f"/admin/assets/{asset_no}", status_code=303)


def _asset_page(request, session, user, asset, *, error=None, saved=False, status=200):
    cats = session.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()
    return _page(request, "admin_asset_edit.html", user, status, asset=asset, categories=cats,
                 url=tag_url(request, asset.tag_token), error=error, saved=saved)


@router.get("/admin/assets/{asset_no}", response_class=HTMLResponse)
def asset_edit_page(asset_no: str, request: Request, saved: int = 0,
                    user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    asset = get_asset(session, asset_no)
    if asset is None:
        return RedirectResponse("/admin/assets", status_code=303)
    return _asset_page(request, session, user, asset, saved=bool(saved))


@router.post("/admin/assets/{asset_no}")
def asset_update(asset_no: str, request: Request, name: str = Form(""), category_id: str = Form(""),
                 note: str = Form(""), csrf_token: str = Form(""),
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
    asset.category_id = int(category_id) if category_id.isdigit() and session.get(Category, int(category_id)) else None
    session.commit()
    return RedirectResponse(f"/admin/assets/{asset_no}?saved=1", status_code=303)


@router.post("/admin/assets/{asset_no}/reissue")
def asset_reissue(asset_no: str, request: Request, csrf_token: str = Form(""),
                  user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    """タグのURLを作り直す。古いタグは無効になる（タグの貼り替えが必要）。"""
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
