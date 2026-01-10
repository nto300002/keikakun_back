"""
CalendarEvent CRUDのテスト
TDD方式でテストを先に作成
"""
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date, timedelta
import pytest
from sqlalchemy.exc import IntegrityError

from app import crud
from app.models.enums import (
    CalendarEventType,
    CalendarSyncStatus,
    GenderType,
    OfficeType,
    SupportPlanStep
)
from tests.utils import load_staff_with_office

pytestmark = pytest.mark.asyncio


async def test_create_calendar_event_for_renewal_deadline(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    更新期限のカレンダーイベント作成テスト
    """
    # テスト用スタッフと事業所を作成
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    # 利用者を作成
    recipient_data = {
        "first_name": "太郎",
        "last_name": "山田",
        "first_name_furigana": "たろう",
        "last_name_furigana": "やまだ",
        "birth_day": date(1990, 1, 1),
        "gender": GenderType.male
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

    # 個別支援計画サイクルを作成（簡易版）
    from app.models.support_plan_cycle import SupportPlanCycle
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=150)
    )
    db_session.add(cycle)
    await db_session.flush()

    # カレンダーイベントを作成
    event_data = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": f"{recipient.last_name} {recipient.first_name} 更新期限",
        "event_start_datetime": datetime.combine(cycle.next_renewal_deadline, datetime.min.time()),
        "event_end_datetime": datetime.combine(cycle.next_renewal_deadline, datetime.min.time()) + timedelta(hours=1),
        "sync_status": CalendarSyncStatus.pending
    }

    # CRUDメソッドが存在することを確認（TDD: まだ実装されていない）
    calendar_event = await crud.calendar_event.create(db=db_session, obj_in=event_data)

    assert calendar_event.id is not None
    assert calendar_event.event_type == CalendarEventType.renewal_deadline
    assert calendar_event.welfare_recipient_id == recipient.id
    assert calendar_event.support_plan_cycle_id == cycle.id
    assert calendar_event.event_title == event_data["event_title"]


async def test_create_calendar_event_for_monitoring_deadline(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    モニタリング期限のカレンダーイベント作成テスト
    """
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    # 利用者を作成
    recipient_data = {
        "first_name": "花子",
        "last_name": "佐藤",
        "first_name_furigana": "はなこ",
        "last_name_furigana": "さとう",
        "birth_day": date(1985, 5, 15),
        "gender": GenderType.female
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

    # 個別支援計画サイクルとステータスを作成
    from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today()
    )
    db_session.add(cycle)
    await db_session.flush()

    status = SupportPlanStatus(
        plan_cycle_id=cycle.id,
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        step_type=SupportPlanStep.monitoring,
        due_date=date.today() + timedelta(days=30)
    )
    db_session.add(status)
    await db_session.flush()

    # カレンダーイベントを作成
    event_data = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_status_id": status.id,
        "event_type": CalendarEventType.monitoring_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": f"{recipient.last_name} {recipient.first_name} 次の個別支援計画の開始期限",
        "event_start_datetime": datetime.combine(status.due_date, datetime.min.time()),
        "event_end_datetime": datetime.combine(status.due_date, datetime.min.time()) + timedelta(hours=1),
        "sync_status": CalendarSyncStatus.pending
    }

    calendar_event = await crud.calendar_event.create(db=db_session, obj_in=event_data)

    assert calendar_event.id is not None
    assert calendar_event.event_type == CalendarEventType.monitoring_deadline
    assert calendar_event.support_plan_status_id == status.id
    assert calendar_event.support_plan_cycle_id is None


