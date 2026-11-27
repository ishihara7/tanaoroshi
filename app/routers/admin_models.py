"""管理者向け：階ごとの3Dモデル（3DGS）のアップロードと、フロア図との座標合わせ、備品の位置の表示。

座標合わせは、ブラウザ（static/model_align.js）で計算し、結果をここに保存する。
"""
import json
import math
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import Anchor, ArItem, FloorModel, Inventory, User, utcnow
from app.routers.admin_inventories import _rows
from app.services import inventories as inv_svc
from app.templating import templates

router = APIRouter()

MODEL_DIR = Path(__file__).resolve().parents[2] / "var" / "models"
EXTS = (".ply", ".splat", ".ksplat")
MAX_BYTES = 800 * 1024 * 1024
CSRF_ERROR = "画面の有効期限が切れました。もう一度お試しください。"
MAX_PAIRS = 50


def _model_path(m: FloorModel) -> Path:
    return MODEL_DIR / m.filename


def _list_page(request, session, user, *, error=None, ok=None, status=200):
    models = {m.floor: m for m in session.scalars(select(FloorModel))}
    floors = sorted(set(models) | {a.floor for a in session.scalars(select(Anchor))} | {1})
    return templates.TemplateResponse(request, "admin_models.html", {
        "user": user, "floors": floors, "models": models, "error": error, "ok": ok}, status_code=status)


