"""
プライバシー保護ユーティリティ

PII（個人識別情報）をマスキングする関数群
- メールアドレスのマスキング
- 個人名のマスキング

使用例:
    >>> mask_email("test@example.com")
    't***@example.com'

    >>> mask_name("山田 太郎")
    '山田 *'
"""
from typing import Optional


def mask_email(email: Optional[str]) -> str:
    """
    メールアドレスをマスキング

    ローカル部分の最初の1文字のみ表示し、残りを***に置き換える
    ドメイン部分はそのまま表示

    Args:
        email: メールアドレス（例: "test@example.com"）

    Returns:
        マスキングされたメールアドレス（例: "t***@example.com"）
        不正な形式またはNoneの場合は "***"

    Examples:
        >>> mask_email("test@example.com")
        't***@example.com'

        >>> mask_email("a@example.com")
        'a***@example.com'

        >>> mask_email(None)
        '***'

        >>> mask_email("invalid")
        '***'
    """
    if email is None:
        return "***"

    if "@" not in email:
        return "***"

    try:
        local, domain = email.split("@", 1)
        if len(local) == 0:
            return "***"

        masked_local = local[0] + "***"
        return f"{masked_local}@{domain}"

    except Exception:
        return "***"


def mask_name(name: Optional[str]) -> str:
    """
    個人名をマスキング

    姓は表示し、名を*に置き換える
    スペース区切りの場合は最初の部分のみ表示

    Args:
        name: 個人名（例: "山田 太郎"）

    Returns:
        マスキングされた名前（例: "山田 *"）
        Noneの場合は "***"

    Examples:
        >>> mask_name("山田 太郎")
        '山田 *'

        >>> mask_name("太郎")
        '*'

        >>> mask_name(None)
        '***'
    """
    if name is None:
        return "***"

    if " " in name:
        parts = name.split(" ", 1)
        return f"{parts[0]} *"
    else:
        return "*"
