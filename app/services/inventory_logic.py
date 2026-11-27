"""AR棚卸の判定（DBに依存しない純粋な処理）。android-ar の Inventory.kt と、同じ考え方。

・読んだ記録から、「確認済み」と「想定外」を求める（同じ備品は、最後の記録が有効。未確認に戻した記録で取り消せる）
・棚卸を終えると、今回の結果が、次回の予定になる
"""
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True)
class Item:
    """予定の1件。"""

    token: str
    name: str
    floor: int = 1
    x: float = 0.0
    y: float = 0.0
    err_m: float = 0.0
    located: bool = True
    missed_last: bool = False
    was_unexpected: bool = False
    asset_no: str | None = None
    z: float | None = None  # 床からの高さ（m）。分からなければ None


@dataclass(frozen=True)
class Read:
    """読んだ（または未確認に戻した）1件の記録。"""

    id: int
    token: str
    kind: str  # read | unconfirm
    read_at: datetime
    floor: int | None = None
    x: float | None = None
    y: float | None = None
    moved: bool = False
    method: str = "qr"
    employee_no: str | None = None
    z: float | None = None  # 床からの高さ（m）


@dataclass(frozen=True)
class Derived:
    confirmed: dict[str, Read]  # 予定にあって、確かめた（備品ごとに、最後の記録）
    unexpected: dict[str, Read]  # 予定にないのに、読んだ


def derive(items: list[Item], reads: list[Read]) -> Derived:
    """記録を、端末の時刻順（同じ時刻なら、受信順）に並べて、最後の状態を求める。"""
    known = {i.token for i in items}
    confirmed: dict[str, Read] = {}
    unexpected: dict[str, Read] = {}
    for r in sorted(reads, key=lambda r: (r.read_at, r.id)):
        if r.kind == "unconfirm":
            confirmed.pop(r.token, None)
            unexpected.pop(r.token, None)
        elif r.token in known:
            confirmed[r.token] = r
        else:
            unexpected[r.token] = r
    return Derived(confirmed, unexpected)


def moved_tokens(d: Derived) -> set[str]:
    """確かめた備品のうち、予定と違う場所で読んだもの。"""
    return {t for t, r in d.confirmed.items() if r.moved}


def finish(
    items: list[Item], d: Derived, describe_unexpected: Callable[[str], tuple[str | None, str]], new_item_err_m: float = 0.0,
) -> tuple[list[Item], dict]:
    """棚卸を終えたあとの予定と、件数を返す。

    ・確かめた備品：前回の印を消す。場所違いで位置が取れていれば、読んだ階・位置に更新する
    ・確かめなかった備品：場所はそのままで、「前回未確認」の印を付ける
    ・想定外：新しい予定に加える（位置が取れていなければ、階だけ）
    describe_unexpected：想定外のトークンから、（管理番号, 名称）を返す。
    """
    nxt: list[Item] = []
    for it in items:
        r = d.confirmed.get(it.token)
        if r is None:
            nxt.append(replace(it, missed_last=True))
            continue
        at = it
        if r.moved and r.x is not None and r.y is not None and r.floor is not None:
            at = replace(it, floor=r.floor, x=r.x, y=r.y, z=r.z, located=True)
        nxt.append(replace(at, missed_last=False, was_unexpected=False))
    for token, r in d.unexpected.items():
        asset_no, name = describe_unexpected(token)
        located = r.x is not None and r.y is not None
        nxt.append(Item(
            token=token, name=name, floor=r.floor or 1, x=r.x or 0.0, y=r.y or 0.0, z=r.z if located else None,
            err_m=new_item_err_m if located else 0.0, located=located, was_unexpected=True, asset_no=asset_no,
        ))
    summary = {
        "checked": len(d.confirmed),
        "checked_moved": len(moved_tokens(d)),
        "missed": sum(1 for i in items if i.token not in d.confirmed),
        "unexpected": len(d.unexpected),
    }
    return nxt, summary
