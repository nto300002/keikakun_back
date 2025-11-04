from pathlib import Path
from typing import Dict, Any

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings

# --- ConnectionConfigの生成 ---
# .envファイルから読み込んだ設定を基に、メールサーバーへの接続設定を作成します。
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD.get_secret_value() if settings.MAIL_PASSWORD else None,
    MAIL_FROM=settings.MAIL_FROM or 'default@example.com', # .envにない場合のデフォルト値
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER or '',
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=bool(settings.MAIL_USERNAME),
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / 'templates' / 'email',
    # 開発中はメールをコンソールに出力する (ローカルテスト用のprint文の代替)
    SUPPRESS_SEND=settings.MAIL_DEBUG,
)

# --- メインのメール送信関数 ---
async def send_email(
    recipient_email: str,
    subject: str,
    template_name: str,
    context: Dict[str, Any],
) -> None:
    """
    メールを非同期で送信します。

    Args:
        recipient_email: 受信者のメールアドレス
        subject: メールの件名
        template_name: 使用するHTMLテンプレートのファイル名 (例: 'verify_email.html')
        context: テンプレートに渡すコンテキスト変数
    """
    message = MessageSchema(
        subject=subject,
        recipients=[recipient_email],
        template_body=context,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message, template_name=template_name)


# --- 具体的なメール送信処理 ---
async def send_verification_email(recipient_email: str, token: str) -> None:
    """
    メールアドレス確認用のメールを送信します。
    """
    subject = "【ケイカくん】メールアドレスの確認をお願いします"
    verification_url = f"{settings.FRONTEND_URL}/auth/verify-email?token={token}"

    context = {
        "title": subject,
        "verification_url": verification_url,
    }

    await send_email(
        recipient_email=recipient_email,
        subject=subject,
        template_name="verify_email.html",
        context=context,
    )


# --- メールアドレス変更関連のメール送信 ---
async def send_email_change_verification(
    new_email: str,
    old_email: str,
    staff_name: str,
    verification_token: str
) -> None:
    """
    新しいメールアドレスに確認メールを送信します。

    Args:
        new_email: 新しいメールアドレス
        old_email: 現在のメールアドレス
        staff_name: スタッフの氏名
        verification_token: 確認トークン
    """
    subject = "【ケイカくん】メールアドレス変更の確認"
    verification_url = f"{settings.FRONTEND_URL}/auth/verify-email-change?token={verification_token}"

    context = {
        "title": subject,
        "staff_name": staff_name,
        "new_email": new_email,
        "old_email": old_email,
        "verification_url": verification_url,
        "expire_minutes": 30,
    }

    await send_email(
        recipient_email=new_email,
        subject=subject,
        template_name="email_change_verification.html",
        context=context,
    )


async def send_email_change_notification(
    old_email: str,
    staff_name: str,
    new_email: str
) -> None:
    """
    旧メールアドレスに変更リクエストの通知を送信します。

    Args:
        old_email: 現在のメールアドレス
        staff_name: スタッフの氏名
        new_email: 新しいメールアドレス（一部マスク）
    """
    subject = "【ケイカくん】メールアドレス変更のリクエスト"

    # 新しいメールアドレスの一部をマスク（プライバシー保護）
    masked_email = _mask_email(new_email)

    context = {
        "title": subject,
        "staff_name": staff_name,
        "masked_new_email": masked_email,
    }

    await send_email(
        recipient_email=old_email,
        subject=subject,
        template_name="email_change_notification.html",
        context=context,
    )


async def send_email_change_completed(
    old_email: str,
    staff_name: str,
    new_email: str
) -> None:
    """
    旧メールアドレスに変更完了通知を送信します。

    Args:
        old_email: 変更前のメールアドレス
        staff_name: スタッフの氏名
        new_email: 新しいメールアドレス（一部マスク）
    """
    subject = "【ケイカくん】メールアドレスが変更されました"

    # 新しいメールアドレスの一部をマスク
    masked_email = _mask_email(new_email)

    context = {
        "title": subject,
        "staff_name": staff_name,
        "masked_new_email": masked_email,
    }

    await send_email(
        recipient_email=old_email,
        subject=subject,
        template_name="email_change_completed.html",
        context=context,
    )


async def send_password_changed_notification(
    email: str,
    staff_name: str
) -> None:
    """
    パスワード変更完了通知を送信します。

    Args:
        email: スタッフのメールアドレス
        staff_name: スタッフの氏名
    """
    subject = "【ケイカくん】パスワードが変更されました"

    context = {
        "title": subject,
        "staff_name": staff_name,
    }

    await send_email(
        recipient_email=email,
        subject=subject,
        template_name="password_changed.html",
        context=context,
    )


def _mask_email(email: str) -> str:
    """
    メールアドレスの一部をマスクします。

    例: test.user@example.com -> t***r@example.com

    Args:
        email: マスク対象のメールアドレス

    Returns:
        マスクされたメールアドレス
    """
    local_part, domain = email.split('@')

    if len(local_part) <= 2:
        # 短すぎる場合は最初の1文字のみ表示
        masked_local = local_part[0] + '*' * (len(local_part) - 1)
    else:
        # 最初と最後の文字のみ表示、中間を*でマスク
        masked_local = local_part[0] + '*' * (len(local_part) - 2) + local_part[-1]

    return f"{masked_local}@{domain}"