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