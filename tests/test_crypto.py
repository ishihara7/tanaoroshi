import importlib.util
import pathlib
import random

import pyodbc
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import crypto
from app.db import build_odbc_string, get_engine
from app.models import Asset, Scan, utcnow

KEY = crypto.parse_key(crypto.generate_key())


# ---- 暗号化そのもの ----
def test_roundtrip_is_exact():
    for v in [36.292572242052785, 139.37613, -33.8688, 0.0, 180.0, -90.0]:
        assert crypto.decrypt_float(crypto.encrypt_float(v, "scans.latitude", KEY), "scans.latitude", KEY) == v


def test_ciphertext_hides_the_value_and_changes_every_time():
    a = crypto.encrypt_float(36.29258, "scans.latitude", KEY)
    b = crypto.encrypt_float(36.29258, "scans.latitude", KEY)
    assert a != b  # 同じ値でも、保存のたびに違う暗号文（同じ場所にあると、DBから分からない）
    assert a.startswith("v1:") and "36.29" not in a and len(a) < 100


def test_ciphertext_is_bound_to_its_column():
    c = crypto.encrypt_float(36.29258, "scans.latitude", KEY)
    with pytest.raises(ValueError):
        crypto.decrypt_float(c, "scans.longitude", KEY)  # 別の列にコピーしても、復号できない


def test_tampering_and_wrong_key_are_detected():
    c = crypto.encrypt_float(36.29258, "scans.latitude", KEY)
    body = c[3:]
    tampered = "v1:" + body[:-2] + ("A" if body[-2] != "A" else "B") + body[-1]
    with pytest.raises(ValueError):
        crypto.decrypt_float(tampered, "scans.latitude", KEY)  # 改ざん
    other = crypto.parse_key(crypto.generate_key())
    with pytest.raises(ValueError):
        crypto.decrypt_float(c, "scans.latitude", other)  # 別の鍵
    with pytest.raises(ValueError):
        crypto.decrypt_float("36.29258", "scans.latitude", KEY)  # 暗号化されていない値（数値のまま）は、受け付けない


def test_key_must_be_set_and_well_formed():
    for bad in ["", "short", "!" * 43, crypto.generate_key()[:-3]]:
        with pytest.raises(RuntimeError):
            crypto.parse_key(bad)
    assert len(crypto.parse_key(crypto.generate_key())) == 32
    assert len(crypto.generate_key()) == 43


# ---- DBに、本当に暗号文が入っているか ----
def test_db_stores_ciphertext_only_and_orm_reads_plain_values():
    no = "9992" + f"{random.randint(0, 999999):06d}"
    with Session(get_engine()) as s:
        s.add(Asset(asset_no=no, name="暗号化テスト", tag_token="Z" + f"{random.randint(0, 10**11 - 1):011d}",
                    current_lat=36.292572242052785, current_lon=139.37613, current_accuracy_m=16))
        s.add(Scan(asset_no=no, user_id=1, employee_no="E1", latitude=36.292572242052785, longitude=139.37613, accuracy_m=16))
        s.add(Scan(asset_no=no, user_id=1, employee_no="E2"))  # 位置なし（NULLのまま）
        s.commit()
    try:
        with get_engine().connect() as c:  # SQLで、DBの中身を直接見る
            raw = c.execute(text("SELECT current_lat, current_lon, current_accuracy_m FROM assets WHERE asset_no = :n"), {"n": no}).one()
            assert isinstance(raw[0], str) and raw[0].startswith("v1:") and "36.29" not in raw[0]
            assert isinstance(raw[1], str) and raw[1].startswith("v1:") and "139.37" not in raw[1]
            assert raw[2] == 16  # 誤差は、暗号化しない
            scans = c.execute(text("SELECT latitude, longitude FROM scans WHERE asset_no = :n ORDER BY id"), {"n": no}).all()
            assert scans[0][0].startswith("v1:") and scans[0][1].startswith("v1:")
            assert scans[1] == (None, None)  # 位置なしは、NULL
        with Session(get_engine()) as s:  # アプリからは、普通の数値として読める
            a = s.get(Asset, no)
            assert (a.current_lat, a.current_lon) == (36.292572242052785, 139.37613)
            got = s.query(Scan).filter(Scan.asset_no == no).order_by(Scan.id).all()
            assert (got[0].latitude, got[0].longitude) == (36.292572242052785, 139.37613)
            assert (got[1].latitude, got[1].longitude) == (None, None)
    finally:
        with Session(get_engine()) as s:
            s.execute(text("DELETE FROM scans WHERE asset_no = :n"), {"n": no})
            s.execute(text("DELETE FROM assets WHERE asset_no = :n"), {"n": no})
            s.commit()


