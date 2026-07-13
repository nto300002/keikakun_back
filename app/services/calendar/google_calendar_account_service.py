"""Google Calendar account and credential resolution."""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_office_calendar_account import crud_office_calendar_account
from app.messages import ja
from app.models.calendar_account import OfficeCalendarAccount
from app.models.enums import CalendarConnectionStatus


class GoogleCalendarAccountService:
    """Google同期に必要なアカウント状態確認とcredential復号を扱う。"""

    async def get_connected_account(
        self,
        db: AsyncSession,
        office_id: UUID,
    ) -> Optional[OfficeCalendarAccount]:
        account = await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=office_id,
        )
        if not account or account.connection_status != CalendarConnectionStatus.connected:
            return None
        return account

    async def get_connected_service_account_json(
        self,
        db: AsyncSession,
        office_id: UUID,
    ) -> str:
        account = await self.get_connected_account(db=db, office_id=office_id)
        if not account:
            raise ValueError("カレンダー連携が設定されていません")

        service_account_json = account.decrypt_service_account_key()
        if not service_account_json:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.SERVICE_ACCOUNT_KEY_NOT_FOUND,
            )
        return service_account_json
