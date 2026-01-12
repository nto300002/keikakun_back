"""サイクル作成時の自動イベント作成テスト（統合テスト）

Phase 1-2: 個別支援計画のサイクル作成時に、カレンダーイベントが自動作成されることを確認

このテストは以下を検証します:
- 利用者作成時に更新期限イベントが自動作成される
- イベントの日時が正しい（開始: 今日9:00、終了: 期限日18:00）
- sync_statusが`pending`になっている
- カレンダーイベントがDBに正しく保存される

実行コマンド:
pytest tests/integration/test_calendar_event_auto_creation.py -v -s --tb=short
"""

import pytest
from datetime import date, datetime, time, timedelta
from sqlalchemy import select

from app.models.calendar_events import CalendarEvent
from app.models.enums import CalendarSyncStatus, CalendarEventType
from app.services.welfare_recipient_service import WelfareRecipientService
from app.services.support_plan_service import SupportPlanService


@pytest.mark.asyncio
async def test_create_recipient_creates_renewal_deadline_event(
    db_session,
    calendar_account_fixture,
    service_admin_user_factory
):
    """利用者作成時に更新期限イベントが自動作成されることを確認

    テスト内容:
    1. カレンダー設定済みの事業所で利用者を作成
    2. CalendarEventテーブルにレコードが作成されたことを確認
    3. イベントタイトルが正しいことを確認
    4. sync_statusがpendingになっていることを確認
    5. event_typeがrenewal_deadlineになっていることを確認
    """
    # Arrange
    from app.schemas.welfare_recipient import UserRegistrationRequest, BasicInfo, ContactAddress, DisabilityInfo
    from app.models.enums import GenderType, FormOfResidence, MeansOfTransportation, LivelihoodProtection

    admin = await service_admin_user_factory(session=db_session)
    office_id = calendar_account_fixture.office_id

    # UserRegistrationRequestスキーマに合わせたデータを作成
    registration_data = UserRegistrationRequest(
        basic_info=BasicInfo(
            firstName="太郎",
            lastName="山田",
            firstNameFurigana="タロウ",
            lastNameFurigana="ヤマダ",
            birthDay=date(1990, 1, 1),
            gender=GenderType.male
        ),
        contact_address=ContactAddress(
            address="東京都渋谷区1-1-1",
            formOfResidence=FormOfResidence.home_alone,
            meansOfTransportation=MeansOfTransportation.walk,
            tel="03-1234-5678"
        ),
        disability_info=DisabilityInfo(
            disabilityOrDiseaseName="テスト",
            livelihoodProtection=LivelihoodProtection.not_receiving
        )
    )

    service = WelfareRecipientService()

    # Act
    recipient_id = await service.create_recipient_with_initial_plan(
        db=db_session,
        registration_data=registration_data,
        office_id=office_id
    )

    await db_session.flush()

    # Assert - CalendarEventが作成されたか確認
    result = await db_session.execute(
        select(CalendarEvent).where(
            CalendarEvent.welfare_recipient_id == recipient_id,
            CalendarEvent.event_type == CalendarEventType.renewal_deadline
        )
    )
    calendar_event = result.scalar_one_or_none()

    assert calendar_event is not None, "更新期限イベントが作成されていません"
    assert calendar_event.event_title == "山田 太郎 更新期限まで残り1ヶ月", f"イベントタイトルが正しくありません: {calendar_event.event_title}"
    assert calendar_event.sync_status == CalendarSyncStatus.pending, f"sync_statusがpendingではありません: {calendar_event.sync_status}"
    assert "更新期限" in calendar_event.event_description, "イベント説明に「更新期限」が含まれていません"

    print(f"\n✅ 更新期限イベント作成成功")
    print(f"   イベントID: {calendar_event.id}")
    print(f"   タイトル: {calendar_event.event_title}")
    print(f"   説明: {calendar_event.event_description}")
    print(f"   sync_status: {calendar_event.sync_status}")


