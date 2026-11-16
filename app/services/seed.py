"""初期データ。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category

DEFAULT_CATEGORIES = ["ノートPC", "モニター", "LANハブ", "その他"]


def seed_categories(session: Session) -> None:
    """種別が1件もなければ、初期の4種類を登録する。"""
    if session.scalar(select(Category.id).limit(1)) is not None:
        return
    for i, name in enumerate(DEFAULT_CATEGORIES, start=1):
        session.add(Category(name=name, sort_order=i))
    session.commit()
