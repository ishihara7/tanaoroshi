"""運用コマンド。最初の管理者を作るときに使う。

使い方：
    python -m app.cli create-admin <ログインID>
    python -m app.cli add-anchor <名前> <階> <x(m)> <y(m)> [--facing <度>]
パスワードは、実行時に（画面に表示されない形で）入力する。
"""
import argparse
import getpass
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import Base, get_engine
from app.models import Anchor, User


def create_admin(login_id: str) -> int:
    login_id = login_id.strip().lower()
    if not auth.LOGIN_ID_RE.match(login_id):
        print("ログインIDは、英数字・ハイフン・アンダースコアの3〜30文字にしてください。")
        return 1
    password = getpass.getpass("パスワード（12文字以上）: ")
    if password != getpass.getpass("もう一度入力: "):
        print("パスワードが一致しません。")
        return 1
    problem = auth.validate_new_password(password, login_id)
    if problem:
        print(problem)
        return 1

    Base.metadata.create_all(get_engine())
    with Session(get_engine()) as s:
        if s.scalar(select(User.id).where(User.login_id == login_id)):
            print("そのログインIDは、すでに使われています。")
            return 1
        # 本人が自分で決めたパスワードなので、初回の変更は求めない
        s.add(User(login_id=login_id, role="admin",
                   password_hash=auth.hash_password(password), must_change_password=False))
        s.commit()
    print(f"管理者「{login_id}」を作成しました。")
    return 0


def add_anchor(name: str, floor: int, x_m: float, y_m: float, facing_deg: float | None = None) -> int:
    """アンカーを登録し、タグに書き込むトークンを表示する。"""
    Base.metadata.create_all(get_engine())
    token = "A" + secrets.token_hex(5)  # 11文字
    with Session(get_engine()) as s:
        s.add(Anchor(anchor_token=token, name=name, floor=floor, x_m=x_m, y_m=y_m, facing_deg=facing_deg))
        s.commit()
    print(f"アンカー「{name}」を登録しました。トークン：{token}
タグ／QRに書くURL：（サイトのURL）/a/{token}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="備品所在管理システムの運用コマンド")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="管理者ユーザーを作成する")
    p.add_argument("login_id")
    a = sub.add_parser("add-anchor", help="位置の基準点（アンカー）を登録する")
    a.add_argument("name")
    a.add_argument("floor", type=int)
    a.add_argument("x_m", type=float)
    a.add_argument("y_m", type=float)
    a.add_argument("--facing", type=float, default=None, help="QRを読むとき向く方向（北を0°とした時計回り、0〜360）")
    args = parser.parse_args()
    if args.command == "create-admin":
        return create_admin(args.login_id)
    if args.command == "add-anchor":
        return add_anchor(args.name, args.floor, args.x_m, args.y_m, args.facing)
    return 1


if __name__ == "__main__":
    sys.exit(main())
