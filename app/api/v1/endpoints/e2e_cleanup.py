"""
E2Eテスト専用クリーンアップエンドポイント

ENVIRONMENT が 'production' の場合は 403 を返し、一切の操作を行わない。
開発・テスト環境でのみ使用可能。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.api import deps
from app.models.staff import Staff
from app.models.enums import StaffRole
from app.core.config import settings

router = APIRouter()


@router.delete("/staffs", status_code=status.HTTP_200_OK)
async def cleanup_e2e_staffs(
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.require_owner),
) -> dict:
    """
    E2Eテスト用スタッフを一括削除する（非本番環境・owner のみ）

    対象: email が 'e2e_staff_' で始まるスタッフ
    処理: 論理削除（is_deleted=True, deleted_at=now）
    制限: ENVIRONMENT=production または owner 以外は 403 を返す
    """
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="本番環境ではこの操作は使用できません",
        )

    # e2e_staff_ で始まる未削除スタッフを取得
    result = await db.execute(
        select(Staff).where(
            Staff.email.like("e2e_staff_%"),
            Staff.is_deleted == False,  # noqa: E712
        )
    )
    staffs = result.scalars().all()

    if not staffs:
        return {"deleted_count": 0, "deleted_emails": []}

    now = datetime.now(timezone.utc)
    deleted_emails = []
    for staff in staffs:
        staff.is_deleted = True
        staff.deleted_at = now
        deleted_emails.append(staff.email)

    await db.commit()

    return {"deleted_count": len(deleted_emails), "deleted_emails": deleted_emails}
