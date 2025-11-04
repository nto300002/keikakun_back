import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from unittest.mock import patch
from uuid import uuid4
from datetime import date, timedelta

from app.services.welfare_recipient_service import welfare_recipient_service
from app.schemas.welfare_recipient import UserRegistrationRequest
from app.db.session import AsyncSessionLocal
from app import crud
from app.models.staff import Staff
from app.models.office import Office
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep, StaffRole, OfficeType
from app.core.security import get_password_hash


pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """テスト用の非同期DBセッションを提供するフィクスチャ"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


@pytest.fixture
def full_registration_data() -> UserRegistrationRequest:
    """テスト用の完全な利用者登録データ"""
    return UserRegistrationRequest(
        basic_info={
            "firstName": "サービス", "lastName": "テスト",
            "firstNameFurigana": "さーびす", "lastNameFurigana": "てすと",
            "birthDay": date(1990, 1, 1), "gender": "male"
        },
        contact_address={
            "address": "テスト住所", "formOfResidence": "home_with_family",
            "meansOfTransportation": "public_transport", "tel": "0123456789"
        },
        emergency_contacts=[],
        disability_info={
            "disabilityOrDiseaseName": "テスト障害", "livelihoodProtection": "not_receiving"},
        disability_details=[]
    )


@pytest.fixture
async def setup_staff_and_office(db: AsyncSession) -> tuple[Staff, Office]:
    """テスト用のスタッフと事業所を作成して返すフィクスチャ（非同期）"""
    staff = Staff(
        first_name="管理者",
        last_name="テスト",
        full_name="テスト 管理者",
        email=f"test_admin_{uuid4()}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.owner,
    )
    db.add(staff)
    await db.flush()

    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=staff.id,
        last_modified_by=staff.id,
    )
    db.add(office)
    await db.flush()
    # refresh to populate mapped relationships/ids
    await db.refresh(staff)
    await db.refresh(office)
    return staff, office


class TestWelfareRecipientService:
    """welfare_recipient_service の非同期テスト"""

    async def test_create_recipient_with_details_success(
        self, db: AsyncSession, full_registration_data: UserRegistrationRequest, setup_staff_and_office
    ):
        """正常系: 利用者と関連データ、初期支援計画がすべて作成されること"""
        _, office = setup_staff_and_office

        # create_recipient_with_initial_plan は同期実装の場合 run_in_executor される等の互換処理を期待
        res = welfare_recipient_service.create_recipient_with_initial_plan(
            db=db, registration_data=full_registration_data, office_id=office.id
        )
        # create_recipient_with_initial_plan may return coroutine when service is async-compatible
        if hasattr(res, "__await__"):
            recipient_id = await res
        else:
            recipient_id = res

        # Eager loadingで関連データを取得
        stmt = select(WelfareRecipient).where(WelfareRecipient.id == recipient_id).options(
            selectinload(WelfareRecipient.detail),
            selectinload(WelfareRecipient.support_plan_cycles).selectinload(SupportPlanCycle.statuses)
        )
        result = await db.execute(stmt)
        db_recipient = result.scalars().first()

        # アサーション
        assert db_recipient is not None
        assert db_recipient.first_name == "サービス"
        assert db_recipient.detail is not None
        assert len(db_recipient.support_plan_cycles) == 1
        assert len(db_recipient.support_plan_cycles[0].statuses) > 0


class TestCreateInitialSupportPlan:
    """初期支援計画作成ロジックのテスト"""

    async def test_initial_plan_for_first_cycle(self, db: AsyncSession, setup_staff_and_office):
        """要件通り、最初のサイクルの初期ステップが正しく作成されるか"""
        staff, office = setup_staff_and_office
        recipient = WelfareRecipient(first_name="初回", last_name="テスト", birth_day=date(1999,1,1), gender="male")
        db.add(recipient)
        await db.flush()

        await welfare_recipient_service._create_initial_support_plan(db, recipient.id, office.id)


        stmt = select(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == recipient.id).options(selectinload(SupportPlanCycle.statuses))
        result = await db.execute(stmt)
        cycle = result.scalars().first()

        assert cycle is not None
        assert cycle.cycle_number == 1
        step_types = {status.step_type for status in cycle.statuses}
        assert step_types == {
            SupportPlanStep.assessment, 
            SupportPlanStep.draft_plan, 
            SupportPlanStep.staff_meeting, 
            SupportPlanStep.final_plan_signed
        }

    async def test_initial_plan_for_subsequent_cycle(self, db: AsyncSession, setup_staff_and_office):
        """要件通り、2回目以降のサイクルの初期ステップが正しく作成されるか"""
        staff, office = setup_staff_and_office
        recipient = WelfareRecipient(first_name="２回目", last_name="テスト", birth_day=date(1998,1,1), gender="female")
        db.add(recipient)
        await db.flush()

        # 既存のサイクルを１つ作成しておく
        existing_cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office.id,
            cycle_number=1,
            is_latest_cycle=False,
            plan_cycle_start_date=date.today() - timedelta(days=200)
        )
        db.add(existing_cycle)
        await db.flush()

        await welfare_recipient_service._create_initial_support_plan(db, recipient.id, office.id)

        stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == recipient.id, 
            SupportPlanCycle.is_latest_cycle == True
        ).options(selectinload(SupportPlanCycle.statuses))
        result = await db.execute(stmt)
        cycle = result.scalars().first()

        assert cycle is not None
        assert cycle.cycle_number == 2
        step_types = {status.step_type for status in cycle.statuses}
        assert step_types == {
            SupportPlanStep.monitoring, 
            SupportPlanStep.draft_plan, 
            SupportPlanStep.staff_meeting, 
            SupportPlanStep.final_plan_signed
        }


    async def test_create_recipient_rollback_on_error(
        self, db: AsyncSession, full_registration_data: UserRegistrationRequest, setup_staff_and_office
    ):
        """異常系: 処理中にエラーが発生した場合にロールバックされること"""
        _, office = setup_staff_and_office

        # patch はクラスメソッドを確実にパッチ
        with patch.object(welfare_recipient_service.__class__, "_create_initial_support_plan", side_effect=Exception("DB Error")):
            with pytest.raises(Exception, match="DB Error"):
                coro_or_res = welfare_recipient_service.create_recipient_with_details(
                    db=db, registration_data=full_registration_data, office_id=office.id
                )
                if hasattr(coro_or_res, "__await__"):
                    await coro_or_res
                else:
                    # 同期例外が発生するならそのまま呼び出す
                    _ = coro_or_res

    async def test_no_duplicate_calendar_events_on_user_registration(
        self, db: AsyncSession, full_registration_data: UserRegistrationRequest, setup_staff_and_office
    ):
        """利用者登録時にカレンダーイベントの重複が発生しないこと（idx_calendar_events_cycle_type_unique制約）"""
        from app.models.calendar_events import CalendarEvent
        from app.models.calendar_account import OfficeCalendarAccount
        from app.models.enums import CalendarConnectionStatus

        _, office = setup_staff_and_office

        # カレンダーアカウントを作成（イベント作成に必要）
        # ユニーク制約違反を避けるため、テストごとにユニークなカレンダーIDを生成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        calendar_account = OfficeCalendarAccount(
            office_id=office.id,
            google_calendar_id=unique_calendar_id,
            calendar_name="テストカレンダー",
            service_account_email="test@serviceaccount.com",
            service_account_key="fake_encrypted_key_data",
            connection_status=CalendarConnectionStatus.connected
        )
        db.add(calendar_account)
        await db.flush()

        # 利用者を作成
        coro_or_res = welfare_recipient_service.create_recipient_with_initial_plan(
            db=db, registration_data=full_registration_data, office_id=office.id
        )
        if hasattr(coro_or_res, "__await__"):
            recipient_id = await coro_or_res
        else:
            recipient_id = coro_or_res

        await db.commit()

        # 作成されたカレンダーイベントを確認
        stmt = select(CalendarEvent).where(CalendarEvent.welfare_recipient_id == recipient_id)
        result = await db.execute(stmt)
        events = result.scalars().all()

        # イベントが作成されていることを確認
        assert len(events) > 0, "カレンダーイベントが作成されていません"

        # cycle_id + event_type の組み合わせで重複がないことを確認
        event_keys = [(event.support_plan_cycle_id, event.event_type) for event in events]
        assert len(event_keys) == len(set(event_keys)), "カレンダーイベントに重複があります"

    async def test_no_missing_greenlet_error_on_user_registration(
        self, db: AsyncSession, full_registration_data: UserRegistrationRequest, setup_staff_and_office
    ):
        """利用者登録時にMissingGreenletエラーが発生しないこと"""
        from app.models.calendar_account import OfficeCalendarAccount
        from app.models.enums import CalendarConnectionStatus

        _, office = setup_staff_and_office

        # カレンダーアカウントを作成
        # ユニーク制約違反を避けるため、テストごとにユニークなカレンダーIDを生成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        calendar_account = OfficeCalendarAccount(
            office_id=office.id,
            google_calendar_id=unique_calendar_id,
            calendar_name="テストカレンダー",
            service_account_email="test@serviceaccount.com",
            service_account_key="fake_encrypted_key_data",
            connection_status=CalendarConnectionStatus.connected
        )
        db.add(calendar_account)
        await db.flush()

        # MissingGreenletエラーが発生しないことを確認
        try:
            coro_or_res = welfare_recipient_service.create_recipient_with_initial_plan(
                db=db, registration_data=full_registration_data, office_id=office.id
            )
            if hasattr(coro_or_res, "__await__"):
                recipient_id = await coro_or_res
            else:
                recipient_id = coro_or_res

            await db.commit()
            assert recipient_id is not None
        except Exception as e:
            # MissingGreenletエラーが発生した場合はテスト失敗
            assert "greenlet" not in str(e).lower(), f"MissingGreenletエラーが発生しました: {e}"
            raise


@pytest.mark.asyncio
async def test_delete_recipient_also_deletes_calendar_events(db: AsyncSession):
    """【統合テスト】利用者削除時、関連するカレンダーイベントがGoogle Calendarからも削除されること"""
    from app.models.calendar_events import CalendarEvent
    from app.models.enums import CalendarEventType, CalendarConnectionStatus, CalendarSyncStatus, GenderType
    from app.services.calendar_service import calendar_service
    from unittest.mock import patch, MagicMock, AsyncMock
    import json

    # スタッフと事業所を作成
    staff = Staff(
        first_name="管理者",
        last_name="テスト",
        full_name="テスト 管理者",
        email=f"test_{uuid4()}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.owner
    )
    db.add(staff)
    await db.flush()

    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=staff.id,
        last_modified_by=staff.id
    )
    db.add(office)
    await db.flush()

    # カレンダーアカウントを作成
    valid_sa_json = json.dumps({
        "type": "service_account",
        "project_id": "test",
        "private_key_id": "test-key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
        "client_email": "test@test.iam.gserviceaccount.com",
        "client_id": "123456"
    })
    from app.schemas.calendar_account import CalendarSetupRequest
    setup_req = CalendarSetupRequest(
        office_id=office.id,
        google_calendar_id=f"test-{uuid4().hex[:8]}@group.calendar.google.com",
        service_account_json=valid_sa_json,
        calendar_name="テストカレンダー"
    )
    account = await calendar_service.setup_office_calendar(db=db, request=setup_req)
    await calendar_service.update_connection_status(
        db=db,
        account_id=account.id,
        status=CalendarConnectionStatus.connected
    )

    # 利用者を作成
    recipient = WelfareRecipient(
        first_name="太郎",
        last_name="削除テスト",
        first_name_furigana="たろう",
        last_name_furigana="さくじょてすと",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male
    )
    db.add(recipient)
    await db.flush()

    # 事業所との紐付け
    from app.models.welfare_recipient import OfficeWelfareRecipient
    association = OfficeWelfareRecipient(
        office_id=office.id,
        welfare_recipient_id=recipient.id
    )
    db.add(association)
    await db.flush()

    # サイクルを作成
    cycle_start = date.today()
    cycle = SupportPlanCycle(
        welfare_recipient_id=recipient.id,
        office_id=office.id,
        plan_cycle_start_date=cycle_start,
        next_renewal_deadline=cycle_start + timedelta(days=180),
        cycle_number=2,
        is_latest_cycle=True
    )
    db.add(cycle)
    await db.flush()

    # monitoringステータスを作成
    status = SupportPlanStatus(
        welfare_recipient_id=recipient.id,
        plan_cycle_id=cycle.id,
        office_id=office.id,
        step_type=SupportPlanStep.monitoring,
        completed=False,
        is_latest_status=True
    )
    db.add(status)
    await db.flush()

    # カレンダーイベントを作成（更新期限とモニタリング期限）
    renewal_event_ids = await calendar_service.create_renewal_deadline_events(
        db=db,
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        cycle_id=cycle.id,
        next_renewal_deadline=cycle.next_renewal_deadline
    )
    assert len(renewal_event_ids) == 1

    monitoring_event_ids = await calendar_service.create_monitoring_deadline_events(
        db=db,
        office_id=office.id,
        welfare_recipient_id=recipient.id,
        cycle_id=cycle.id,
        cycle_start_date=cycle_start,
        cycle_number=cycle.cycle_number,
        status_id=status.id
    )
    assert len(monitoring_event_ids) == 1

    # Google event IDを設定（Google Calendar同期済みとして扱う）
    renewal_event = await db.get(CalendarEvent, renewal_event_ids[0])
    renewal_event.google_event_id = f"google_event_{uuid4().hex[:8]}"

    monitoring_event = await db.get(CalendarEvent, monitoring_event_ids[0])
    monitoring_event.google_event_id = f"google_event_{uuid4().hex[:8]}"

    await db.flush()

    # MissingGreenletエラーを防ぐため、commit前にrecipient_idを変数に保存
    recipient_id = recipient.id

    await db.commit()

    # イベントが存在することを確認
    events = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.welfare_recipient_id == recipient_id
        )
    )
    events_list = events.scalars().all()
    assert len(events_list) == 2

    # Google Calendar APIのモック
    with patch('app.services.google_calendar_client.GoogleCalendarClient') as mock_client_class:
        mock_instance = MagicMock()
        mock_instance.delete_event = AsyncMock()
        mock_client_class.return_value = mock_instance

        # 利用者削除
        deleted = await welfare_recipient_service.delete_recipient(
            db=db,
            recipient_id=recipient_id
        )

        assert deleted is True

        # Google Calendar APIのdelete_eventが2回呼ばれたことを確認
        assert mock_instance.delete_event.call_count == 2

    # DBからイベントが削除されたことを確認（CASCADE）
    events_after = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.welfare_recipient_id == recipient_id
        )
    )
    assert len(events_after.scalars().all()) == 0

    # 利用者も削除されたことを確認
    recipient_after = await db.get(WelfareRecipient, recipient_id)
    assert recipient_after is None