@router.get("/admin/models", response_class=HTMLResponse)
def models_page(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _list_page(request, session, user)


@router.post("/admin/models/upload")
async def model_upload(request: Request, floor: int = Form(...), file: UploadFile = File(...), csrf_token: str = Form(""),
                       user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    if not auth.check_csrf(request, csrf_token):
        return _list_page(request, session, user, error=CSRF_ERROR, status=400)
    if not -9 <= floor <= 99 or floor == 0:
        return _list_page(request, session, user, error="階は、-9〜99の整数（0を除く）にしてください。", status=400)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in EXTS:
        return _list_page(request, session, user, error="ファイルは、.ply、.splat、.ksplat のどれかにしてください。", status=400)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    name = f"floor_{floor}{ext}"
    tmp = MODEL_DIR / (name + ".part")
    size, head = 0, b""
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                if not head:
                    head = chunk[:3]
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("size")
                out.write(chunk)
        if size == 0 or (ext == ".ply" and head != b"ply"):
            raise ValueError("format")
    except ValueError as e:
        tmp.unlink(missing_ok=True)
        msg = "ファイルが大きすぎます（上限 800MB）。" if str(e) == "size" else "ファイルの形式が正しくありません。"
        return _list_page(request, session, user, error=msg, status=400)

    m = session.get(FloorModel, floor)
    if m is not None and m.filename != name:
        (MODEL_DIR / m.filename).unlink(missing_ok=True)  # 拡張子が変わったときは、古いファイルを消す
    tmp.replace(MODEL_DIR / name)
    if m is None:
        m = FloorModel(floor=floor, filename=name)
        session.add(m)
    m.filename, m.original_name, m.size_bytes, m.uploaded_at = name, (file.filename or "")[:200], size, utcnow()
    # モデルを差し替えたら、座標は合わせ直す
    m.scale = m.theta_deg = m.tx = m.ty = m.rms_m = m.aligned_at = None
    m.pairs_json = None
    session.commit()
    return RedirectResponse(f"/admin/models/{floor}", status_code=303)


def _result_items(session: Session, inv: Inventory, floor: int) -> list[dict]:
    """棚卸の結果を、3Dに出す札にする。確認済みは、読んだ位置。未確認は、予定の位置。想定外は、読んだ位置。
    状態：ok（確認済み）／moved（確認済みだが場所違い）／missed（未確認）／unexpected（想定外）。"""
    items, d = inv_svc.view_of(session, inv)
    planned = {i.token: i for i in items}
    out = []
    for r in _rows(items, d):
        if r["kind"] == "未確認":
            it = planned[r["token"]]
            if not it.located:
                continue
            x, y, fl, err, status = it.x, it.y, it.floor, it.err_m, "missed"
        else:
            x, y, fl, err = r["x"], r["y"], r["floor"], 0.0
            status = "unexpected" if r["kind"] == "想定外" else "moved" if r["moved"] else "ok"
        if fl != floor or x is None or y is None:
            continue
        out.append({"token": r["token"], "asset_no": r["asset_no"], "name": r["name"], "x": x, "y": y, "err_m": err, "status": status})
    return out


@router.get("/admin/models/{floor}", response_class=HTMLResponse)
def model_view(floor: int, request: Request, inv: int | None = None, user: User = Depends(auth.require_admin),
               session: Session = Depends(get_session)):
    m = session.get(FloorModel, floor)
    if m is None or not _model_path(m).exists():
        return RedirectResponse("/admin/models", status_code=303)
    anchors = [{"token": a.anchor_token, "name": a.name, "x": a.x_m, "y": a.y_m}
               for a in session.scalars(select(Anchor).where(Anchor.floor == floor, Anchor.is_active == True)  # noqa: E712
                                        .order_by(Anchor.name))]
    inventory = session.get(Inventory, inv) if inv is not None else None
    items = []
    if inventory is not None:
        items = _result_items(session, inventory, floor)
    else:
        for i in session.scalars(select(ArItem).where(ArItem.floor == floor, ArItem.located == True)  # noqa: E712
                                 .order_by(ArItem.name)):
            status = "unexpected" if i.was_unexpected else "missed" if i.missed_last else "ok"
            items.append({"token": i.token, "asset_no": i.asset_no or "", "name": i.name, "x": i.x, "y": i.y,
                          "err_m": i.err_m, "status": status})
    state = {
        "floor": floor,
        "modelUrl": f"/admin/models/{floor}/model{Path(m.filename).suffix}?v={int(m.uploaded_at.timestamp())}",
        "ySign": m.y_sign, "floorY": m.floor_y,
        "transform": None if m.scale is None else {"s": m.scale, "theta": math.radians(m.theta_deg), "tx": m.tx, "ty": m.ty,
                                                   "rms": m.rms_m},
        "pairs": json.loads(m.pairs_json) if m.pairs_json else [],
        "anchors": anchors, "items": items,
    }
    return templates.TemplateResponse(request, "admin_model_view.html", {"user": user, "model": m, "state": state,
                                                                          "inventory": inventory})


@router.get("/admin/models/{floor}/model{ext}")
def model_file(floor: int, ext: str, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    m = session.get(FloorModel, floor)
    if m is None or ext != Path(m.filename).suffix or not _model_path(m).exists():
        return JSONResponse({"detail": "not found"}, status_code=404)
    return FileResponse(_model_path(m), media_type="application/octet-stream", headers={"Cache-Control": "private, max-age=3600"})


def _finite(*vals) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals)


def _bad(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"detail": msg}, status_code=status)


@router.post("/admin/models/{floor}/align")
async def model_align(floor: int, request: Request, user: User = Depends(auth.require_admin),
                      session: Session = Depends(get_session)):
    """座標合わせの結果（と、設定）を保存する。JSON。CSRFトークンは、ヘッダー X-CSRF-Token。"""
    if not auth.check_csrf(request, request.headers.get("x-csrf-token")):
        return _bad(CSRF_ERROR)
    m = session.get(FloorModel, floor)
    if m is None:
        return _bad("モデルがありません。", 404)
    try:
        body = await request.json()
    except ValueError:
        return _bad("入力が正しくありません。")
    if not isinstance(body, dict):
        return _bad("入力が正しくありません。")

    y_sign, floor_y = body.get("y_sign"), body.get("floor_y")
    if y_sign not in (1, -1) or not _finite(floor_y):
        return _bad("上下の向きと、床の高さを確かめてください。")
    pairs = body.get("pairs", [])
    if not isinstance(pairs, list) or len(pairs) > MAX_PAIRS:
        return _bad("対応点が正しくありません。")
    clean = []
    for p in pairs:
        if not isinstance(p, dict) or not isinstance(p.get("anchor"), str) or not _finite(p.get("mx"), p.get("my"), p.get("mz")):
            return _bad("対応点が正しくありません。")
        clean.append({"anchor": p["anchor"][:20], "mx": p["mx"], "my": p["my"], "mz": p["mz"]})

    t = body.get("transform")
    if t is None:
        m.scale = m.theta_deg = m.tx = m.ty = m.rms_m = m.aligned_at = None
    else:
        if not isinstance(t, dict) or not _finite(t.get("s"), t.get("theta"), t.get("tx"), t.get("ty"), t.get("rms")) \
                or not 1e-6 < t["s"] < 1e6 or len(clean) < 2:
            return _bad("変換が正しくありません（対応点が2つ以上、必要です）。")
        m.scale, m.theta_deg, m.tx, m.ty, m.rms_m = t["s"], math.degrees(t["theta"]) % 360, t["tx"], t["ty"], t["rms"]
        m.aligned_at = utcnow()
    m.y_sign, m.floor_y, m.pairs_json = y_sign, float(floor_y), json.dumps(clean)
    session.commit()
    return {"ok": True}


@router.post("/admin/models/{floor}/delete")
def model_delete(floor: int, request: Request, csrf_token: str = Form(""), user: User = Depends(auth.require_admin),
                 session: Session = Depends(get_session)):
    m = session.get(FloorModel, floor)
    if m is not None and auth.check_csrf(request, csrf_token):
        _model_path(m).unlink(missing_ok=True)
        session.delete(m)
        session.commit()
    return RedirectResponse("/admin/models", status_code=303)
