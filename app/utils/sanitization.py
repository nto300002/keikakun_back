"""
入力サニタイズユーティリティ

XSS対策、HTMLタグの除去、危険な文字列のエスケープ
"""
import re
from typing import Optional
import html


def sanitize_html(text: Optional[str]) -> Optional[str]:
    """
    HTMLタグを除去し、危険な文字列をエスケープ

    Args:
        text: サニタイズ対象のテキスト

    Returns:
        サニタイズされたテキスト

    Examples:
        >>> sanitize_html("<script>alert('XSS')</script>")
        "&lt;script&gt;alert('XSS')&lt;/script&gt;"
        >>> sanitize_html("Normal text")
        "Normal text"
    """
    if text is None:
        return None

    # HTMLエンティティをエスケープ
    text = html.escape(text)

    return text


def sanitize_text_content(text: Optional[str], max_length: Optional[int] = None) -> Optional[str]:
    """
    テキストコンテンツをサニタイズ

    Args:
        text: サニタイズ対象のテキスト
        max_length: 最大文字数（省略可）

    Returns:
        サニタイズされたテキスト

    Note:
        - HTMLタグを除去
        - 制御文字を除去（改行・タブは保持）
        - 連続する空白を1つにまとめる
        - 前後の空白を削除
    """
    if text is None:
        return None

    # HTMLタグを除去（<...>を削除）
    text = re.sub(r'<[^>]+>', '', text)

    # 制御文字を除去（改行とタブは保持）
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    # 連続する空白を1つにまとめる（改行は保持）
    text = re.sub(r'[ \t]+', ' ', text)

    # 前後の空白を削除
    text = text.strip()

    # 最大文字数制限
    if max_length is not None and len(text) > max_length:
        text = text[:max_length]

    return text


def sanitize_email(email: Optional[str]) -> Optional[str]:
    """
    メールアドレスをサニタイズ

    Args:
        email: メールアドレス

    Returns:
        サニタイズされたメールアドレス

    Note:
        - 小文字に変換
        - 前後の空白を削除
        - 基本的なフォーマットチェック
    """
    if email is None:
        return None

    # 前後の空白を削除
    email = email.strip()

    # 小文字に変換
    email = email.lower()

    # 基本的なメールアドレス形式チェック
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        raise ValueError(f"Invalid email format: {email}")

    return email


def contains_spam_patterns(text: str) -> bool:
    """
    スパムパターンを検出

    Args:
        text: チェック対象のテキスト

    Returns:
        スパムパターンが含まれている場合True

    Note:
        簡易的なスパム検出。以下のパターンをチェック：
        - 過度なURL（3つ以上）
        - 過度な大文字使用（50%以上）
        - 禁止キーワード
    """
    if not text:
        return False

    # URLの数をカウント
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)
    if len(urls) >= 3:
        return True

    # 大文字の割合をチェック
    if len(text) > 0:
        uppercase_ratio = sum(1 for c in text if c.isupper()) / len(text)
        if uppercase_ratio > 0.5 and len(text) > 20:
            return True

    # 禁止キーワード
    spam_keywords = [
        'viagra', 'cialis', 'casino', 'lottery', 'winner',
        '無料', '当選', 'クリック', '今すぐ', '限定'
    ]
    text_lower = text.lower()
    for keyword in spam_keywords:
        if keyword in text_lower:
            return True

    return False


def validate_honeypot(honeypot_value: Optional[str]) -> bool:
    """
    ハニーポットフィールドを検証

    Args:
        honeypot_value: ハニーポットフィールドの値

    Returns:
        ボットでない場合True（ハニーポットが空の場合）

    Note:
        ハニーポットは人間には見えないフィールド。
        ボットは全フィールドを埋めるため、値が入っている場合はボット判定。
    """
    # ハニーポットフィールドが空ならOK
    return honeypot_value is None or honeypot_value == ""


def sanitize_inquiry_input(
    title: str,
    content: str,
    sender_name: Optional[str] = None,
    sender_email: Optional[str] = None,
    honeypot: Optional[str] = None
) -> dict:
    """
    問い合わせ入力を一括でサニタイズ・検証

    Args:
        title: 件名
        content: 内容
        sender_name: 送信者名（任意）
        sender_email: 送信者メールアドレス（任意）
        honeypot: ハニーポットフィールド

    Returns:
        サニタイズされた入力データ

    Raises:
        ValueError: バリデーションエラー
    """
    # ハニーポットチェック
    if not validate_honeypot(honeypot):
        raise ValueError("Invalid submission detected")

    # 件名をサニタイズ
    sanitized_title = sanitize_text_content(title, max_length=200)
    if not sanitized_title or len(sanitized_title) < 1:
        raise ValueError("Title is required and must be at least 1 character")

    # 内容をサニタイズ
    sanitized_content = sanitize_text_content(content, max_length=20000)
    if not sanitized_content or len(sanitized_content) < 1:
        raise ValueError("Content is required and must be at least 1 character")

    # スパムチェック
    if contains_spam_patterns(sanitized_content):
        raise ValueError("Spam detected")

    # 送信者名をサニタイズ
    sanitized_name = None
    if sender_name:
        sanitized_name = sanitize_text_content(sender_name, max_length=100)

    # 送信者メールアドレスをサニタイズ
    sanitized_email = None
    if sender_email:
        sanitized_email = sanitize_email(sender_email)

    return {
        "title": sanitized_title,
        "content": sanitized_content,
        "sender_name": sanitized_name,
        "sender_email": sanitized_email
    }
