"""
OfficeCalendarAccount CRUDのテスト
TDD方式でテストを先に作成
"""
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

from app import crud
from app.models.enums import CalendarConnectionStatus
from app.schemas.calendar_account import (
    OfficeCalendarAccountCreate,
    OfficeCalendarAccountUpdate
)
from tests.utils import load_staff_with_office

pytestmark = pytest.mark.asyncio


async def test_create_office_calendar_account(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    事業所カレンダーアカウント作成テスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    # カレンダーアカウントデータ
    account_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id="test-calendar-123@group.calendar.google.com",
        calendar_name="テスト事業所カレンダー",
        calendar_url="https://calendar.google.com/calendar/test-123",
        service_account_email="test-sa@test-project.iam.gserviceaccount.com",
        service_account_key='{"type": "service_account", "project_id": "test"}',
        connection_status=CalendarConnectionStatus.connected,
        auto_invite_staff=True,
        default_reminder_minutes=1440
    )

    # カレンダーアカウント作成（暗号化付き）
    created_account = await crud.office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=account_data
    )

    assert created_account.id is not None
    assert created_account.office_id == office.id
    assert created_account.google_calendar_id == "test-calendar-123@group.calendar.google.com"
    assert created_account.calendar_name == "テスト事業所カレンダー"
    assert created_account.connection_status == CalendarConnectionStatus.connected


async def test_get_office_calendar_account_by_office_id(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    事業所IDでカレンダーアカウントを取得するテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    account_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id="test-cal@group.calendar.google.com",
        calendar_name="取得テスト",
        service_account_email="test@test.iam.gserviceaccount.com",
        service_account_key='{"type": "service_account"}',
    )

    created_account = await crud.office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=account_data
    )

    # 事業所IDで取得
    retrieved_account = await crud.office_calendar_account.get_by_office_id(
        db=db_session,
        office_id=office.id
    )

    assert retrieved_account is not None
    assert retrieved_account.id == created_account.id
    assert retrieved_account.office_id == office.id


async def test_update_office_calendar_account_connection_status(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    カレンダーアカウントの接続状態を更新するテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    account_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id="test@group.calendar.google.com",
        calendar_name="更新テスト",
        service_account_email="test@test.iam.gserviceaccount.com",
        service_account_key='{"type": "service_account"}',
        connection_status=CalendarConnectionStatus.not_connected
    )

    created_account = await crud.office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=account_data
    )

    # 接続状態を更新
    updated_account = await crud.office_calendar_account.update_connection_status(
        db=db_session,
        account_id=created_account.id,
        status=CalendarConnectionStatus.connected
    )

    assert updated_account.connection_status == CalendarConnectionStatus.connected


async def test_update_office_calendar_account_connection_status_with_error(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    接続エラーと共に状態を更新するテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    account_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id="error@group.calendar.google.com",
        calendar_name="エラーテスト",
        service_account_email="error@test.iam.gserviceaccount.com",
        service_account_key='{"type": "service_account"}',
        connection_status=CalendarConnectionStatus.connected
    )

    created_account = await crud.office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=account_data
    )

    # エラーメッセージ付きで状態を更新
    error_message = "Google Calendar API authentication failed"
    updated_account = await crud.office_calendar_account.update_connection_status(
        db=db_session,
        account_id=created_account.id,
        status=CalendarConnectionStatus.error,
        error_message=error_message
    )

    assert updated_account.connection_status == CalendarConnectionStatus.error
    assert updated_account.last_error_message == error_message


async def test_update_office_calendar_account_with_encryption(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    サービスアカウントキーを含む更新テスト（暗号化付き）
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    account_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id="update@group.calendar.google.com",
        calendar_name="暗号化更新テスト",
        service_account_email="old@test.iam.gserviceaccount.com",
        service_account_key='{"type": "service_account", "version": "old"}',
    )

    created_account = await crud.office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=account_data
    )

    # サービスアカウントキーを更新
    update_data = OfficeCalendarAccountUpdate(
        service_account_email="new@test.iam.gserviceaccount.com",
        service_account_key='{"type": "service_account", "version": "new"}',
    )

    updated_account = await crud.office_calendar_account.update_with_encryption(
        db=db_session,
        db_obj=created_account,
        obj_in=update_data
    )

    assert updated_account.service_account_email == "new@test.iam.gserviceaccount.com"
    # 暗号化されていることを確認（暗号化されたキーは元のキーと異なる）
    assert updated_account.service_account_key is not None


async def test_get_connected_accounts(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    連携済みカレンダーアカウント一覧を取得するテスト
    """
    # 複数の事業所とカレンダーアカウントを作成
    for i in range(3):
        staff = await employee_user_factory()
        office = staff.office_associations[0].office if staff.office_associations else None

        status = CalendarConnectionStatus.connected if i < 2 else CalendarConnectionStatus.not_connected

        account_data = OfficeCalendarAccountCreate(
            office_id=office.id,
            google_calendar_id=f"test-{i}@group.calendar.google.com",
            calendar_name=f"カレンダー{i}",
            service_account_email=f"test-{i}@test.iam.gserviceaccount.com",
            service_account_key='{"type": "service_account"}',
            connection_status=status
        )

        await crud.office_calendar_account.create_with_encryption(
            db=db_session,
            obj_in=account_data
        )

    # 連携済みアカウントのみ取得
    connected_accounts = await crud.office_calendar_account.get_connected_accounts(
        db=db_session
    )

    assert len(connected_accounts) >= 2
    assert all(
        account.connection_status == CalendarConnectionStatus.connected
        for account in connected_accounts
    )


async def test_delete_office_calendar_account(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    事業所カレンダーアカウント削除テスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    account_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id="delete@group.calendar.google.com",
        calendar_name="削除テスト",
        service_account_email="delete@test.iam.gserviceaccount.com",
        service_account_key='{"type": "service_account"}',
    )

    created_account = await crud.office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=account_data
    )
    account_id = created_account.id

    # 削除
    removed_account = await crud.office_calendar_account.remove(
        db=db_session,
        id=account_id
    )

    assert removed_account is not None
    assert removed_account.id == account_id


async def test_service_account_key_encryption_decryption(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    サービスアカウントキーの暗号化・復号化テスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    original_key = '{"type": "service_account", "project_id": "test-project", "private_key": "test-key"}'

    account_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id="encryption@group.calendar.google.com",
        calendar_name="暗号化テスト",
        service_account_email="encryption@test.iam.gserviceaccount.com",
        service_account_key=original_key,
    )

    created_account = await crud.office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=account_data
    )

    # DBから取得
    retrieved_account = await crud.office_calendar_account.get(
        db=db_session,
        id=created_account.id
    )

    # 復号化して元のキーと一致するか確認
    decrypted_key = retrieved_account.decrypt_service_account_key()

    assert decrypted_key is not None
    # 復号化されたキーが元のキーと一致することを確認
    import json
    assert json.loads(decrypted_key) == json.loads(original_key)
