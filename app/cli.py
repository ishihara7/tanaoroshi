"""運用コマンド。最初の管理者を作るときに使う。

使い方：
    python -m app.cli create-admin <ログインID>
パスワードは、実行時に（画面に表示されない形で）入力する。
"""
import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import Base, get_engine
from app.models import User


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


def main() -> int:
    parser = argparse.ArgumentParser(description="備品所在管理システムの運用コマンド")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="管理者ユーザーを作成する")
    p.add_argument("login_id")
    args = parser.parse_args()
    if args.command == "create-admin":
        return create_admin(args.login_id)
    return 1


if __name__ == "__main__":
    sys.exit(main())
