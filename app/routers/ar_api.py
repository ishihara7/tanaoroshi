"""AR棚卸アプリ向けのJSON API。ログインは、既存のセッション（Cookie）。更新系は、X-CSRF-Token ヘッダーが要る。"""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import Anchor, ArItem, Asset, Inventory, InventoryRecord, User, utcnow
from app.services import devices
from app.services import inventories as svc

router = APIRouter(prefix="/api/ar")

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")
EMPLOYEE_NO_RE = re.compile(r"[A-Za-z0-9]{1,20}")
MAX_RECORDS = 500  # 1回に送れる記録の数


def _check_token(token: str) -> str:
    if not TOKEN_RE.fullmatch(token):
        raise HTTPException(400, "タグの指定が正しくありません。")
    return token


def _asset_by_token(session: Session, token: str) -> Asset | None:
    a = session.scalar(select(Asset).where(Asset.tag_token == token))
    return a if a and a.is_active else None


def item_json(i: ArItem | svc.Item) -> dict:
    return {
        "token": i.token, "asset_no": i.asset_no, "name": i.name, "floor": i.floor, "x": i.x, "y": i.y, "err_m": i.err_m,
        "located": i.located, "missed_last": i.missed_last, "was_unexpected": i.was_unexpected,
    }


@router.get("/plan")
def get_plan(request: Request, user: User = Depends(auth.api_user), session: Session = Depends(get_session)):
    """予定（備品の位置）、アンカー、開いている棚卸、CSRFトークン。端末は、これを写しとして持つ。"""
    inv = svc.current_open(session)
    return {
        "csrf": auth.get_csrf_token(request),
        "server_time": datetime.now(timezone.utc).isoformat(),
        "anchors": [
            {"token": a.anchor_token, "name": a.name, "floor": a.floor, "x_m": a.x_m, "y_m": a.y_m, "facing_deg": a.facing_deg}
            for a in session.scalars(select(Anchor).where(Anchor.is_active == True).order_by(Anchor.floor, Anchor.name))  # noqa: E712
        ],
        "items": [item_json(i) for i in svc.load_items(session)],
        # 台帳（管理対象の備品）のタグ。端末は、これにないタグを、登録させない（電波がなくても、判断できるように）
        "assets": [
            {"token": a.tag_token, "asset_no": a.asset_no, "name": a.name}
            for a in session.scalars(select(Asset).where(Asset.is_active == True).order_by(Asset.asset_no))  # noqa: E712
        ],
        "inventory": {"id": inv.id, "started_at": inv.started_at.isoformat()} if inv else None,
    }


class ItemIn(BaseModel):
    floor: int = Field(default=1, ge=-9, le=99)
    x: float
    y: float
    err_m: float = Field(default=0.0, ge=0)


@router.put("/items/{token}")
def put_item(token: str, body: ItemIn, user: User = Depends(auth.api_user), _csrf: None = Depends(auth.api_csrf), session: Session = Depends(get_session)):
    """備品登録モード：台帳にある備品の階と位置を、予定として登録する（あれば、置き換える）。

    台帳にないタグ（管理対象外）は、登録できない。棚卸で読むと、想定外になる。
    """
    _check_token(token)
    asset = _asset_by_token(session, token)
    if asset is None:
        raise HTTPException(400, "台帳にない備品です（管理対象外）。管理画面で台帳に登録してから、登録してください。")
    name = asset.name
    item = session.get(ArItem, token)
    if item is None:
        item = ArItem(token=token)
        session.add(item)
    item.asset_no = asset.asset_no
    item.name, item.floor, item.x, item.y, item.err_m, item.located = name, body.floor, body.x, body.y, body.err_m, True
    item.missed_last = item.was_unexpected = False
    session.commit()
    return item_json(item)


@router.delete("/items/{token}")
def delete_item(token: str, user: User = Depends(auth.api_user), _csrf: None = Depends(auth.api_csrf), session: Session = Depends(get_session)):
    item = session.get(ArItem, _check_token(token))
    if item is not None:
        session.delete(item)
        session.commit()
    return {"ok": True}