async def test_get_calendar_event_by_id(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    IDによるカレンダーイベント取得テスト
    """
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    recipient_data = {
        "first_name": "次郎",
        "last_name": "鈴木",
        "first_name_furigana": "じろう",
        "last_name_furigana": "すずき",
        "birth_day": date(1992, 3, 20),
        "gender": GenderType.male
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

    from app.models.support_plan_cycle import SupportPlanCycle
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=150)
    )
    db_session.add(cycle)
    await db_session.flush()

    event_data = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "テストイベント",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
    }

    created_event = await crud.calendar_event.create(db=db_session, obj_in=event_data)

    # 取得テスト
    retrieved_event = await crud.calendar_event.get(db=db_session, id=created_event.id)

    assert retrieved_event is not None
    assert retrieved_event.id == created_event.id
    assert retrieved_event.event_title == "テストイベント"


async def test_update_calendar_event_sync_status(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    カレンダーイベントの同期ステータス更新テスト
    """
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    recipient_data = {
        "first_name": "三郎",
        "last_name": "田中",
        "first_name_furigana": "さぶろう",
        "last_name_furigana": "たなか",
        "birth_day": date(1988, 7, 10),
        "gender": GenderType.male
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

    from app.models.support_plan_cycle import SupportPlanCycle
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=150)
    )
    db_session.add(cycle)
    await db_session.flush()

    event_data = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "更新テスト",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
        "sync_status": CalendarSyncStatus.pending
    }

    created_event = await crud.calendar_event.create(db=db_session, obj_in=event_data)

    # 同期ステータスを更新
    update_data = {
        "sync_status": CalendarSyncStatus.synced,
        "google_event_id": "google-event-123",
        "google_event_url": "https://calendar.google.com/event/123",
        "last_sync_at": datetime.now()
    }

    updated_event = await crud.calendar_event.update(
        db=db_session,
        db_obj=created_event,
        obj_in=update_data
    )

    assert updated_event.sync_status == CalendarSyncStatus.synced
    assert updated_event.google_event_id == "google-event-123"


async def test_delete_calendar_event(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    カレンダーイベント削除テスト
    """
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    recipient_data = {
        "first_name": "四郎",
        "last_name": "高橋",
        "first_name_furigana": "しろう",
        "last_name_furigana": "たかはし",
        "birth_day": date(1995, 11, 25),
        "gender": GenderType.male
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

    from app.models.support_plan_cycle import SupportPlanCycle
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=150)
    )
    db_session.add(cycle)
    await db_session.flush()

    event_data = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "削除テスト",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
    }

    created_event = await crud.calendar_event.create(db=db_session, obj_in=event_data)
    event_id = created_event.id

    # 削除
    removed_event = await crud.calendar_event.remove(db=db_session, id=event_id)

    assert removed_event is not None
    assert removed_event.id == event_id


async def test_duplicate_prevention_for_cycle_event_type(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    同じcycle_idとevent_typeの組み合わせで重複イベントを作成しようとした場合のテスト
    重複防止制約により、IntegrityErrorが発生する
    """
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    recipient_data = {
        "first_name": "五郎",
        "last_name": "伊藤",
        "first_name_furigana": "ごろう",
        "last_name_furigana": "いとう",
        "birth_day": date(1987, 2, 14),
        "gender": GenderType.male
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

    from app.models.support_plan_cycle import SupportPlanCycle
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=150)
    )
    db_session.add(cycle)
    await db_session.flush()

    # 1つ目のイベント作成
    event_data_1 = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "イベント1",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
        "sync_status": CalendarSyncStatus.pending
    }

    await crud.calendar_event.create(db=db_session, obj_in=event_data_1)

    # 同じcycle_idとevent_typeで2つ目のイベント作成を試みる
    event_data_2 = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "イベント2（重複）",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
        "sync_status": CalendarSyncStatus.pending
    }

    # 重複防止制約により IntegrityError が発生することを期待
    with pytest.raises(IntegrityError):
        await crud.calendar_event.create(db=db_session, obj_in=event_data_2)
        await db_session.flush()


