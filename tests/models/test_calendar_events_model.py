import pytest
import uuid
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.calendar_events import (
    CalendarEvent,
    NotificationPattern,
    CalendarEventSeries,
    CalendarEventInstance,
)
from app.models.enums import (
    CalendarEventType,
    CalendarSyncStatus,
    ReminderPatternType,
    EventInstanceStatus,
)
from app.models.welfare_recipient import WelfareRecipient
from app.models.enums import GenderType
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep

pytestmark = pytest.mark.asyncio


class TestCalendarEventModel:
    """CalendarEventモデルのテスト"""

    async def test_create_calendar_event(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventの基本的な作成テスト"""
        # 準備
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="太郎",
            last_name="山田",
            first_name_furigana="たろう",
            last_name_furigana="やまだ",
            birth_day=datetime.date(1990, 1, 1),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            next_renewal_deadline=datetime.date.today() + datetime.timedelta(days=30),
        )
        db_session.add(cycle)
        await db_session.flush()

        # CalendarEvent作成
        event = CalendarEvent(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id="calendar123@group.calendar.google.com",
            event_title="山田 太郎 更新期限",
            event_description="個別支援計画の更新期限です",
            event_start_datetime=datetime.datetime.now(datetime.timezone.utc),
            event_end_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        # 検証
        assert event.id is not None
        assert event.office_id == office.id
        assert event.welfare_recipient_id == recipient.id
        assert event.support_plan_cycle_id == cycle.id
        assert event.event_type == CalendarEventType.renewal_deadline
        assert event.event_title == "山田 太郎 更新期限"
        assert event.sync_status == CalendarSyncStatus.pending
        assert event.created_by_system is True
        assert event.created_at is not None

    async def test_calendar_event_default_values(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventのデフォルト値テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="花子",
            last_name="鈴木",
            first_name_furigana="はなこ",
            last_name_furigana="すずき",
            birth_day=datetime.date(1995, 5, 15),
            gender=GenderType.female,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
        )
        db_session.add(cycle)
        await db_session.flush()

        event = CalendarEvent(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id="test@calendar.google.com",
            event_title="テストイベント",
            event_start_datetime=datetime.datetime.now(datetime.timezone.utc),
            event_end_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        # デフォルト値の確認
        assert event.sync_status == CalendarSyncStatus.pending
        assert event.created_by_system is True
        assert event.google_event_id is None
        assert event.google_event_url is None
        assert event.last_sync_at is None
        assert event.last_error_message is None

    async def test_calendar_event_exclusive_constraint(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventのcycle_idとstatus_idの排他制約テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="次郎",
            last_name="佐藤",
            first_name_furigana="じろう",
            last_name_furigana="さとう",
            birth_day=datetime.date(1988, 3, 20),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(cycle)
        await db_session.flush()

        status = SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            step_type=SupportPlanStep.monitoring,
        )
        db_session.add(status)
        await db_session.flush()

        # cycle_idとstatus_idの両方を指定 → 制約違反
        event = CalendarEvent(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            support_plan_status_id=status.id,  # 両方指定は制約違反
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id="test@calendar.google.com",
            event_title="テスト",
            event_start_datetime=datetime.datetime.now(datetime.timezone.utc),
            event_end_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        )
        db_session.add(event)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_calendar_event_unique_cycle_type(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventのcycle_id+event_type一意制約テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="三郎",
            last_name="高橋",
            first_name_furigana="さぶろう",
            last_name_furigana="たかはし",
            birth_day=datetime.date(1992, 7, 10),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(cycle)
        await db_session.flush()

        # 1つ目のイベント
        event1 = CalendarEvent(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id="test@calendar.google.com",
            event_title="イベント1",
            event_start_datetime=datetime.datetime.now(datetime.timezone.utc),
            event_end_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
            sync_status=CalendarSyncStatus.synced,
        )
        db_session.add(event1)
        await db_session.commit()

        # 同じcycle_id + event_typeの2つ目のイベント → 制約違反
        event2 = CalendarEvent(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id="test@calendar.google.com",
            event_title="イベント2",
            event_start_datetime=datetime.datetime.now(datetime.timezone.utc),
            event_end_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
            sync_status=CalendarSyncStatus.pending,
        )
        db_session.add(event2)

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_calendar_event_relationships(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventのリレーションシップテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="四郎",
            last_name="田中",
            first_name_furigana="しろう",
            last_name_furigana="たなか",
            birth_day=datetime.date(1985, 12, 25),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(cycle)
        await db_session.flush()

        event = CalendarEvent(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id="test@calendar.google.com",
            event_title="リレーションテスト",
            event_start_datetime=datetime.datetime.now(datetime.timezone.utc),
            event_end_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        )
        db_session.add(event)
        await db_session.commit()

        # Eagerロードしてリレーションシップを確認
        await db_session.refresh(event, ["office", "welfare_recipient", "support_plan_cycle"])

        assert event.office is not None
        assert event.office.id == office.id
        assert event.welfare_recipient is not None
        assert event.welfare_recipient.id == recipient.id
        assert event.support_plan_cycle is not None
        assert event.support_plan_cycle.id == cycle.id


class TestNotificationPatternModel:
    """NotificationPatternモデルのテスト"""

    async def test_create_notification_pattern(self, db_session: AsyncSession):
        """NotificationPatternの基本的な作成テスト"""
        pattern = NotificationPattern(
            pattern_name="テスト通知パターン",
            pattern_description="テスト用のパターン",
            event_type=CalendarEventType.renewal_deadline,
            reminder_days_before=[30, 25, 20, 15, 10, 5, 1],
            title_template="{recipient_name} 更新期限",
            description_template="{recipient_name}さんの更新期限まであと{days_before}日です",
            is_system_default=False,
            is_active=True,
        )
        db_session.add(pattern)
        await db_session.commit()
        await db_session.refresh(pattern)

        # 検証
        assert pattern.id is not None
        assert pattern.pattern_name == "テスト通知パターン"
        assert pattern.event_type == CalendarEventType.renewal_deadline
        assert pattern.reminder_days_before == [30, 25, 20, 15, 10, 5, 1]
        assert pattern.is_system_default is False
        assert pattern.is_active is True

    async def test_notification_pattern_unique_name(self, db_session: AsyncSession):
        """NotificationPatternのpattern_name一意制約テスト"""
        pattern1 = NotificationPattern(
            pattern_name="ユニークパターン",
            event_type=CalendarEventType.renewal_deadline,
            reminder_days_before=[30, 7, 1],
            title_template="テスト",
        )
        db_session.add(pattern1)
        await db_session.commit()

        # 同じ名前のパターン → 制約違反
        pattern2 = NotificationPattern(
            pattern_name="ユニークパターン",
            event_type=CalendarEventType.next_plan_start_date,
            reminder_days_before=[7, 1],
            title_template="テスト2",
        )
        db_session.add(pattern2)

        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestCalendarEventSeriesModel:
    """CalendarEventSeriesモデルのテスト"""

    async def test_create_calendar_event_series(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventSeriesの基本的な作成テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="五郎",
            last_name="伊藤",
            first_name_furigana="ごろう",
            last_name_furigana="いとう",
            birth_day=datetime.date(1993, 6, 30),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            next_renewal_deadline=datetime.date.today() + datetime.timedelta(days=30),
        )
        db_session.add(cycle)
        await db_session.flush()

        pattern = NotificationPattern(
            pattern_name="標準パターン",
            event_type=CalendarEventType.renewal_deadline,
            reminder_days_before=[30, 7, 1],
            title_template="{recipient_name} 更新期限",
        )
        db_session.add(pattern)
        await db_session.flush()

        # CalendarEventSeries作成
        series = CalendarEventSeries(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            series_title="伊藤 五郎 更新期限",
            base_deadline_date=datetime.date.today() + datetime.timedelta(days=30),
            pattern_type=ReminderPatternType.multiple_fixed,
            notification_pattern_id=pattern.id,
            reminder_days_before=[30, 7, 1],
            google_calendar_id="calendar@google.com",
        )
        db_session.add(series)
        await db_session.commit()
        await db_session.refresh(series)

        # 検証
        assert series.id is not None
        assert series.office_id == office.id
        assert series.welfare_recipient_id == recipient.id
        assert series.support_plan_cycle_id == cycle.id
        assert series.event_type == CalendarEventType.renewal_deadline
        assert series.series_title == "伊藤 五郎 更新期限"
        assert series.pattern_type == ReminderPatternType.multiple_fixed
        assert series.reminder_days_before == [30, 7, 1]
        assert series.series_status == CalendarSyncStatus.pending
        assert series.total_instances == 0
        assert series.completed_instances == 0

    async def test_calendar_event_series_relationships(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventSeriesのリレーションシップテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="六郎",
            last_name="渡辺",
            first_name_furigana="ろくろう",
            last_name_furigana="わたなべ",
            birth_day=datetime.date(1991, 9, 15),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(cycle)
        await db_session.flush()

        series = CalendarEventSeries(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            series_title="シリーズテスト",
            base_deadline_date=datetime.date.today() + datetime.timedelta(days=30),
            reminder_days_before=[7, 1],
            google_calendar_id="test@calendar.google.com",
        )
        db_session.add(series)
        await db_session.commit()

        # Eagerロードしてリレーションシップを確認
        await db_session.refresh(series, ["office", "welfare_recipient", "support_plan_cycle"])

        assert series.office is not None
        assert series.office.id == office.id
        assert series.welfare_recipient is not None
        assert series.welfare_recipient.id == recipient.id
        assert series.support_plan_cycle is not None
        assert series.support_plan_cycle.id == cycle.id


class TestCalendarEventInstanceModel:
    """CalendarEventInstanceモデルのテスト"""

    async def test_create_calendar_event_instance(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventInstanceの基本的な作成テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="七郎",
            last_name="山本",
            first_name_furigana="しちろう",
            last_name_furigana="やまもと",
            birth_day=datetime.date(1994, 11, 5),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(cycle)
        await db_session.flush()

        series = CalendarEventSeries(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            series_title="山本 七郎 更新期限",
            base_deadline_date=datetime.date.today() + datetime.timedelta(days=30),
            reminder_days_before=[30, 7, 1],
            google_calendar_id="calendar@google.com",
        )
        db_session.add(series)
        await db_session.flush()

        # CalendarEventInstance作成
        instance = CalendarEventInstance(
            event_series_id=series.id,
            instance_title="山本 七郎 更新期限（30日前）",
            instance_description="更新期限まであと30日です",
            event_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30),
            days_before_deadline=30,
        )
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance)

        # 検証
        assert instance.id is not None
        assert instance.event_series_id == series.id
        assert instance.instance_title == "山本 七郎 更新期限（30日前）"
        assert instance.days_before_deadline == 30
        assert instance.instance_status == EventInstanceStatus.pending
        assert instance.sync_status == CalendarSyncStatus.pending
        assert instance.reminder_sent is False

    async def test_calendar_event_instance_relationship(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventInstanceのリレーションシップテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="八郎",
            last_name="中村",
            first_name_furigana="はちろう",
            last_name_furigana="なかむら",
            birth_day=datetime.date(1987, 4, 18),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(cycle)
        await db_session.flush()

        series = CalendarEventSeries(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            series_title="インスタンスリレーションテスト",
            base_deadline_date=datetime.date.today() + datetime.timedelta(days=30),
            reminder_days_before=[7, 1],
            google_calendar_id="test@calendar.google.com",
        )
        db_session.add(series)
        await db_session.flush()

        instance = CalendarEventInstance(
            event_series_id=series.id,
            instance_title="テストインスタンス",
            event_datetime=datetime.datetime.now(datetime.timezone.utc),
            days_before_deadline=7,
        )
        db_session.add(instance)
        await db_session.commit()

        # Eagerロードしてリレーションシップを確認
        await db_session.refresh(instance, ["event_series"])

        assert instance.event_series is not None
        assert instance.event_series.id == series.id
        assert instance.event_series.series_title == "インスタンスリレーションテスト"

    async def test_calendar_event_instance_cascade_delete(
        self, db_session: AsyncSession, office_factory, employee_user_factory
    ):
        """CalendarEventSeriesのカスケード削除テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        recipient = WelfareRecipient(
            first_name="九郎",
            last_name="小林",
            first_name_furigana="くろう",
            last_name_furigana="こばやし",
            birth_day=datetime.date(1996, 2, 14),
            gender=GenderType.male,
        )
        db_session.add(recipient)
        await db_session.flush()

        cycle = SupportPlanCycle(welfare_recipient_id=recipient.id, office_id=office.id)
        db_session.add(cycle)
        await db_session.flush()

        series = CalendarEventSeries(
            office_id=office.id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            series_title="カスケード削除テスト",
            base_deadline_date=datetime.date.today() + datetime.timedelta(days=30),
            reminder_days_before=[30, 7, 1],
            google_calendar_id="test@calendar.google.com",
        )
        db_session.add(series)
        await db_session.flush()

        # 複数のインスタンスを作成
        instances = [
            CalendarEventInstance(
                event_series_id=series.id,
                instance_title=f"インスタンス{i}",
                event_datetime=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=i),
                days_before_deadline=i,
            )
            for i in [30, 7, 1]
        ]
        for instance in instances:
            db_session.add(instance)
        await db_session.commit()

        series_id = series.id

        # シリーズを削除
        await db_session.delete(series)
        await db_session.commit()

        # インスタンスがカスケード削除されたことを確認
        stmt = select(CalendarEventInstance).where(
            CalendarEventInstance.event_series_id == series_id
        )
        result = await db_session.execute(stmt)
        remaining_instances = result.scalars().all()

        assert len(remaining_instances) == 0
