import pytest
import uuid
import os
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.calendar_account import OfficeCalendarAccount
from app.models.enums import CalendarConnectionStatus


class TestOfficeCalendarAccountModel:
    """OfficeCalendarAccountモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_office_calendar_account(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """OfficeCalendarAccount作成のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        # 一意のgoogle_calendar_idを生成
        unique_calendar_id = f"calendar-{uuid.uuid4().hex[:8]}@group.calendar.google.com"

        account = OfficeCalendarAccount(
            office_id=office.id,
            google_calendar_id=unique_calendar_id,
            calendar_name="テスト事業所カレンダー",
            calendar_url="https://calendar.google.com/calendar/u/0?cid=xxx",
            service_account_email="service@project.iam.gserviceaccount.com",
            connection_status=CalendarConnectionStatus.connected,
            auto_invite_staff=True,
            default_reminder_minutes=1440
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        assert account.id is not None
        assert account.office_id == office.id
        assert account.google_calendar_id == unique_calendar_id
        assert account.calendar_name == "テスト事業所カレンダー"
        assert account.connection_status == CalendarConnectionStatus.connected
        assert account.auto_invite_staff is True
        assert account.default_reminder_minutes == 1440
        assert account.created_at is not None
        assert account.updated_at is not None

    @pytest.mark.asyncio
    async def test_office_calendar_account_default_values(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """OfficeCalendarAccountのデフォルト値テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        account = OfficeCalendarAccount(
            office_id=office.id
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        # デフォルト値の確認
        assert account.google_calendar_id is None
        assert account.calendar_name is None
        assert account.calendar_url is None
        assert account.service_account_key is None
        assert account.service_account_email is None
        assert account.connection_status == CalendarConnectionStatus.not_connected
        assert account.last_sync_at is None
        assert account.last_error_message is None
        assert account.auto_invite_staff is True
        assert account.default_reminder_minutes == 1440

    @pytest.mark.asyncio
    async def test_office_calendar_account_unique_office_id(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """OfficeCalendarAccountのoffice_id一意制約テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        # 同じoffice_idで2つのアカウントを作成
        account1 = OfficeCalendarAccount(
            office_id=office.id
        )
        account2 = OfficeCalendarAccount(
            office_id=office.id
        )

        db_session.add(account1)
        await db_session.commit()

        # 同じoffice_idの2つ目を追加しようとすると制約違反
        db_session.add(account2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_office_calendar_account_foreign_key_constraint(self, db_session: AsyncSession):
        """OfficeCalendarAccountの外部キー制約テスト"""
        # 存在しないoffice_idを指定
        fake_office_id = uuid.uuid4()

        account = OfficeCalendarAccount(
            office_id=fake_office_id
        )

        db_session.add(account)

        # IntegrityErrorが発生することを期待
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_office_calendar_account_relationship_with_office(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """OfficeCalendarAccountとOfficeのリレーションシップテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        account = OfficeCalendarAccount(
            office_id=office.id,
            calendar_name="テストカレンダー"
        )
        db_session.add(account)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(account, ["office"])

        assert account.office is not None
        assert account.office.id == office.id
        assert account.office.name == office.name

    @pytest.mark.asyncio
    async def test_office_calendar_account_encrypt_decrypt_key(
        self, db_session: AsyncSession, office_factory, employee_user_factory, monkeypatch
    ):
        """サービスアカウントキーの暗号化・復号化テスト"""
        # テスト用の暗号化キーを設定
        from cryptography.fernet import Fernet
        test_encryption_key = Fernet.generate_key()
        monkeypatch.setenv("CALENDAR_ENCRYPTION_KEY", test_encryption_key.decode())

        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        account = OfficeCalendarAccount(
            office_id=office.id
        )

        # 暗号化して保存
        original_key = '{"type": "service_account", "project_id": "test"}'
        account.encrypt_service_account_key(original_key)

        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        # 暗号化されているため、元の値と異なる
        assert account.service_account_key != original_key
        assert account.service_account_key is not None

        # 復号して元の値と一致することを確認
        decrypted_key = account.decrypt_service_account_key()
        assert decrypted_key == original_key

    @pytest.mark.asyncio
    async def test_office_calendar_account_connection_status_update(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """接続ステータス更新のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        account = OfficeCalendarAccount(
            office_id=office.id,
            connection_status=CalendarConnectionStatus.not_connected
        )
        db_session.add(account)
        await db_session.commit()

        # 接続済みに更新
        account.connection_status = CalendarConnectionStatus.connected
        account.last_sync_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(account)

        assert account.connection_status == CalendarConnectionStatus.connected
        assert account.last_sync_at is not None

        # エラー状態に更新
        account.connection_status = CalendarConnectionStatus.error
        account.last_error_message = "認証エラーが発生しました"
        await db_session.commit()
        await db_session.refresh(account)

        assert account.connection_status == CalendarConnectionStatus.error
        assert account.last_error_message == "認証エラーが発生しました"

    @pytest.mark.asyncio
    async def test_office_calendar_account_updated_at_changes(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """OfficeCalendarAccount updated_at更新のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        account = OfficeCalendarAccount(
            office_id=office.id
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        original_updated_at = account.updated_at

        # 少し待ってから更新
        import asyncio
        await asyncio.sleep(0.01)

        account.calendar_name = "更新されたカレンダー名"
        await db_session.commit()
        await db_session.refresh(account)

        # updated_atが更新されていることを確認
        assert account.updated_at >= original_updated_at

    @pytest.mark.asyncio
    async def test_encrypt_none_key(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """Noneのキーを暗号化した場合のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        account = OfficeCalendarAccount(
            office_id=office.id
        )

        # Noneを暗号化
        account.encrypt_service_account_key(None)

        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        assert account.service_account_key is None

    @pytest.mark.asyncio
    async def test_decrypt_none_key(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """Noneのキーを復号化した場合のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        account = OfficeCalendarAccount(
            office_id=office.id,
            service_account_key=None
        )

        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        # Noneを復号
        decrypted = account.decrypt_service_account_key()
        assert decrypted is None
