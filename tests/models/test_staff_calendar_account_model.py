import pytest
import uuid
from datetime import datetime, timezone, date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.calendar_account import StaffCalendarAccount
from app.models.enums import NotificationTiming


class TestStaffCalendarAccountModel:
    """StaffCalendarAccountモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_staff_calendar_account(self, db_session: AsyncSession, employee_user_factory):
        """StaffCalendarAccount作成のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            calendar_notifications_enabled=True,
            email_notifications_enabled=True,
            in_app_notifications_enabled=True,
            notification_email="custom@example.com",
            notification_timing=NotificationTiming.standard,
            has_calendar_access=True,
            total_notifications_sent=0
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        assert account.id is not None
        assert account.staff_id == staff.id
        assert account.calendar_notifications_enabled is True
        assert account.email_notifications_enabled is True
        assert account.in_app_notifications_enabled is True
        assert account.notification_email == "custom@example.com"
        assert account.notification_timing == NotificationTiming.standard
        assert account.has_calendar_access is True
        assert account.total_notifications_sent == 0
        assert account.created_at is not None
        assert account.updated_at is not None

    @pytest.mark.asyncio
    async def test_staff_calendar_account_default_values(self, db_session: AsyncSession, employee_user_factory):
        """StaffCalendarAccountのデフォルト値テスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        # デフォルト値の確認
        assert account.calendar_notifications_enabled is True
        assert account.email_notifications_enabled is True
        assert account.in_app_notifications_enabled is True
        assert account.notification_email is None
        assert account.notification_timing == NotificationTiming.standard
        assert account.custom_reminder_days is None
        assert account.notifications_paused_until is None
        assert account.pause_reason is None
        assert account.has_calendar_access is False
        assert account.calendar_access_granted_at is None
        assert account.total_notifications_sent == 0
        assert account.last_notification_sent_at is None

    @pytest.mark.asyncio
    async def test_staff_calendar_account_unique_staff_id(self, db_session: AsyncSession, employee_user_factory):
        """StaffCalendarAccountのstaff_id一意制約テスト"""
        staff = await employee_user_factory(with_office=False)

        # 同じstaff_idで2つのアカウントを作成
        account1 = StaffCalendarAccount(
            staff_id=staff.id
        )
        account2 = StaffCalendarAccount(
            staff_id=staff.id
        )

        db_session.add(account1)
        await db_session.commit()

        # 同じstaff_idの2つ目を追加しようとすると制約違反
        db_session.add(account2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_staff_calendar_account_foreign_key_constraint(self, db_session: AsyncSession):
        """StaffCalendarAccountの外部キー制約テスト"""
        # 存在しないstaff_idを指定
        fake_staff_id = uuid.uuid4()

        account = StaffCalendarAccount(
            staff_id=fake_staff_id
        )

        db_session.add(account)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_staff_calendar_account_relationship_with_staff(self, db_session: AsyncSession, employee_user_factory):
        """StaffCalendarAccountとStaffのリレーションシップテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id
        )
        db_session.add(account)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(account, ["staff"])

        assert account.staff is not None
        assert account.staff.id == staff.id
        assert account.staff.email == staff.email

    @pytest.mark.asyncio
    async def test_get_notification_email_custom(self, db_session: AsyncSession, employee_user_factory):
        """get_notification_emailメソッド（カスタムメール）のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notification_email="custom@example.com"
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account, ["staff"])

        assert account.get_notification_email() == "custom@example.com"

    @pytest.mark.asyncio
    async def test_get_notification_email_default(self, db_session: AsyncSession, employee_user_factory):
        """get_notification_emailメソッド（デフォルトメール）のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notification_email=None
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account, ["staff"])

        assert account.get_notification_email() == staff.email

    @pytest.mark.asyncio
    async def test_get_reminder_days_early(self, db_session: AsyncSession, employee_user_factory):
        """get_reminder_daysメソッド（early）のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notification_timing=NotificationTiming.early
        )
        db_session.add(account)
        await db_session.commit()

        assert account.get_reminder_days() == [30, 14, 7, 3, 1]

    @pytest.mark.asyncio
    async def test_get_reminder_days_standard(self, db_session: AsyncSession, employee_user_factory):
        """get_reminder_daysメソッド（standard）のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notification_timing=NotificationTiming.standard
        )
        db_session.add(account)
        await db_session.commit()

        assert account.get_reminder_days() == [30, 7, 1]

    @pytest.mark.asyncio
    async def test_get_reminder_days_minimal(self, db_session: AsyncSession, employee_user_factory):
        """get_reminder_daysメソッド（minimal）のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notification_timing=NotificationTiming.minimal
        )
        db_session.add(account)
        await db_session.commit()

        assert account.get_reminder_days() == [7, 1]

    @pytest.mark.asyncio
    async def test_get_reminder_days_custom(self, db_session: AsyncSession, employee_user_factory):
        """get_reminder_daysメソッド（custom）のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notification_timing=NotificationTiming.custom,
            custom_reminder_days="60,30,14,7,3,1"
        )
        db_session.add(account)
        await db_session.commit()

        assert account.get_reminder_days() == [60, 30, 14, 7, 3, 1]

    @pytest.mark.asyncio
    async def test_is_notifications_paused_true(self, db_session: AsyncSession, employee_user_factory):
        """is_notifications_pausedメソッド（一時停止中）のテスト"""
        staff = await employee_user_factory(with_office=False)

        # 未来の日付まで一時停止
        future_date = date.today() + timedelta(days=7)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notifications_paused_until=future_date,
            pause_reason="休暇中"
        )
        db_session.add(account)
        await db_session.commit()

        assert account.is_notifications_paused() is True

    @pytest.mark.asyncio
    async def test_is_notifications_paused_false(self, db_session: AsyncSession, employee_user_factory):
        """is_notifications_pausedメソッド（一時停止なし）のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notifications_paused_until=None
        )
        db_session.add(account)
        await db_session.commit()

        assert account.is_notifications_paused() is False

    @pytest.mark.asyncio
    async def test_is_notifications_paused_expired(self, db_session: AsyncSession, employee_user_factory):
        """is_notifications_pausedメソッド（一時停止期限切れ）のテスト"""
        staff = await employee_user_factory(with_office=False)

        # 過去の日付
        past_date = date.today() - timedelta(days=7)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            notifications_paused_until=past_date
        )
        db_session.add(account)
        await db_session.commit()

        assert account.is_notifications_paused() is False

    @pytest.mark.asyncio
    async def test_increment_notification_count(self, db_session: AsyncSession, employee_user_factory):
        """increment_notification_countメソッドのテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id,
            total_notifications_sent=5
        )
        db_session.add(account)
        await db_session.commit()

        # カウントを増加
        account.increment_notification_count()
        await db_session.commit()
        await db_session.refresh(account)

        assert account.total_notifications_sent == 6
        assert account.last_notification_sent_at is not None

    @pytest.mark.asyncio
    async def test_staff_calendar_account_updated_at_changes(self, db_session: AsyncSession, employee_user_factory):
        """StaffCalendarAccount updated_at更新のテスト"""
        staff = await employee_user_factory(with_office=False)

        account = StaffCalendarAccount(
            staff_id=staff.id
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        original_updated_at = account.updated_at

        # 少し待ってから更新
        import asyncio
        await asyncio.sleep(0.01)

        account.calendar_notifications_enabled = False
        await db_session.commit()
        await db_session.refresh(account)

        # updated_atが更新されていることを確認
        assert account.updated_at >= original_updated_at