class RecordIn(BaseModel):
    client_id: str = Field(min_length=8, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    kind: str = Field(default="read", pattern=r"^(read|unconfirm)$")
    token: str = Field(default="", max_length=40)
    asset_no: str = Field(default="", max_length=20)  # 手入力のとき、トークンの代わりに、管理番号で指定できる
    method: str = Field(default="qr", pattern=r"^(qr|manual)$")
    floor: int | None = Field(default=None, ge=-9, le=99)
    x: float | None = None
    y: float | None = None
    moved: bool = False
    employee_no: str = Field(default="", max_length=20)
    read_at: datetime


class RecordsIn(BaseModel):
    records: list[dict] = Field(max_length=MAX_RECORDS)


def _to_utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


@router.post("/records")
def post_records(body: RecordsIn, user: User = Depends(auth.api_user), _csrf: None = Depends(auth.api_csrf), session: Session = Depends(get_session)):
    """読んだ記録を、まとめて受け取る。client_id が同じ記録は、二重にしない（再送しても安全）。

    記録ごとに、結果を返す：ok（受け取った）／duplicate（受け取り済み）／error（直らない誤り。端末は再送しない）。
    """
    ids = [r.get("client_id") for r in body.records if isinstance(r.get("client_id"), str)]
    seen = set(session.scalars(select(InventoryRecord.client_id).where(InventoryRecord.client_id.in_(ids)))) if ids else set()
    inv = None
    results = []
    for raw in body.records:
        cid = raw.get("client_id") if isinstance(raw.get("client_id"), str) else ""
        try:
            r = RecordIn.model_validate(raw)
        except ValidationError:
            results.append({"client_id": cid, "status": "error", "message": "記録の形式が正しくありません。"})
            continue
        if r.client_id in seen:
            results.append({"client_id": cid, "status": "duplicate"})
            continue
        token = r.token
        if not token and r.asset_no:
            a = session.scalar(select(Asset).where(Asset.asset_no == r.asset_no))
            token = a.tag_token if a else ""
            if not a:
                results.append({"client_id": cid, "status": "error", "message": "その管理番号の備品が、台帳にありません。"})
                continue
        if not TOKEN_RE.fullmatch(token):
            results.append({"client_id": cid, "status": "error", "message": "タグまたは管理番号が必要です。"})
            continue
        emp = r.employee_no.strip()
        if emp and not EMPLOYEE_NO_RE.fullmatch(emp):
            results.append({"client_id": cid, "status": "error", "message": "社員番号は、半角英数字（20文字まで）にしてください。"})
            continue
        if inv is None:
            inv = svc.open_or_start(session)
        session.add(InventoryRecord(
            client_id=r.client_id, inventory_id=inv.id, kind=r.kind, token=token, method=r.method,
            floor=r.floor, x=r.x, y=r.y, moved=r.moved, user_id=user.id, employee_no=emp or None,
            read_at=_to_utc_naive(r.read_at),
        ))
        seen.add(r.client_id)
        results.append({"client_id": cid, "status": "ok"})
    session.commit()
    return {"inventory_id": inv.id if inv else None, "results": results}


@router.post("/inventories/{inventory_id}/finish")
def finish_inventory(inventory_id: int, err_m: float = 0.0, user: User = Depends(auth.api_user), _csrf: None = Depends(auth.api_csrf),
                     session: Session = Depends(get_session)):
    """棚卸を終える。今回の結果が、次回の予定になる。"""
    inv = session.get(Inventory, inventory_id)
    if inv is None:
        raise HTTPException(404, "その棚卸は、ありません。")
    if inv.status != "open":
        raise HTTPException(409, "この棚卸は、すでに終えています。")
    return {"ok": True, "summary": svc.finish_inventory(session, inv, user.id, max(err_m, 0.0))}


@router.post("/inventories/{inventory_id}/undo-finish")
def undo_finish(inventory_id: int, user: User = Depends(auth.api_user), _csrf: None = Depends(auth.api_csrf), session: Session = Depends(get_session)):
    """終えた棚卸を取り消す（直近の1回だけ。次の棚卸で読んだ記録があれば、取り消せない）。"""
    inv = session.get(Inventory, inventory_id)
    if inv is None:
        raise HTTPException(404, "その棚卸は、ありません。")
    problem = svc.undo_finish(session, inv)
    if problem:
        raise HTTPException(409, problem)
    return {"ok": True}


class EnrollIn(BaseModel):
    code: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/enroll")
def enroll(body: EnrollIn, session: Session = Depends(get_session)):
    """設定コード（管理画面のQR）を、端末トークンに引き換える。ログインは要らない（コードが、その代わり）。

    トークンは、この応答でだけ見える。以降、アプリは Authorization: Bearer <トークン> で通信する。
    """
    redeemed = devices.redeem_code(session, body.code)
    if redeemed is None:
        raise HTTPException(400, "設定用のQRが、無効です（期限切れ・使用済みの可能性があります）。管理画面で、もう一度発行してください。")
    token, user = redeemed
    return {"token": token, "login_id": user.login_id}