# ---- 既存データを暗号化する移行ツール ----
def load_tool():
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "encrypt_coordinates.py"
    spec = importlib.util.spec_from_file_location("encrypt_coordinates", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_tool_encrypts_existing_numbers_safely():
    tool = load_tool()
    con = pyodbc.connect(build_odbc_string(), autocommit=False)
    cur = con.cursor()
    table = "tmp_enc_migration"
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.execute(f"CREATE TABLE {table} (id INT IDENTITY PRIMARY KEY, lat FLOAT NULL, lon FLOAT NULL, note NVARCHAR(20) NULL)")
    values = [(36.292572242052785, 139.37613), (35.0, None), (None, None), (-33.8688, 151.2093)]
    for lat, lon in values:
        cur.execute(f"INSERT INTO {table} (lat, lon, note) VALUES (?, ?, N'メモ')", lat, lon)
    con.commit()
    cols = [("lat", "tmp.lat"), ("lon", "tmp.lon")]
    try:
        # 確認だけのときは、何も変更しない
        msg = tool.migrate_table(con, table, "id", cols, KEY, apply=False)
        assert "暗号化が必要" in msg and "lat 3件" in msg and "lon 2件" in msg
        assert tool.column_type(cur, table, "lat") == "float"
        # 実行
        msg = tool.migrate_table(con, table, "id", cols, KEY, apply=True)
        assert "暗号化しました" in msg
        assert tool.column_type(cur, table, "lat") == "varchar" and tool.column_type(cur, table, "lon") == "varchar"
        rows = cur.execute(f"SELECT lat, lon, note FROM {table} ORDER BY id").fetchall()
        decoded = [(None if r[0] is None else crypto.decrypt_float(r[0], "tmp.lat", KEY),
                    None if r[1] is None else crypto.decrypt_float(r[1], "tmp.lon", KEY)) for r in rows]
        assert decoded == values  # 元の値と、完全に一致する（NULLもそのまま）
        assert [r[2] for r in rows] == ["メモ"] * 4  # ほかの列は、変わらない
        # もう一度実行しても、安全（暗号化済みは、飛ばす）
        assert "暗号化済み" in tool.migrate_table(con, table, "id", cols, KEY, apply=True)
    finally:
        con.rollback()
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        con.commit()
        con.close()


def test_migration_rolls_back_when_verification_fails(monkeypatch):
    tool = load_tool()
    con = pyodbc.connect(build_odbc_string(), autocommit=False)
    cur = con.cursor()
    table = "tmp_enc_rollback"
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.execute(f"CREATE TABLE {table} (id INT IDENTITY PRIMARY KEY, lat FLOAT NULL)")
    cur.execute(f"INSERT INTO {table} (lat) VALUES (36.5)")
    con.commit()
    try:
        monkeypatch.setattr(tool, "decrypt_float", lambda *a, **k: 0.0)  # 確認で、必ず食い違うようにする
        with pytest.raises(RuntimeError, match="確認に失敗"):
            tool.migrate_table(con, table, "id", [("lat", "tmp.lat")], KEY, apply=True)
        # 元の状態のまま（数値のまま、列も増えていない）
        assert tool.column_type(con.cursor(), table, "lat") == "float"
        assert tool.column_type(con.cursor(), table, "lat_enc") is None
        assert con.cursor().execute(f"SELECT lat FROM {table}").fetchone()[0] == 36.5
    finally:
        con.rollback()
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        con.commit()
        con.close()
