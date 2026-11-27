"""棚卸アプリの端末の登録：設定コード（QR）の発行と引き換え、端末トークンの確認と無効化。

秘密の値（コード・トークン）は、ハッシュ（SHA-256）だけをDBに保存する。値そのものは、発行したときに一度見えるだけ。
いずれも、十分に長いランダムな値なので、ソルトなしのSHA-256でよい（パスワードのような、総当たりの対象ではない）。
"""
import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import DeviceToken, EnrollCode, User, utcnow

CODE_MINUTES = 10  # 設定コードの有効期間
TOUCH_MINUTES = 5  # 最後に使った時刻は、これより細かくは更新しない（書き込みを減らす）


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def issue_code(session: Session, user_id: int, label: str = "") -> str:
    """設定コードを発行する（QRに入れる）。1回だけ、CODE_MINUTES分間、使える。"""
    code = secrets.token_urlsafe(24)  # 32文字
    session.add(EnrollCode(user_id=user_id, code_hash=_hash(code), label=label.strip()[:100],
                           expires_at=utcnow() + timedelta(minutes=CODE_MINUTES)))
    session.commit()
    return code


def redeem_code(session: Session, code: str) -> tuple[str, User] | None:
    """設定コードを、端末トークンに引き換える。使えない（期限切れ・使用済み・存在しない・ユーザーが無効）ときは None。"""
    row = session.scalar(select(EnrollCode).where(EnrollCode.code_hash == _hash(code)))
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at < now:
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    # 同時に2回使われても、1回だけ成功するように、未使用の行だけを更新する
    claimed = session.execute(
        update(EnrollCode).where(EnrollCode.id == row.id, EnrollCode.used_at.is_(None)).values(used_at=now)
    ).rowcount
    if claimed != 1:
        session.rollback()
        return None
    token = secrets.token_urlsafe(32)  # 43文字
    session.add(DeviceToken(user_id=user.id, token_hash=_hash(token), label=row.label))
    session.commit()
    return token, user


def user_for_token(session: Session, token: str) -> User | None:
    """端末トークンから、ユーザーを返す。無効にした端末、無効なユーザーは None。"""
    if not token:
        return None
    dev = session.scalar(select(DeviceToken).where(DeviceToken.token_hash == _hash(token)))
    if dev is None or dev.revoked_at is not None:
        return None
    user = session.get(User, dev.user_id)
    if user is None or not user.is_active:
        return None
    now = utcnow()
    if dev.last_used_at is None or dev.last_used_at < now - timedelta(minutes=TOUCH_MINUTES):
        dev.last_used_at = now
        session.commit()
    return user


def revoke(session: Session, device_id: int) -> bool:
    dev = session.get(DeviceToken, device_id)
    if dev is None or dev.revoked_at is not None:
        return False
    dev.revoked_at = utcnow()
    session.commit()
    return True
