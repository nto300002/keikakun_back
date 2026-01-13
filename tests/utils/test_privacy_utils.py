"""
PII保護ユーティリティのテスト

テスト対象:
- メールアドレスのマスキング
- 個人名のマスキング（オプション）
"""
import pytest

from app.utils.privacy_utils import mask_email, mask_name


def test_mask_email_standard():
    """
    標準的なメールアドレスのマスキング

    検証内容:
    - test@example.com → t***@example.com
    """
    result = mask_email("test@example.com")
    assert result == "t***@example.com"


def test_mask_email_short():
    """
    短いメールアドレスのマスキング

    検証内容:
    - a@example.com → a***@example.com
    """
    result = mask_email("a@example.com")
    assert result == "a***@example.com"


def test_mask_email_long_local_part():
    """
    長いローカル部分のメールアドレスのマスキング

    検証内容:
    - verylongemail@example.com → v***@example.com
    """
    result = mask_email("verylongemail@example.com")
    assert result == "v***@example.com"


def test_mask_email_none():
    """
    Noneの場合の処理

    検証内容:
    - None → "***"
    """
    result = mask_email(None)
    assert result == "***"


def test_mask_email_invalid():
    """
    不正な形式の場合の処理

    検証内容:
    - "invalid" → "***"
    """
    result = mask_email("invalid")
    assert result == "***"


def test_mask_name_full():
    """
    フルネームのマスキング

    検証内容:
    - "山田 太郎" → "山田 *"
    """
    result = mask_name("山田 太郎")
    assert result == "山田 *"


def test_mask_name_single():
    """
    単一の名前のマスキング

    検証内容:
    - "太郎" → "*"
    """
    result = mask_name("太郎")
    assert result == "*"


def test_mask_name_none():
    """
    Noneの場合の処理

    検証内容:
    - None → "***"
    """
    result = mask_name(None)
    assert result == "***"
