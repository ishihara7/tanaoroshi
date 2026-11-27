"""管理者向け：AR棚卸の結果（PCで見る）と、CSVダウンロード。"""
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import FloorModel, Inventory, InventoryRecord, User
from app.routers.admin_csv import csv_response
from app.services import inventories as svc
from app.services.inventory_logic import Derived, Item
from app.templating import jst, templates

router = APIRouter()


def _rows(items: list[Item], d: Derived) -> list[dict]:
    """結果の一覧（備品ごと）。区分：確認済み／未確認／想定外。"""
    rows = []
    for it in items:
        r = d.confirmed.get(it.token)
        rows.append({
            "kind": "確認済み" if r else "未確認", "token": it.token, "asset_no": it.asset_no or "", "name": it.name,
            "floor": r.floor if r and r.floor else it.floor, "x": r.x if r and r.x is not None else None,
            "y": r.y if r and r.y is not None else None, "z": r.z if r else None, "moved": bool(r and r.moved),
            "missed_last": it.missed_last, "method": r.method if r else "", "employee_no": (r.employee_no or "") if r else "",
            "read_at": r.read_at if r else None,
        })
    for token, r in d.unexpected.items():
        rows.append({
            "kind": "想定外", "token": token, "asset_no": "", "name": token, "floor": r.floor, "x": r.x, "y": r.y, "z": r.z,
            "moved": False, "missed_last": False, "method": r.method, "employee_no": r.employee_no or "", "read_at": r.read_at,
        })
    return rows


@router.get("/admin/inventories", response_class=HTMLResponse)
def inventories_page(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    counts = dict(session.execute(select(InventoryRecord.inventory_id, func.count()).group_by(InventoryRecord.inventory_id)).all())
    rows = [{"inv": i, "records": counts.get(i.id, 0), "summary": json.loads(i.summary_json) if i.summary_json else None}
            for i in session.scalars(select(Inventory).order_by(Inventory.id.desc()))]
    return templates.TemplateResponse(request, "admin_inventories.html", {"user": user, "rows": rows})


@router.get("/admin/inventories/{inventory_id}", response_class=HTMLResponse)
def inventory_page(inventory_id: int, request: Request, user: User = Depends(auth.require_admin),
                   session: Session = Depends(get_session)):
    inv = session.get(Inventory, inventory_id)
    if inv is None:
        return RedirectResponse("/admin/inventories", status_code=303)
    items, d = svc.view_of(session, inv)
    rows = _rows(items, d)
    groups = {k: [r for r in rows if r["kind"] == k] for k in ("確認済み", "未確認", "想定外")}
    model_floors = sorted(session.scalars(select(FloorModel.floor)))  # 3Dモデルのある階
    return templates.TemplateResponse(request, "admin_inventory.html", {
        "user": user, "inv": inv, "groups": groups, "model_floors": model_floors, "moved": [r for r in groups["確認済み"] if r["moved"]]})


@router.get("/admin/inventories/{inventory_id}/export.csv")
def inventory_csv(inventory_id: int, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    inv = session.get(Inventory, inventory_id)
    if inv is None:
        return RedirectResponse("/admin/inventories", status_code=303)
    items, d = svc.view_of(session, inv)
    order = {"確認済み": 0, "未確認": 1, "想定外": 2}
    rows = sorted(_rows(items, d), key=lambda r: (order[r["kind"]], r["asset_no"], r["token"]))
    return csv_response(
        f"inventory_{inv.id}.csv",
        ["区分", "場所違い", "前回未確認", "管理番号", "タグ", "名称", "階", "東m", "北m", "高さm", "方法", "社員番号", "読んだ日時"],
        [(r["kind"], "はい" if r["moved"] else "", "はい" if r["missed_last"] else "", r["asset_no"], r["token"], r["name"],
          r["floor"], r["x"], r["y"], r["z"], {"qr": "QR", "manual": "手入力"}.get(r["method"], ""), r["employee_no"],
          jst(r["read_at"], "%Y-%m-%d %H:%M:%S")) for r in rows],
    )
