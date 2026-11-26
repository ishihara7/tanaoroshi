"""AR棚卸の判定（純粋な処理）。android-ar の InventoryTest.kt と、同じ考え方を確かめる。"""
from datetime import datetime, timedelta

from app.services.inventory_logic import Item, Read, derive, finish, moved_tokens

T0 = datetime(2026, 11, 26, 9, 0, 0)


def read(id, token, minutes=0, kind="read", **kw):
    return Read(id=id, token=token, kind=kind, read_at=T0 + timedelta(minutes=minutes), **kw)


def describe(token):
    return None, token


def test_known_token_is_confirmed_and_unknown_is_unexpected():
    d = derive([Item("a", "A")], [read(1, "a"), read(2, "z")])
    assert set(d.confirmed) == {"a"} and set(d.unexpected) == {"z"}


def test_unconfirm_cancels_the_read():
    d = derive([Item("a", "A")], [read(1, "a", 0), read(2, "a", 1, kind="unconfirm")])
    assert d.confirmed == {} and d.unexpected == {}


def test_read_again_after_unconfirm_counts():
    d = derive([Item("a", "A")], [read(1, "a", 0), read(2, "a", 1, kind="unconfirm"), read(3, "a", 2)])
    assert set(d.confirmed) == {"a"}


def test_order_follows_device_time_not_arrival_order():
    # 到着は「未確認に戻す」が先でも、端末の時刻が先なら、あとから読んだほうが有効
    d = derive([Item("a", "A")], [read(1, "a", 5), read(2, "a", 1, kind="unconfirm")])
    assert set(d.confirmed) == {"a"}


def test_last_read_of_same_token_wins():
    d = derive([Item("a", "A")], [read(1, "a", 0, floor=1, x=0.0, y=0.0), read(2, "a", 1, floor=2, x=5.0, y=5.0, moved=True)])
    assert d.confirmed["a"].floor == 2 and moved_tokens(d) == {"a"}


def test_finish_missed_item_keeps_place_and_gets_flag():
    items = [Item("a", "A", floor=1, x=5, y=6)]
    nxt, s = finish(items, derive(items, []), describe)
    assert nxt[0].missed_last and (nxt[0].x, nxt[0].y, nxt[0].floor) == (5, 6, 1) and s["missed"] == 1


def test_finish_confirmed_item_clears_flags_and_keeps_place():
    items = [Item("a", "A", x=5, y=6, missed_last=True, was_unexpected=True)]
    nxt, _ = finish(items, derive(items, [read(1, "a", x=5.5, y=6.5, floor=1)]), describe)
    assert not nxt[0].missed_last and not nxt[0].was_unexpected and (nxt[0].x, nxt[0].y) == (5, 6)


def test_finish_moved_item_updates_floor_and_place():
    items = [Item("a", "A", floor=1)]
    nxt, s = finish(items, derive(items, [read(1, "a", floor=2, x=7.0, y=8.0, moved=True)]), describe)
    assert (nxt[0].floor, nxt[0].x, nxt[0].y) == (2, 7.0, 8.0) and s["checked_moved"] == 1


def test_finish_moved_without_position_does_not_update_place():
    items = [Item("a", "A", floor=1, x=1, y=2)]
    nxt, _ = finish(items, derive(items, [read(1, "a", floor=2, moved=True)]), describe)
    assert (nxt[0].floor, nxt[0].x) == (1, 1)


def test_finish_adds_unexpected_with_position():
    d = derive([], [read(1, "z", floor=2, x=3.0, y=4.0)])
    nxt, s = finish([], d, lambda t: ("N1", "新しい備品"), new_item_err_m=0.7)
    z = nxt[0]
    assert z.was_unexpected and z.located and z.floor == 2 and z.err_m == 0.7 and z.asset_no == "N1" and s["unexpected"] == 1


def test_finish_adds_unexpected_without_position_as_floor_only():
    nxt, _ = finish([], derive([], [read(1, "z", floor=2)]), describe)
    assert not nxt[0].located and nxt[0].floor == 2 and nxt[0].err_m == 0.0


def test_finish_summary():
    items = [Item("a", "A"), Item("b", "B"), Item("c", "C")]
    d = derive(items, [read(1, "a"), read(2, "b", floor=1, x=9.0, y=9.0, moved=True), read(3, "z")])
    _, s = finish(items, d, describe)
    assert s == {"checked": 2, "checked_moved": 1, "missed": 1, "unexpected": 1}
