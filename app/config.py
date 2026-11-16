"""設定（環境変数から読む）。秘密情報はコードに書かない。"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_server: str
    db_name: str
    db_trusted: bool
    db_user: str
    db_password: str
    storage_connection_string: str
    storage_container: str
    secret_key: str
    cookie_secure: bool
    session_days: int


def load_settings() -> Settings:
    return Settings(
        db_server=os.environ.get("DB_SERVER", ""),
        db_name=os.environ.get("DB_NAME", ""),
        db_trusted=os.environ.get("DB_TRUSTED", "false").lower() == "true",
        db_user=os.environ.get("DB_USER", ""),
        db_password=os.environ.get("DB_PASSWORD", ""),
        storage_connection_string=os.environ.get("STORAGE_CONNECTION_STRING", ""),
        storage_container=os.environ.get("STORAGE_CONTAINER", "floors"),
        secret_key=os.environ.get("SECRET_KEY", ""),
        # 未設定のときは安全側（Secure あり）
        cookie_secure=os.environ.get("COOKIE_SECURE", "true").lower() != "false",
        session_days=int(os.environ.get("SESSION_DAYS", "30")),
    )
