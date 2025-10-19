"""イベント重複防止テスト（統合テスト）

Phase 1-3: 同じサイクル・ステータスで重複するカレンダーイベントが作成されないことを確認

このテストは以下を検証します:
- 同じcycle_id + event_typeで重複イベントが作成されない
- 同じstatus_id + event_typeで重複イベントが作成されない
- DBに1つだけイベントが保存されることを確認

実行コマンド:
pytest tests/integration/test_calendar_event_duplicate_prevention.py -v -s --tb=short
"""

import pytest
from datetime import date, timedelta
from sqlalchemy import select, func

from app.models.calendar_events import CalendarEvent
from app.models.enums import CalendarEventType
from app.services.calendar_service import calendar_service


@pytest.mark.asyncio
async def test_duplicate_renewal_deadline_event_prevented(
    db_session,
    welfare_recipient_fixture,
    calendar_account_fixture
):
    """同じcycle_idで重複する更新期限イベントが作成されないことを確認

    テスト内容:
    1. 同じcycle_idで2回イベント作成を試みる
    2. 1回目はイベントIDが返される
    3. 2回目はNoneが返される（重複防止）
    4. DBに1つだけイベントが存在することを確認
    """
    # Arrange - サイクルを作成
    from app.models.support_plan_cycle import SupportPlanCycle

    next_renewal_deadline = date.today() + timedelta(days=180)

    cycle = SupportPlanCycle(
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=welfare_recipient_fixture.office_id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=next_renewal_deadline,
        is_latest_cycle=True,
        cycle_number=1
    )
    db_session.add(cycle)
    await db_session.flush()
    await db_session.refresh(cycle)

    # Act - 同じcycle_idで2回イベント作成を試みる
    event_ids_1 = await calendar_service.create_renewal_deadline_events(
        db=db_session,
        office_id=welfare_recipient_fixture.office_id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        cycle_id=cycle.id,
        next_renewal_deadline=next_renewal_deadline
    )

    await db_session.flush()

    event_ids_2 = await calendar_service.create_renewal_deadline_events(
        db=db_session,
        office_id=welfare_recipient_fixture.office_id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        cycle_id=cycle.id,  # 同じcycle_id
        next_renewal_deadline=next_renewal_deadline
    )

    await db_session.flush()

    # Assert - 2回目は空リストが返される（重複防止）
    assert event_ids_1 is not None and len(event_ids_1) == 1, "1回目のイベント作成が失敗しました"
    assert event_ids_2 == [], "2回目のイベント作成が重複して実行されました（空リストが返されるべき）"

    # DBに1つだけ存在することを確認
    result = await db_session.execute(
        select(func.count()).select_from(CalendarEvent).where(
            CalendarEvent.support_plan_cycle_id == cycle.id,
            CalendarEvent.event_type == CalendarEventType.renewal_deadline
        )
    )
    count = result.scalar()
    assert count == 1, f"DBに重複イベントが保存されています（件数: {count}）"

    print(f"\n✅ 更新期限イベントの重複防止成功")
    print(f"   1回目イベントID: {event_ids_1}")
    print(f"   2回目イベントID: {event_ids_2} (空リスト)")
    print(f"   DBのイベント数: {count}")


@pytest.mark.asyncio
async def test_duplicate_monitoring_deadline_event_prevented(
    db_session,
    welfare_recipient_fixture,
    calendar_account_fixture
):
    """同じstatus_idで重複するモニタリング期限イベントが作成されないことを確認

    テスト内容:
    1. 同じstatus_idで2回イベント作成を試みる
    2. 1回目はイベントIDが返される
    3. 2回目はNoneが返される（重複防止）
    4. DBに1つだけイベントが存在することを確認
    """
    # Arrange - サイクルとステータスを作成
    from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
    from app.models.enums import SupportPlanStep

    due_date = date.today() + timedelta(days=7)

    # サイクルを作成
    cycle = SupportPlanCycle(
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=welfare_recipient_fixture.office_id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=180),
        is_latest_cycle=True,
        cycle_number=1
    )
    db_session.add(cycle)
    await db_session.flush()

    # モニタリングステータスを作成
    status = SupportPlanStatus(
        plan_cycle_id=cycle.id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=welfare_recipient_fixture.office_id,
        step_type=SupportPlanStep.monitoring,
        is_latest_status=True,
        due_date=due_date
    )
    db_session.add(status)
    await db_session.flush()
    await db_session.refresh(status)

    # Act - 同じstatus_idで2回イベント作成を試みる
    event_id_1 = await calendar_service.create_monitoring_deadline_event(
        db=db_session,
        office_id=welfare_recipient_fixture.office_id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        status_id=status.id,
        due_date=due_date
    )

    await db_session.flush()

    event_id_2 = await calendar_service.create_monitoring_deadline_event(
        db=db_session,
        office_id=welfare_recipient_fixture.office_id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        status_id=status.id,  # 同じstatus_id
        due_date=due_date
    )

    await db_session.flush()

    # Assert - 2回目はNoneが返される（重複防止）
    assert event_id_1 is not None, "1回目のイベント作成が失敗しました"
    assert event_id_2 is None, "2回目のイベント作成が重複して実行されました（Noneが返されるべき）"

    # DBに1つだけ存在することを確認
    result = await db_session.execute(
        select(func.count()).select_from(CalendarEvent).where(
            CalendarEvent.support_plan_status_id == status.id,
            CalendarEvent.event_type == CalendarEventType.monitoring_deadline
        )
    )
    count = result.scalar()
    assert count == 1, f"DBに重複イベントが保存されています（件数: {count}）"

    print(f"\n✅ モニタリング期限イベントの重複防止成功")
    print(f"   1回目イベントID: {event_id_1}")
    print(f"   2回目イベントID: {event_id_2} (None)")
    print(f"   DBのイベント数: {count}")


