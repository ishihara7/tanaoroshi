"""備品の共通処理。管理番号は半角英数字（1〜20文字）で、英字の大文字・小文字は区別しない。"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset

# \d や \w は全角文字も通すため、半角の英数字を明示する（fullmatch で使う）
ASSET_NO_RE = re.compile(r"[A-Za-z0-9]{1,20}")
ASSET_NO_RULE = "半角英数字（1〜20文字。大文字・小文字は区別しません）"


def get_asset(session: Session, asset_no: str) -> Asset | None:
    """管理番号から備品を探す（大文字・小文字は区別しない）。"""
    return session.scalar(select(Asset).where(func.upper(Asset.asset_no) == asset_no.strip().upper()))