@pytest.mark.asyncio
async def test_renewal_deadline_event_has_correct_datetime(
    db_session,
    calendar_account_fixture,
    welfare_recipient_fixture,
    service_admin_user_factory
):
    """更新期限イベントの日時が正しく設定されることを確認

    テスト内容:
    1. 新しいサイクルを作成（次回更新期限を指定）
    2. CalendarEventの開始時刻が150日後の9:00であることを確認
    3. CalendarEventの終了時刻が180日後（更新期限日）の18:00であることを確認
    4. イベントタイトルに利用者名が含まれることを確認
    """
    # Arrange
    from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
    from app.models.enums import SupportPlanStep

    admin = await service_admin_user_factory(session=db_session)
    office_id = calendar_account_fixture.office_id

    # まず古いサイクルを作成（モニタリングが完了した状態）
    old_cycle = SupportPlanCycle(
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=office_id,
        plan_cycle_start_date=date.today() - timedelta(days=180),
        next_renewal_deadline=date.today(),
        is_latest_cycle=True,
        cycle_number=1
    )
    db_session.add(old_cycle)
    await db_session.flush()

    # モニタリングステータスを作成
    monitoring_status = SupportPlanStatus(
        plan_cycle_id=old_cycle.id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=office_id,
        step_type=SupportPlanStep.monitoring,
        is_latest_status=True,
        completed=True,
        completed_at=datetime.now()
    )
    db_session.add(monitoring_status)
    await db_session.flush()
    await db_session.refresh(old_cycle)

    service = SupportPlanService()

    # Act - 新しいサイクルを作成
    await service._create_new_cycle_from_monitoring(
        db=db_session,
        old_cycle=old_cycle,
        monitoring_completed_at=monitoring_status.completed_at
    )

    await db_session.flush()

    # 新しいサイクルを取得
    from sqlalchemy import select
    result = await db_session.execute(
        select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == welfare_recipient_fixture.id,
            SupportPlanCycle.cycle_number == 2
        )
    )
    new_cycle = result.scalar_one()

    # Assert
    result = await db_session.execute(
        select(CalendarEvent).where(
            CalendarEvent.support_plan_cycle_id == new_cycle.id,
            CalendarEvent.event_type == CalendarEventType.renewal_deadline
        )
    )
    calendar_event = result.scalar_one()

    # 開始時刻: 150日後 9:00 (JST) - 更新期限30日前
    from zoneinfo import ZoneInfo
    jst = ZoneInfo("Asia/Tokyo")
    expected_start_date = date.today() + timedelta(days=150)
    expected_start = datetime.combine(expected_start_date, time(9, 0), tzinfo=jst)
    # 終了時刻: 180日後（next_renewal_deadline）18:00 (JST)
    expected_end = datetime.combine(new_cycle.next_renewal_deadline, time(18, 0), tzinfo=jst)

    assert calendar_event.event_start_datetime == expected_start, \
        f"開始時刻が正しくありません: {calendar_event.event_start_datetime} (期待: {expected_start})"
    assert calendar_event.event_end_datetime == expected_end, \
        f"終了時刻が正しくありません: {calendar_event.event_end_datetime} (期待: {expected_end})"

    assert welfare_recipient_fixture.last_name in calendar_event.event_title, \
        f"イベントタイトルに利用者の姓が含まれていません: {calendar_event.event_title}"
    assert welfare_recipient_fixture.first_name in calendar_event.event_title, \
        f"イベントタイトルに利用者の名が含まれていません: {calendar_event.event_title}"

    print(f"\n✅ 更新期限イベントの日時設定が正しい")
    print(f"   開始: {calendar_event.event_start_datetime}")
    print(f"   終了: {calendar_event.event_end_datetime}")
    print(f"   タイトル: {calendar_event.event_title}")


@pytest.mark.asyncio
async def test_next_plan_start_date_event_creation(
    db_session,
    calendar_account_fixture,
    welfare_recipient_fixture,
    service_admin_user_factory
):
    """モニタリング期限イベントが正しく作成されることを確認

    テスト内容:
    1. モニタリング期限イベントを作成
    2. イベントの開始時刻が期限日9:00であることを確認
    3. イベントの終了時刻が期限日18:00であることを確認
    4. sync_statusがpendingになっていることを確認
    """
    # Arrange
    from app.services.calendar_service import calendar_service
    from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
    from app.models.enums import SupportPlanStep

    admin = await service_admin_user_factory(session=db_session)
    office_id = calendar_account_fixture.office_id
    due_date = date.today() + timedelta(days=7)

    # サイクルを作成
    cycle = SupportPlanCycle(
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=office_id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=180),
        is_latest_cycle=True,
        cycle_number=1
    )
    db_session.add(cycle)
    await db_session.flush()

    # モニタリングステータスを作成
    monitoring_status = SupportPlanStatus(
        plan_cycle_id=cycle.id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=office_id,
        step_type=SupportPlanStep.monitoring,
        is_latest_status=True,
        due_date=due_date
    )
    db_session.add(monitoring_status)
    await db_session.flush()
    await db_session.refresh(monitoring_status)

    # Act
    event_id = await calendar_service.create_next_plan_start_date_event(
        db=db_session,
        office_id=office_id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        status_id=monitoring_status.id,
        due_date=due_date
    )

    await db_session.flush()

    # Assert
    assert event_id is not None, "モニタリング期限イベントが作成されませんでした"

    result = await db_session.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id
        )
    )
    calendar_event = result.scalar_one()

    # 開始時刻: 期限日 9:00 (JST)
    from zoneinfo import ZoneInfo
    jst = ZoneInfo("Asia/Tokyo")
    expected_start = datetime.combine(due_date, time(9, 0), tzinfo=jst)
    # 終了時刻: 期限日 18:00 (JST)
    expected_end = datetime.combine(due_date, time(18, 0), tzinfo=jst)

    assert calendar_event.event_start_datetime == expected_start, \
        f"開始時刻が正しくありません: {calendar_event.event_start_datetime}"
    assert calendar_event.event_end_datetime == expected_end, \
        f"終了時刻が正しくありません: {calendar_event.event_end_datetime}"
    assert calendar_event.sync_status == CalendarSyncStatus.pending
    assert calendar_event.event_type == CalendarEventType.next_plan_start_date

    print(f"\n✅ モニタリング期限イベント作成成功")
    print(f"   開始: {calendar_event.event_start_datetime}")
    print(f"   終了: {calendar_event.event_end_datetime}")
    print(f"   タイトル: {calendar_event.event_title}")