@pytest.mark.asyncio
async def test_different_cycle_allows_multiple_events(
    db_session,
    welfare_recipient_fixture,
    calendar_account_fixture
):
    """異なるcycle_idの場合は複数のイベントが作成できることを確認

    テスト内容:
    1. cycle_id=1でイベントを作成
    2. cycle_id=2でイベントを作成
    3. 両方ともイベントIDが返される
    4. DBに2つのイベントが存在することを確認
    """
    # Arrange - 2つのサイクルを作成
    from app.models.support_plan_cycle import SupportPlanCycle

    next_renewal_deadline_1 = date.today() + timedelta(days=180)
    next_renewal_deadline_2 = date.today() + timedelta(days=360)

    # サイクル1を作成
    cycle_1 = SupportPlanCycle(
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=welfare_recipient_fixture.office_id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=next_renewal_deadline_1,
        is_latest_cycle=False,
        cycle_number=1
    )
    db_session.add(cycle_1)
    await db_session.flush()
    await db_session.refresh(cycle_1)

    # サイクル2を作成
    cycle_2 = SupportPlanCycle(
        welfare_recipient_id=welfare_recipient_fixture.id,
        office_id=welfare_recipient_fixture.office_id,
        plan_cycle_start_date=date.today() + timedelta(days=180),
        next_renewal_deadline=next_renewal_deadline_2,
        is_latest_cycle=True,
        cycle_number=2
    )
    db_session.add(cycle_2)
    await db_session.flush()
    await db_session.refresh(cycle_2)

    # Act - 異なるcycle_idで2回イベント作成
    event_ids_1 = await calendar_service.create_renewal_deadline_events(
        db=db_session,
        office_id=welfare_recipient_fixture.office_id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        cycle_id=cycle_1.id,
        next_renewal_deadline=next_renewal_deadline_1
    )

    await db_session.flush()

    event_ids_2 = await calendar_service.create_renewal_deadline_events(
        db=db_session,
        office_id=welfare_recipient_fixture.office_id,
        welfare_recipient_id=welfare_recipient_fixture.id,
        cycle_id=cycle_2.id,  # 異なるcycle_id
        next_renewal_deadline=next_renewal_deadline_2
    )

    await db_session.flush()

    # Assert - 両方ともイベントが作成される
    assert event_ids_1 is not None and len(event_ids_1) == 1, "1回目のイベント作成が失敗しました"
    assert event_ids_2 is not None and len(event_ids_2) == 1, "2回目のイベント作成が失敗しました"

    # DBに2つ存在することを確認
    result = await db_session.execute(
        select(func.count()).select_from(CalendarEvent).where(
            CalendarEvent.welfare_recipient_id == welfare_recipient_fixture.id,
            CalendarEvent.event_type == CalendarEventType.renewal_deadline
        )
    )
    count = result.scalar()
    assert count == 2, f"DBのイベント数が正しくありません（件数: {count}, 期待: 2）"

    print(f"\n✅ 異なるcycle_idで複数イベント作成成功")
    print(f"   cycle_id={cycle_1.id} イベントID: {event_ids_1}")
    print(f"   cycle_id={cycle_2.id} イベントID: {event_ids_2}")
    print(f"   DBのイベント数: {count}")
