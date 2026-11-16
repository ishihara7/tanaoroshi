import csv
import io
import random

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Asset, Scan
from tests.test_auth import client, login, make_user, token  # noqa: F401（フィクスチャを再利用）


@pytest.fixture()
def admin(client, make_user):  # noqa: F811
    login(client, make_user("admin"))
    yield client
    with Session(get_engine()) as s:
        s.execute(delete(Scan).where(Scan.asset_no.like("9996%")))
        s.execute(delete(Asset).where(Asset.asset_no.like("9996%")))
        s.commit()


def nos(n=3):
    base = random.randint(0, 999000)
    return ["9996" + f"{base + i:06d}" for i in range(n)]


def upload(c, content: bytes):
    return c.post("/admin/assets-import", data={"csrf_token": token(c, "/admin/assets-import")},
                  files={"file": ("assets.csv", content, "text/csv")})


def count(prefix="9996"):
    with Session(get_engine()) as s:
        return len(s.scalars(select(Asset).where(Asset.asset_no.like(prefix + "%"))).all())


def test_import_utf8_with_bom(admin):
    a, b, c = nos()
    body = f"管理番号,名称,備考\n{a},ノートPC A,会議室用\n{b},モニター B,\n{c},備考なし,メモ\n".encode("utf-8-sig")
    r = upload(admin, body)
    assert r.status_code == 200 and "3件を登録しました" in r.text and count() == 3
    with Session(get_engine()) as s:
        assert s.get(Asset, a).note == "会議室用" and s.get(Asset, b).note == ""
        assert len(s.get(Asset, c).tag_token) == 12


def test_import_shift_jis(admin):
    (a,) = nos(1)
    body = f"管理番号,名称\n{a},日本語の名称\n".encode("cp932")
    assert "1件を登録しました" in upload(admin, body).text
    with Session(get_engine()) as s:
        assert s.get(Asset, a).name == "日本語の名称"


def test_import_skips_duplicates_and_is_rerunnable(admin):
    a, b, _ = nos()
    body = f"管理番号,名称\n{a},A\n{b},B\n{a},Aの重複\n".encode("utf-8")
    r = upload(admin, body)
    assert "2件を登録しました" in r.text and "飛ばした行：1件" in r.text
    r = upload(admin, body)  # 同じファイルをもう一度
    assert "0件を登録しました" in r.text and count() == 2


def test_import_rolls_back_everything_on_any_error(admin):
    a, b, _ = nos()
    body = f"管理番号,名称\n{a},正常な行\nAB-12,ハイフン入りの行\n{b},名称が長すぎる行{'あ' * 100}\n".encode("utf-8")
    r = upload(admin, body)
    assert r.status_code == 400 and "1件も登録していません" in r.text
    assert "3行目" in r.text and "先頭の0が消えていないか" in r.text and "4行目" in r.text
    assert count() == 0  # 正常な行も登録されない


def test_import_alphanumeric_and_case_insensitive_duplicates(admin):
    a = "9996Ab" + "".join(random.choices("xyz", k=4))
    lines = ["管理番号,名称", f"{a},英数字の番号", f"{a.upper()},大文字違いの重複", f"{a.lower()},小文字違いの重複"]
    r = upload(admin, "\n".join(lines).encode())
    assert "1件を登録しました" in r.text and "飛ばした行：2件" in r.text and count() == 1
    # 登録済みの番号の、大文字違いは、飛ばされる
    again = upload(admin, f"管理番号,名称\n{a.upper()},登録済みの大文字違い".encode())
    assert "0件を登録しました" in again.text
    # 21文字は、誤り
    too_long = upload(admin, ("管理番号,名称\n" + "A" * 21 + ",長すぎる番号").encode())
    assert too_long.status_code == 400 and "1〜20文字" in too_long.text


def test_import_ignores_the_old_category_column(admin):
    """種別の列が付いた古いCSVも取り込める（種別は使わず、無視した列として表示する）。"""
    (a,) = nos(1)
    r = upload(admin, f"管理番号,名称,種別,備考\n{a},古い形式のCSV,ノートPC,メモ\n".encode())
    assert "1件を登録しました" in r.text and "次の列は、使いません" in r.text and "種別" in r.text
    with Session(get_engine()) as s:
        assert s.get(Asset, a).note == "メモ"


def test_import_rejects_missing_header_and_empty(admin):
    assert upload(admin, "名称\nだけ\n".encode()).status_code == 400
    assert upload(admin, b"").status_code in (400, 422)


def test_export_assets_is_excel_friendly_and_safe(admin):
    (a,) = nos(1)
    upload(admin, f"管理番号,名称,備考\n{a},=SUM(1+1),+cmd\n".encode("utf-8"))
    r = admin.get("/admin/export/assets.csv")
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf")  # BOM付きUTF-8
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["管理番号", "名称", "備考"] and "種別" not in rows[0] and rows[0][-1] == "タグURL"
    row = next(x for x in rows if x[0] == a)
    assert row[1] == "'=SUM(1+1)" and row[2] == "'+cmd"  # 数式として実行されない
    assert "/i/" in row[-1] and a not in row[-1]  # タグURLに管理番号は含まれない


def test_export_scans(admin):
    (a,) = nos(1)
    upload(admin, f"管理番号,名称\n{a},履歴用\n".encode())
    with Session(get_engine()) as s:
        s.add(Scan(asset_no=a, user_id=1, latitude=36.0, longitude=139.0, accuracy_m=15))
        s.commit()
    rows = list(csv.reader(io.StringIO(admin.get("/admin/export/scans.csv").content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["日時", "管理番号", "名称"]
    assert any(x[1] == a and x[2] == "履歴用" and x[4] == "36.0" for x in rows)


def test_csv_pages_are_admin_only(client, make_user):  # noqa: F811
    login(client, make_user("user"))
    for path in ["/admin/assets-import", "/admin/export/assets.csv", "/admin/export/scans.csv"]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
