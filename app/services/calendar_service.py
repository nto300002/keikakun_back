"""カレンダー連携サービス

事業所のGoogleカレンダー連携設定を管理するサービス
- サービスアカウントJSONの処理
- 暗号化処理
- OfficeCalendarAccountの作成・更新・取得
"""

import json
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_office_calendar_account import crud_office_calendar_account
from app.schemas.calendar_account import (
    CalendarSetupRequest,
    OfficeCalendarAccountCreate,
    OfficeCalendarAccountUpdate
)
from app.models.calendar_account import OfficeCalendarAccount
from app.models.enums import CalendarConnectionStatus


class CalendarService:
    """カレンダー連携サービス"""

    async def setup_office_calendar(
        self,
        db: AsyncSession,
        request: CalendarSetupRequest
    ) -> OfficeCalendarAccount:
        """事業所のカレンダー連携を設定する

        Args:
            db: データベースセッション
            request: カレンダー設定リクエスト

        Returns:
            作成されたOfficeCalendarAccount

        Raises:
            ValueError: 既に設定が存在する場合
        """
        # 既に設定が存在するかチェック
        existing = await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=request.office_id
        )
        if existing:
            raise ValueError(f"Office {request.office_id} already has a calendar account")

        # サービスアカウントメールアドレスを抽出
        service_account_email = self._extract_service_account_email(
            request.service_account_json
        )

        # OfficeCalendarAccountCreate スキーマを作成
        create_data = OfficeCalendarAccountCreate(
            office_id=request.office_id,
            google_calendar_id=request.google_calendar_id,
            calendar_name=request.calendar_name,
            service_account_key=request.service_account_json,  # 暗号化前のJSON
            service_account_email=service_account_email,
            connection_status=CalendarConnectionStatus.not_connected,
            auto_invite_staff=request.auto_invite_staff,
            default_reminder_minutes=request.default_reminder_minutes
        )

        # CRUDレイヤーで暗号化して保存
        account = await crud_office_calendar_account.create_with_encryption(
            db=db,
            obj_in=create_data
        )

        # セッションから切り離される前にすべての属性をロード
        await db.refresh(account)

        # トランザクションをコミット
        await db.commit()

        return account

    async def update_office_calendar(
        self,
        db: AsyncSession,
        account_id: UUID,
        request: CalendarSetupRequest
    ) -> OfficeCalendarAccount:
        """事業所のカレンダー連携設定を更新する

        Args:
            db: データベースセッション
            account_id: 更新対象のアカウントID
            request: カレンダー設定リクエスト

        Returns:
            更新されたOfficeCalendarAccount

        Raises:
            ValueError: アカウントが存在しない場合
        """
        # 既存のアカウントを取得
        existing = await crud_office_calendar_account.get(db=db, id=account_id)
        if not existing:
            raise ValueError(f"Calendar account {account_id} not found")

        # サービスアカウントメールアドレスを抽出
        service_account_email = self._extract_service_account_email(
            request.service_account_json
        )

        # OfficeCalendarAccountUpdate スキーマを作成
        update_data = OfficeCalendarAccountUpdate(
            google_calendar_id=request.google_calendar_id,
            calendar_name=request.calendar_name,
            service_account_key=request.service_account_json,
            service_account_email=service_account_email,
            auto_invite_staff=request.auto_invite_staff,
            default_reminder_minutes=request.default_reminder_minutes
        )

        # CRUDレイヤーで暗号化して更新
        account = await crud_office_calendar_account.update_with_encryption(
            db=db,
            db_obj=existing,
            obj_in=update_data
        )

        # セッションから切り離される前にすべての属性をロード
        await db.refresh(account)

        # トランザクションをコミット
        await db.commit()

        return account

    async def get_office_calendar_by_office_id(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> Optional[OfficeCalendarAccount]:
        """事業所IDでカレンダー設定を取得する

        Args:
            db: データベースセッション
            office_id: 事業所ID

        Returns:
            OfficeCalendarAccount または None
        """
        return await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=office_id
        )

    async def get_office_calendar_by_id(
        self,
        db: AsyncSession,
        account_id: UUID
    ) -> Optional[OfficeCalendarAccount]:
        """アカウントIDでカレンダー設定を取得する

        Args:
            db: データベースセッション
            account_id: アカウントID

        Returns:
            OfficeCalendarAccount または None
        """
        return await crud_office_calendar_account.get(db=db, id=account_id)

    async def update_connection_status(
        self,
        db: AsyncSession,
        account_id: UUID,
        status: CalendarConnectionStatus,
        error_message: Optional[str] = None
    ) -> Optional[OfficeCalendarAccount]:
        """カレンダー連携状態を更新する

        Args:
            db: データベースセッション
            account_id: アカウントID
            status: 新しい連携状態
            error_message: エラーメッセージ（任意）

        Returns:
            更新されたOfficeCalendarAccount または None
        """
        return await crud_office_calendar_account.update_connection_status(
            db=db,
            account_id=account_id,
            status=status,
            error_message=error_message
        )

    def _extract_service_account_email(self, service_account_json: str) -> str:
        """サービスアカウントJSONからclient_emailを抽出する

        Args:
            service_account_json: サービスアカウントJSON文字列

        Returns:
            client_emailの値

        Raises:
            ValueError: client_emailが存在しない場合
        """
        try:
            parsed = json.loads(service_account_json)
            client_email = parsed.get("client_email")
            if not client_email:
                raise ValueError("client_email not found in service account JSON")
            return client_email
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {str(e)}")


# シングルトンインスタンス
calendar_service = CalendarService()
