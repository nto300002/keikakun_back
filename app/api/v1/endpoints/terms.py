"""
利用規約・プライバシーポリシー同意管理 APIエンドポイント
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, schemas
from app.api import deps
from app.models.staff import Staff

router = APIRouter()

# 現在の規約バージョン（定数として管理）
CURRENT_TERMS_VERSION = "1.0"
CURRENT_PRIVACY_VERSION = "1.0"


@router.post("/agree", response_model=schemas.AgreeToTermsResponse)
async def agree_to_terms(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
    request: Request,
    agreement_data: schemas.AgreeToTermsRequest
):
    """
    利用規約・プライバシーポリシーに同意する

    Args:
        db: データベースセッション
        current_user: 現在のユーザー
        request: HTTPリクエスト
        agreement_data: 同意データ

    Returns:
        同意レスポンス

    Raises:
        HTTPException: 同意が不完全な場合
    """
    if not agreement_data.agree_to_terms or not agreement_data.agree_to_privacy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="利用規約とプライバシーポリシーの両方に同意する必要があります"
        )

    # IPアドレスとユーザーエージェントを取得
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # 同意を記録
    agreement = await crud.terms_agreement.agree_to_terms(
        db,
        staff_id=current_user.id,
        terms_version=agreement_data.terms_version,
        privacy_version=agreement_data.privacy_version,
        ip_address=ip_address,
        user_agent=user_agent
    )

    await db.commit()

    return schemas.AgreeToTermsResponse(
        message="利用規約とプライバシーポリシーへの同意が記録されました",
        agreed_at=agreement.terms_of_service_agreed_at,
        terms_version=agreement.terms_version,
        privacy_version=agreement.privacy_version
    )


@router.get("/status", response_model=schemas.TermsAgreementRead)
async def get_agreement_status(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user)
):
    """
    現在の同意状態を取得

    Args:
        db: データベースセッション
        current_user: 現在のユーザー

    Returns:
        同意履歴

    Raises:
        HTTPException: 同意履歴が見つからない場合
    """
    agreement = await crud.terms_agreement.get_by_staff_id(
        db,
        staff_id=current_user.id
    )

    if not agreement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="同意履歴が見つかりません"
        )

    return agreement


@router.get("/required")
async def check_agreement_required(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user)
):
    """
    同意が必要かチェック

    Args:
        db: データベースセッション
        current_user: 現在のユーザー

    Returns:
        同意が必要かどうかの情報
    """
    agreement = await crud.terms_agreement.get_by_staff_id(
        db,
        staff_id=current_user.id
    )

    if not agreement:
        return {
            "required": True,
            "reason": "未同意",
            "current_terms_version": CURRENT_TERMS_VERSION,
            "current_privacy_version": CURRENT_PRIVACY_VERSION
        }

    needs_terms_update = not agreement.has_agreed_to_current_terms(CURRENT_TERMS_VERSION)
    needs_privacy_update = not agreement.has_agreed_to_current_privacy(CURRENT_PRIVACY_VERSION)

    if needs_terms_update or needs_privacy_update:
        return {
            "required": True,
            "reason": "規約が更新されました",
            "needs_terms_update": needs_terms_update,
            "needs_privacy_update": needs_privacy_update,
            "current_terms_version": CURRENT_TERMS_VERSION,
            "current_privacy_version": CURRENT_PRIVACY_VERSION,
            "agreed_terms_version": agreement.terms_version,
            "agreed_privacy_version": agreement.privacy_version
        }

    return {
        "required": False,
        "terms_version": agreement.terms_version,
        "privacy_version": agreement.privacy_version
    }
