"""
公開問い合わせAPIエンドポイント

ログイン済み・未ログインユーザーからの問い合わせ送信
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.staff import Staff
from app.models.enums import StaffRole, InquiryPriority
from app.crud.crud_inquiry import crud_inquiry
from app.schemas.inquiry import InquiryCreate, InquiryCreateResponse
from app.core.limiter import limiter
from app.utils.sanitization import sanitize_inquiry_input
from app.utils.temp_office import get_or_create_system_office

router = APIRouter()


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[Staff]:
    """
    現在のユーザーを取得（オプショナル）

    認証トークンがあれば認証済みユーザーを返し、なければNoneを返す
    """
    # Cookieからトークンを取得
    cookie_token = request.cookies.get("access_token")

    # Authorizationヘッダーからトークンを取得
    auth_header = request.headers.get("authorization")
    header_token = None
    if auth_header and auth_header.startswith("Bearer "):
        header_token = auth_header.replace("Bearer ", "")

    # トークンがない場合はNoneを返す
    final_token = cookie_token if cookie_token else header_token
    if not final_token:
        return None

    try:
        # トークンを使って認証
        return await get_current_user(request=request, db=db, token=final_token)
    except HTTPException:
        # 認証エラーの場合はNoneを返す（未ログインとして扱う）
        return None


async def get_app_admin_staff_ids(db: AsyncSession) -> list:
    """
    app_adminロールのスタッフIDリストを取得

    Returns:
        app_adminのスタッフIDリスト
    """
    stmt = select(Staff.id).where(
        Staff.role == StaffRole.app_admin,
        Staff.is_deleted == False  # noqa: E712
    )
    result = await db.execute(stmt)
    admin_ids = list(result.scalars().all())

    if not admin_ids:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="システムエラー: 問い合わせ受信者が設定されていません"
        )

    return admin_ids


@router.post("", response_model=InquiryCreateResponse)
@limiter.limit("5 per 30 minutes")
async def create_inquiry(
    *,
    db: AsyncSession = Depends(get_db),
    inquiry_in: InquiryCreate,
    request: Request,
    current_user: Optional[Staff] = Depends(get_current_user_optional)
) -> InquiryCreateResponse:
    """
    問い合わせを送信

    - ログイン済みユーザー: sender_staff_id が設定される
    - 未ログインユーザー: sender_name, sender_email を指定（必須）

    **セキュリティ**:
    - レート制限: 5回/30分（IPアドレスベース）
    - 入力サニタイズ: XSS対策、スパム検出、ハニーポット検証

    **Request Body**:
    - **title**: 問い合わせ件名（1-200文字）
    - **content**: 問い合わせ内容（1-20,000文字）
    - **category**: 問い合わせ種別（不具合 | 質問 | その他）- オプション
    - **sender_name**: 送信者名（未ログイン時は推奨、100文字以内）
    - **sender_email**: 送信者メールアドレス（未ログイン時は必須）
    """
    # 未ログインの場合のバリデーション
    if not current_user and not inquiry_in.sender_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未ログインの場合、送信者メールアドレスは必須です"
        )

    # 入力サニタイズとバリデーション
    try:
        sanitized = sanitize_inquiry_input(
            title=inquiry_in.title,
            content=inquiry_in.content,
            sender_name=inquiry_in.sender_name,
            sender_email=inquiry_in.sender_email,
            honeypot=None  # フロントエンドから送信される場合は honeypot フィールドを追加
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # IPアドレス取得
    client_host = request.client.host if request.client else None

    # User-Agent取得
    user_agent = request.headers.get("user-agent")

    # app_adminのスタッフIDを取得
    admin_recipient_ids = await get_app_admin_staff_ids(db)

    # 優先度のマッピング（カテゴリに応じて優先度を設定）
    priority = InquiryPriority.normal
    if inquiry_in.category == "不具合":
        priority = InquiryPriority.high
    elif inquiry_in.category == "質問":
        priority = InquiryPriority.normal
    else:
        priority = InquiryPriority.low

    # office_id の決定
    office_id = None

    if current_user:
        # ログイン済みユーザーの場合、プライマリ事務所を取得
        from app.models.office import OfficeStaff
        stmt = select(OfficeStaff.office_id).where(
            OfficeStaff.staff_id == current_user.id,
            OfficeStaff.is_primary == True  # noqa: E712
        )
        result = await db.execute(stmt)
        office_id = result.scalar_one_or_none()

        if not office_id:
            # プライマリ事務所がない場合、最初の事務所を使用
            stmt = select(OfficeStaff.office_id).where(
                OfficeStaff.staff_id == current_user.id
            ).limit(1)
            result = await db.execute(stmt)
            office_id = result.scalar_one_or_none()

    if not office_id:
        # 未ログインまたは事務所所属がない場合、システム事務所を取得または作成
        # システム事務所は再利用されるため、削除しない
        office_id = await get_or_create_system_office(
            db=db,
            admin_staff_id=admin_recipient_ids[0]
        )

    try:
        # 問い合わせ作成（サニタイズされた値を使用）
        inquiry_detail = await crud_inquiry.create_inquiry(
            db=db,
            sender_staff_id=current_user.id if current_user else None,
            office_id=office_id,
            title=sanitized["title"],
            content=sanitized["content"],
            priority=priority,
            admin_recipient_ids=admin_recipient_ids,
            sender_name=sanitized.get("sender_name"),
            sender_email=sanitized.get("sender_email"),
            ip_address=client_host,
            user_agent=user_agent,
            is_test_data=False
        )

        # コミット前に必要な値を取得（セッション切り離し後にアクセスできないため）
        from datetime import timezone
        inquiry_id = inquiry_detail.id
        inquiry_created_at = inquiry_detail.created_at.astimezone(timezone.utc).isoformat()

        # 問い合わせをコミット
        await db.commit()

        # 管理者へ通知メール送信（非同期・ベストエフォート）
        try:
            from app.core.mail import send_inquiry_received_email

            # 各app_adminに通知メールを送信
            for admin_id in admin_recipient_ids:
                # app_adminの情報を取得
                admin_stmt = select(Staff).where(Staff.id == admin_id)
                admin_result = await db.execute(admin_stmt)
                admin_staff = admin_result.scalar_one_or_none()

                if admin_staff and admin_staff.email:
                    await send_inquiry_received_email(
                        admin_email=admin_staff.email,
                        sender_name=sanitized.get("sender_name") or "未設定",
                        sender_email=sanitized.get("sender_email") or "未設定",
                        category=inquiry_in.category or "その他",
                        inquiry_title=sanitized["title"],
                        inquiry_content=sanitized["content"],
                        created_at=inquiry_created_at,
                        inquiry_id=str(inquiry_id)
                    )
        except Exception as email_error:
            # メール送信失敗はログに記録するが、問い合わせ作成自体は成功とする
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"管理者への通知メール送信に失敗: {str(email_error)}")

        return InquiryCreateResponse(
            id=inquiry_id,
            message="問い合わせを受け付けました"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"問い合わせの送信に失敗しました: {str(e)}"
        )
