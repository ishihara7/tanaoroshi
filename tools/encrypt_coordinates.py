r"""既存のDBに、数値のまま保存されている座標を、暗号化する（一度だけ実行する移行ツール）。

対象：assets（current_lat／current_lon）、scans（latitude／longitude）。
やること：暗号文用の列を追加 → 全行を暗号化 → 復号して元の値と一致することを確認 → 元の列を削除 → 列名を元に戻す。
テーブルごとに、1つの取引で行う。途中で失敗したら、そのテーブルは、元に戻る。何度実行しても安全（暗号化済みの列は、飛ばす）。

使い方（プロジェクトのフォルダで）：
    # DBの接続情報と、鍵を、環境変数に入れておく（DB_SERVER、DB_NAME、DB_USER、DB_PASSWORD、DB_TRUSTED、COORD_ENCRYPTION_KEY）
    .venv\Scripts\python.exe tools\encrypt_coordinates.py            # 確認だけ（何も変更しない）
    .venv\Scripts\python.exe tools\encrypt_coordinates.py --apply    # 実際に暗号化する

注意：実行前に、必ずバックアップを取る。鍵（COORD_ENCRYPTION_KEY）を失うと、座標は、二度と読めない。
実行した直後に、新しいコードをデプロイする（古いコードは、暗号化された列を読めない）。
"""
import argparse
import pathlib
import sys

import pyodbc

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.crypto import decrypt_float, encrypt_float, parse_key  # noqa: E402
from app.db import build_odbc_string  # noqa: E402

# (テーブル, 主キーの列, [(列, 暗号文に結びつける名前), ...])
TARGETS = [
    ("assets", "asset_no", [("current_lat", "assets.current_lat"), ("current_lon", "assets.current_lon")]),
    ("scans", "id", [("latitude", "scans.latitude"), ("longitude", "scans.longitude")]),
]


def column_type(cur, table: str, column: str) -> str | None:
    cur.execute("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND COLUMN_NAME = ?", table, column)
    row = cur.fetchone()
    return row[0].lower() if row else None


def migrate_table(con, table: str, pk: str, cols: list[tuple[str, str]], key: bytes, apply: bool) -> str:
    """1つのテーブルの座標の列を暗号化する。結果の説明（日本語）を返す。テーブル名・列名は、定数だけを渡すこと。"""
    cur = con.cursor()
    types = {col: column_type(cur, table, col) for col, _ in cols}
    if all(t is None for t in types.values()):
        return f"{table}：テーブルがない（飛ばしました）"
    todo = [(col, label) for col, label in cols if types[col] == "float"]
    done = [col for col, _ in cols if types[col] in ("varchar", "nvarchar")]
    if not todo:
        return f"{table}：暗号化済み（{', '.join(done)}）"
    counts = {col: cur.execute(f"SELECT COUNT({col}) FROM {table}").fetchone()[0] for col, _ in todo}
    summary = "、".join(f"{col} {n}件" for col, n in counts.items())
    if not apply:
        return f"{table}：暗号化が必要（{summary}）。--apply を付けると実行します"

    try:
        for col, _ in todo:
            cur.execute(f"ALTER TABLE {table} ADD {col}_enc VARCHAR(100) NULL")
        for col, label in todo:
            rows = cur.execute(f"SELECT {pk}, {col} FROM {table} WHERE {col} IS NOT NULL").fetchall()
            for pk_value, value in rows:
                cur.execute(f"UPDATE {table} SET {col}_enc = ? WHERE {pk} = ?", encrypt_float(value, label, key), pk_value)
            # 復号して、元の値と、完全に一致することを確認する
            check = cur.execute(f"SELECT {pk}, {col}, {col}_enc FROM {table} WHERE {col} IS NOT NULL").fetchall()
            for pk_value, original, encrypted in check:
                if encrypted is None or decrypt_float(encrypted, label, key) != original:
                    raise RuntimeError(f"{table}.{col}（{pk}={pk_value}）の暗号化の確認に失敗しました。元に戻します。")
        for col, _ in todo:
            cur.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
            cur.execute(f"EXEC sp_rename '{table}.{col}_enc', '{col}', 'COLUMN'")
        con.commit()
    except Exception:
        con.rollback()
        raise
    return f"{table}：暗号化しました（{summary}）"


def main() -> int:
    parser = argparse.ArgumentParser(description="DBの座標を暗号化する")
    parser.add_argument("--apply", action="store_true", help="実際に暗号化する（省略すると、確認だけ）")
    args = parser.parse_args()

    key = parse_key(load_settings().coord_key)
    con = pyodbc.connect(build_odbc_string(), autocommit=False)
    print("実行モード：" + ("実際に暗号化する" if args.apply else "確認だけ（変更しない）"))
    for table, pk, cols in TARGETS:
        print(" ", migrate_table(con, table, pk, cols, key, args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
