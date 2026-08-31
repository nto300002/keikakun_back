"""WebAuthnで共有するバイト列・challenge処理。"""

import base64
import hashlib
import re


_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]*$")


def base64url_encode(value: bytes) -> str:
    """WebAuthn JSONで用いるpaddingなしbase64urlに変換する。"""
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    """paddingなしbase64urlを厳密に復元する。"""
    if not _BASE64URL_PATTERN.fullmatch(value):
        raise ValueError("base64url形式が不正です")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def hash_challenge(challenge: bytes) -> str:
    """challengeを永続化する前にSHA-256で一方向化する。"""
    return hashlib.sha256(challenge).hexdigest()
