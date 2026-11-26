"""AR棚卸のDB処理：予定の読み書き、棚卸の開始・終了・終了の取り消し。判定そのものは inventory_logic にある。"""
import json
from dataclasses import asdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ArItem, Asset, Inventory, InventoryRecord, utcnow
from app.services.inventory_logic import Derived, Item, Read, derive, finish


def load_items(session: Session) -> list[Item]:
    return [
        Item(a.token, a.name, a.floor, a.x, a.y, a.err_m, a.located, a.missed_last, a.was_unexpected, a.asset_no)
        for a in session.scalars(select(ArItem).order_by(ArItem.updated_at, ArItem.token))
    ]


def replace_items(session: Session, items: list[Item]) -> None:
    session.execute(delete(ArItem))
    for i in items:
        session.add(ArItem(
            token=i.token, asset_no=i.asset_no, name=i.name, floor=i.floor, x=i.x, y=i.y, err_m=i.err_m,
            located=i.located, missed_last=i.missed_last, was_unexpected=i.was_unexpected,
        ))


def items_to_json(items: list[Item]) -> str:
    return json.dumps([asdict(i) for i in items], ensure_ascii=False)


def items_from_json(text: str | None) -> list[Item]:
    return [Item(**d) for d in json.loads(text)] if text else []


def current_open(session: Session) -> Inventory | None:
    return session.scalar(select(Inventory).where(Inventory.status == "open").order_by(Inventory.id.desc()))


def open_or_start(session: Session) -> Inventory:
    inv = current_open(session)
    if inv is None:
        inv = Inventory(status="open")
        session.add(inv)
        session.flush()
    return inv


def reads_of(session: Session, inventory_id: int) -> list[Read]:
    return [
        Read(r.id, r.token, r.kind, r.read_at, r.floor, r.x, r.y, r.moved, r.method, r.employee_no)
        for r in session.scalars(select(InventoryRecord).where(InventoryRecord.inventory_id == inventory_id))
    ]


def describe_unexpected(session: Session):
    """想定外のトークンから、（管理番号, 名称）を返す。台帳に同じタグがあれば、その備品。なければ、トークンを名前にする。"""

    def _describe(token: str) -> tuple[str | None, str]:
        a = session.scalar(select(Asset).where(Asset.tag_token == token))
        return (a.asset_no, a.name) if a else (None, token)

    return _describe


def view_of(session: Session, inv: Inventory) -> tuple[list[Item], Derived]:
    """棚卸の結果の見え方。開いている間は、いまの予定。終えたあとは、終える前の予定と、その記録。"""
    items = load_items(session) if inv.status == "open" else items_from_json(inv.before_json)
    return items, derive(items, reads_of(session, inv.id))


def finish_inventory(session: Session, inv: Inventory, user_id: int, new_item_err_m: float = 0.0) -> dict:
    """棚卸を終える。今回の結果が、次回の予定になる。終える前の予定は、取り消せるように保存する。"""
    items = load_items(session)
    d = derive(items, reads_of(session, inv.id))
    nxt, summary = finish(items, d, describe_unexpected(session), new_item_err_m)
    inv.before_json = items_to_json(items)
    inv.summary_json = json.dumps(summary)
    inv.status, inv.closed_at, inv.closed_by = "closed", utcnow(), user_id
    replace_items(session, nxt)
    session.commit()
    return summary


def undo_finish(session: Session, inv: Inventory) -> str | None:
    """終えた棚卸を、開き直す。直近に終えた1回だけ取り消せる。取り消せなければ、理由を返す。"""
    if inv.status != "closed":
        return "この棚卸は、終えていません。"
    latest = session.scalar(select(Inventory).where(Inventory.status == "closed").order_by(Inventory.closed_at.desc(), Inventory.id.desc()))
    if latest is None or latest.id != inv.id:
        return "取り消せるのは、直近に終えた棚卸だけです。"
    newer = current_open(session)
    if newer is not None:
        if session.scalar(select(InventoryRecord.id).where(InventoryRecord.inventory_id == newer.id).limit(1)) is not None:
            return "次の棚卸が、すでに始まっています（読んだ記録があります）。取り消せません。"
        session.delete(newer)  # 記録のない、空の棚卸は、捨てる
    replace_items(session, items_from_json(inv.before_json))
    inv.status, inv.closed_at, inv.closed_by, inv.summary_json, inv.before_json = "open", None, None, None, None
    session.commit()
    return None
