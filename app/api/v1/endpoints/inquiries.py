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
        # 未ログインまたは事務所所属がない場合、システム用のダミー事務所IDを使用
        # または、office_idをNULLにする（Message.office_idがNULL許容の場合）
        # ここでは、最初のapp_adminの事務所を使用
        from app.models.office import OfficeStaff
        stmt = select(OfficeStaff.office_id).where(
            OfficeStaff.staff_id.in_(admin_recipient_ids)
        ).limit(1)
        result = await db.execute(stmt)
        office_id = result.scalar_one_or_none()

        if not office_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="システムエラー: 問い合わせ受付用の事務所が設定されていません"
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

        await db.commit()

        # TODO: 管理者へ通知メール送信
        # from app.utils.email_utils import send_and_log_email
        # await send_and_log_email(...)

        return InquiryCreateResponse(
            id=inquiry_detail.id,
            message="問い合わせを受け付けました"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"問い合わせの送信に失敗しました: {str(e)}"
        )
