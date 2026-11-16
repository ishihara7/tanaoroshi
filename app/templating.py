"""Jinja2 テンプレートの共通設定。"""
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.auth import get_csrf_token

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["csrf_token"] = get_csrf_token  # テンプレートで {{ csrf_token(request) }}