async def test_exclusive_constraint_cycle_and_status(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    cycle_idとstatus_idの排他制約テスト
    両方が設定されているとIntegrityErrorが発生する
    """
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    recipient_data = {
        "first_name": "六郎",
        "last_name": "渡辺",
        "first_name_furigana": "ろくろう",
        "last_name_furigana": "わたなべ",
        "birth_day": date(1993, 9, 5),
        "gender": GenderType.male
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

    from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=150)
    )
    db_session.add(cycle)
    await db_session.flush()

    status = SupportPlanStatus(
        plan_cycle_id=cycle.id,
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        step_type=SupportPlanStep.assessment,
        due_date=date.today() + timedelta(days=30)
    )
    db_session.add(status)
    await db_session.flush()

    # cycle_idとstatus_idの両方を設定してイベント作成を試みる
    event_data = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "support_plan_status_id": status.id,  # 排他制約違反
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "排他制約テスト",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
    }

    # 排他制約により IntegrityError が発生することを期待
    with pytest.raises(IntegrityError):
        await crud.calendar_event.create(db=db_session, obj_in=event_data)
        await db_session.flush()


async def test_get_events_by_office_id(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    事業所IDでカレンダーイベント一覧を取得するテスト
    """
    staff = await employee_user_factory()
    staff = await load_staff_with_office(db_session, staff)
    office = staff.office_associations[0].office if staff.office_associations else None

    # 複数の利用者とイベントを作成
    for i in range(3):
        recipient_data = {
            "first_name": f"太郎{i}",
            "last_name": f"テスト{i}",
            "first_name_furigana": f"たろう{i}",
            "last_name_furigana": f"てすと{i}",
            "birth_day": date(1990, 1, 1),
            "gender": GenderType.male
        }
        recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)

        from app.models.support_plan_cycle import SupportPlanCycle
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=150 + i)
        )
        db_session.add(cycle)
        await db_session.flush()

        event_data = {
            "office_id": office.id,
            "welfare_recipient_id": recipient.id,
            "support_plan_cycle_id": cycle.id,
            "event_type": CalendarEventType.renewal_deadline,
            "google_calendar_id": "test-calendar@example.com",
            "event_title": f"イベント{i}",
            "event_start_datetime": datetime.now() + timedelta(days=i),
            "event_end_datetime": datetime.now() + timedelta(days=i, hours=1),
        }
        await crud.calendar_event.create(db=db_session, obj_in=event_data)

    # 事業所IDでイベント一覧を取得
    events = await crud.calendar_event.get_by_office_id(db=db_session, office_id=office.id)

    assert len(events) == 3
    assert all(event.office_id == office.id for event in events)


async def test_get_pending_sync_events(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    同期待ちのイベント一覧を取得するテスト
    """
    import logging
    logger = logging.getLogger(__name__)

    from tests.utils import load_staff_with_office

    logger.debug("=== test_get_pending_sync_events START ===")

    staff = await employee_user_factory()
    logger.debug(f"Staff created: {staff.id}")

    # リレーションシップを明示的にロード (MissingGreenletエラー回避)
    staff = await load_staff_with_office(db_session, staff)

    office = staff.office_associations[0].office if staff.office_associations else None
    logger.debug(f"Office: {office.id if office else 'None'}")

    recipient_data = {
        "first_name": "七郎",
        "last_name": "中村",
        "first_name_furigana": "ななろう",
        "last_name_furigana": "なかむら",
        "birth_day": date(1991, 4, 18),
        "gender": GenderType.male
    }
    recipient = await crud.welfare_recipient.create(db=db_session, obj_in=recipient_data)
    logger.debug(f"Recipient created: {recipient.id}")

    from app.models.support_plan_cycle import SupportPlanCycle
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today(),
        next_renewal_deadline=date.today() + timedelta(days=150)
    )
    db_session.add(cycle)
    await db_session.flush()

    # pending状態のイベントを作成
    event_data_pending = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "Pendingイベント",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
        "sync_status": CalendarSyncStatus.pending
    }
    await crud.calendar_event.create(db=db_session, obj_in=event_data_pending)

    # synced状態のイベントを作成（別のcycleを作成）
    cycle2 = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=date.today() + timedelta(days=180),
        next_renewal_deadline=date.today() + timedelta(days=330)
    )
    db_session.add(cycle2)
    await db_session.flush()

    event_data_synced = {
        "office_id": office.id,
        "welfare_recipient_id": recipient.id,
        "support_plan_cycle_id": cycle2.id,
        "event_type": CalendarEventType.renewal_deadline,
        "google_calendar_id": "test-calendar@example.com",
        "event_title": "Syncedイベント",
        "event_start_datetime": datetime.now(),
        "event_end_datetime": datetime.now() + timedelta(hours=1),
        "sync_status": CalendarSyncStatus.synced
    }
    await crud.calendar_event.create(db=db_session, obj_in=event_data_synced)
    logger.debug("Synced event created")

    # pending状態のイベントのみ取得
    logger.debug("Before get_pending_sync_events")
    pending_events = await crud.calendar_event.get_pending_sync_events(db=db_session)
    logger.debug(f"Pending events retrieved: {len(pending_events)}")

    logger.debug("Before length assertion")
    assert len(pending_events) >= 1

    logger.debug("Before sync_status check")
    for i, event in enumerate(pending_events):
        logger.debug(f"Event {i}: {event.id}, sync_status={event.sync_status}")

    logger.debug("Before all() assertion")
    assert all(event.sync_status == CalendarSyncStatus.pending for event in pending_events)
    logger.debug("=== test_get_pending_sync_events END ===")
