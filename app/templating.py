"""Jinja2 テンプレートの共通設定。"""
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.auth import get_csrf_token

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["csrf_token"] = get_csrf_token  # テンプレートで {{ csrf_token(request) }}


def jst(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """DBのUTC時刻を、日本時間の文字列にする。"""
    return "" if dt is None else (dt + timedelta(hours=9)).strftime(fmt)


templates.env.filters["jst"] = jst
