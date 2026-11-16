"""テーブル定義。Phase 0 は位置情報テスト用のみ（本テーブルは Phase 1 で追加）。"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    """UTCの現在時刻（タイムゾーンなし。DBにはUTCで保存する）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """ログインユーザー。管理者が1人ずつ発行する。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(String(30), unique=True)  # 英数字のみなのでVARCHARでよい
    display_name: Mapped[str] = mapped_column(Unicode(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="user")  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Asset(Base):
    """備品。管理番号は既存の資産番号（半角英数字1〜20文字。大文字・小文字は区別しない）。タグのURLには、管理番号ではなく tag_token を使う。"""

    __tablename__ = "assets"

    asset_no: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    tag_token: Mapped[str] = mapped_column(String(20), unique=True)
    note: Mapped[str] = mapped_column(Unicode(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 廃棄したら False（台帳から非表示）
    # 最新の所在（記録時に更新する）
    current_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Scan(Base):
    """備品タグのタッチ記録。追記のみ（更新・削除しない）。位置が取れなかったときは、位置はNULL。"""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_no: Mapped[str] = mapped_column(String(20), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    employee_no: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # 記録した人の社員番号（旧データは空）
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str] = mapped_column(Unicode(200), default="")
    user_agent: Mapped[str] = mapped_column(Unicode(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class GeoTest(Base):
    """位置情報テストの記録。社内各フロアでの誤差を測るために使う。"""

    __tablename__ = "geo_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 日本語を保存するため、文字列は Unicode（SQL Server では NVARCHAR）にする。
    # String は VARCHAR になり、日本語が「?」に化ける。
    label: Mapped[str] = mapped_column(Unicode(100), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str] = mapped_column(Unicode(200), default="")
    user_agent: Mapped[str] = mapped_column(Unicode(300), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
