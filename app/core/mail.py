from pathlib import Path
from typing import Dict, Any, List

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


async def send_password_reset_email(
    email: str,
    staff_name: str,
    token: str
) -> None:
    """
    パスワードリセット用のメールを送信します。

    Args:
        email: スタッフのメールアドレス
        staff_name: スタッフの氏名
        token: パスワードリセットトークン（UUID）
    """
    subject = "【ケイカくん】パスワードリセットのリクエスト"

    # セキュリティレビュー対応: URLフラグメントを使用してトークンを渡す
    # フラグメント（#token=xxx）はサーバーログに記録されない
    reset_url = f"{settings.FRONTEND_URL}/auth/reset-password#token={token}"

    context = {
        "title": subject,
        "staff_name": staff_name,
        "reset_url": reset_url,
        "expire_minutes": settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    }

    await send_email(
        recipient_email=email,
        subject=subject,
        template_name="password_reset.html",
        context=context,
    )


async def send_inquiry_received_email(
    admin_email: str,
    sender_name: str,
    sender_email: str,
    category: str,
    inquiry_title: str,
    inquiry_content: str,
    created_at: str,
    inquiry_id: str
) -> None:
    """
    問い合わせ受信通知を管理者に送信します。

    Args:
        admin_email: 管理者のメールアドレス
        sender_name: 送信者名
        sender_email: 送信者のメールアドレス
        category: 問い合わせ種別
        inquiry_title: 問い合わせ件名
        inquiry_content: 問い合わせ内容
        created_at: 受信日時
        inquiry_id: 問い合わせID
    """
    subject = "【ケイカくん】新しい問い合わせが届きました"
    admin_url = f"{settings.FRONTEND_URL}/app-admin?tab=inquiries&id={inquiry_id}"

    context = {
        "title": subject,
        "sender_name": sender_name or "未設定",
        "sender_email": sender_email or "未設定",
        "category": category,
        "inquiry_title": inquiry_title,
        "inquiry_content": inquiry_content,
        "created_at": created_at,
        "admin_url": admin_url,
    }

    await send_email(
        recipient_email=admin_email,
        subject=subject,
        template_name="inquiry_received.html",
        context=context,
    )


async def send_inquiry_reply_email(
    recipient_email: str,
    recipient_name: str,
    inquiry_title: str,
    inquiry_created_at: str,
    reply_content: str,
    login_url: str = None
) -> None:
    """
    問い合わせへの返信をユーザーに送信します。

    Args:
        recipient_email: 受信者のメールアドレス
        recipient_name: 受信者名
        inquiry_title: 問い合わせ件名
        inquiry_created_at: 問い合わせ送信日時
        reply_content: 返信内容
        login_url: ログインURL（任意）
    """
    subject = "【ケイカくん】お問い合わせへの返信"

    context = {
        "title": subject,
        "recipient_name": recipient_name or "お客様",
        "inquiry_title": inquiry_title,
        "inquiry_created_at": inquiry_created_at,
        "reply_content": reply_content,
        "login_url": login_url or f"{settings.FRONTEND_URL}/auth/login",
    }

    await send_email(
        recipient_email=recipient_email,
        subject=subject,
        template_name="inquiry_reply.html",
        context=context,
    )


async def send_withdrawal_rejected_email(
    staff_email: str,
    staff_name: str,
    office_name: str,
    rejection_reason: str,
    request_date: str
) -> None:
    """
    事務所退会申請却下通知を送信します。

    Args:
        staff_email: スタッフのメールアドレス
        staff_name: スタッフ名
        office_name: 事務所名
        rejection_reason: 却下理由
        request_date: 申請日時
    """
    subject = "【ケイカくん】事務所退会申請が却下されました"
    login_url = f"{settings.FRONTEND_URL}/auth/login"

    context = {
        "title": subject,
        "staff_name": staff_name,
        "office_name": office_name,
        "rejection_reason": rejection_reason,
        "request_date": request_date,
        "login_url": login_url,
    }

    await send_email(
        recipient_email=staff_email,
        subject=subject,
        template_name="withdrawal_rejected.html",
        context=context,
    )


async def send_deadline_alert_email(
    staff_email: str,
    staff_name: str,
    office_name: str,
    renewal_alerts: List[Any],
    assessment_alerts: List[Any],
    dashboard_url: str
) -> None:
    """
    期限アラートメールを送信します。

    Args:
        staff_email: スタッフのメールアドレス
        staff_name: スタッフの氏名
        office_name: 事業所名
        renewal_alerts: 更新期限が近い利用者のリスト
        assessment_alerts: アセスメント未完了の利用者のリスト
        dashboard_url: ダッシュボードURL

    Examples:
        >>> await send_deadline_alert_email(
        ...     staff_email="staff@example.com",
        ...     staff_name="山田 太郎",
        ...     office_name="○○事業所",
        ...     renewal_alerts=[...],
        ...     assessment_alerts=[...],
        ...     dashboard_url="https://keikakun.com/protected/dashboard"
        ... )
    """
    subject = "【ケイカくん】更新期限が近い利用者がいます"

    context = {
        "title": subject,
        "staff_name": staff_name,
        "office_name": office_name,
        "renewal_alerts": [
            {
                "full_name": alert.full_name,
                "days_remaining": alert.days_remaining,
                "current_cycle_number": alert.current_cycle_number,
            }
            for alert in renewal_alerts
        ],
        "assessment_alerts": [
            {
                "full_name": alert.full_name,
                "current_cycle_number": alert.current_cycle_number,
            }
            for alert in assessment_alerts
        ],
        "dashboard_url": dashboard_url,
        "has_renewal_alerts": len(renewal_alerts) > 0,
        "has_assessment_alerts": len(assessment_alerts) > 0,
    }

    await send_email(
        recipient_email=staff_email,
        subject=subject,
        template_name="deadline_alert.html",
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