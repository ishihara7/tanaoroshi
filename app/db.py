"""DB接続（SQLAlchemy 2.x + pyodbc + ODBC Driver 18）。"""
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import load_settings


class Base(DeclarativeBase):
    pass


def build_odbc_string() -> str:
    s = load_settings()
    parts = [
        "DRIVER={ODBC Driver 18 for SQL Server}",
        f"SERVER={s.db_server}",
        f"DATABASE={s.db_name}",
        "Encrypt=yes",
    ]
    if s.db_trusted:
        # ローカル（SQL Server Express）。自己署名証明書を許可する
        parts += ["Trusted_Connection=yes", "TrustServerCertificate=yes"]
    else:
        # Azure SQL。サーバー証明書を検証する
        parts += [f"UID={s.db_user}", f"PWD={s.db_password}", "TrustServerCertificate=no"]
    return ";".join(parts)


def create_db_engine() -> Engine:
    url = "mssql+pyodbc:///?odbc_connect=" + quote_plus(build_odbc_string())
    return create_engine(url, pool_pre_ping=True)


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session():
    """FastAPIの依存関数。リクエストごとにセッションを渡す。"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
