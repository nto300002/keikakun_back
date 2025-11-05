"""
Notice (通知) CRUDのテスト
TDD方式でテストを先に作成
"""
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

from app import crud

pytestmark = pytest.mark.asyncio


async def test_create_notice(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    お知らせ作成テスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    # お知らせデータ
    notice_data = {
        "recipient_staff_id": staff.id,
        "office_id": office.id,
        "type": "calendar_event",
        "title": "更新期限が近づいています",
        "content": "山田太郎さんの個別支援計画の更新期限（2025-12-31）まで30日です。",
        "link_url": "/support-plans/123",
        "is_read": False
    }

    created_notice = await crud.notice.create(db=db_session, obj_in=notice_data)

    assert created_notice.id is not None
    assert created_notice.recipient_staff_id == staff.id
    assert created_notice.office_id == office.id
    assert created_notice.type == "calendar_event"
    assert created_notice.title == "更新期限が近づいています"
    assert created_notice.is_read is False


async def test_get_notice_by_id(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    IDでお知らせを取得するテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    notice_data = {
        "recipient_staff_id": staff.id,
        "office_id": office.id,
        "type": "system",
        "title": "システムメンテナンスのお知らせ",
        "content": "明日の午前2時からメンテナンスを実施します。",
        "is_read": False
    }

    created_notice = await crud.notice.create(db=db_session, obj_in=notice_data)

    # 取得
    retrieved_notice = await crud.notice.get(db=db_session, id=created_notice.id)

    assert retrieved_notice is not None
    assert retrieved_notice.id == created_notice.id
    assert retrieved_notice.title == "システムメンテナンスのお知らせ"


async def test_get_notices_by_staff_id(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    スタッフIDでお知らせ一覧を取得するテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    # 複数のお知らせを作成
    for i in range(3):
        notice_data = {
            "recipient_staff_id": staff.id,
            "office_id": office.id,
            "type": "calendar_event",
            "title": f"お知らせ{i}",
            "content": f"内容{i}",
            "is_read": False
        }
        await crud.notice.create(db=db_session, obj_in=notice_data)

    # スタッフIDでお知らせ一覧を取得
    notices = await crud.notice.get_by_staff_id(db=db_session, staff_id=staff.id)

    assert len(notices) == 3
    assert all(notice.recipient_staff_id == staff.id for notice in notices)


async def test_get_unread_notices(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    未読のお知らせ一覧を取得するテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    # 未読のお知らせを作成
    unread_notice_data = {
        "recipient_staff_id": staff.id,
        "office_id": office.id,
        "type": "calendar_event",
        "title": "未読お知らせ",
        "content": "未読の内容",
        "is_read": False
    }
    await crud.notice.create(db=db_session, obj_in=unread_notice_data)

    # 既読のお知らせを作成
    read_notice_data = {
        "recipient_staff_id": staff.id,
        "office_id": office.id,
        "type": "system",
        "title": "既読お知らせ",
        "content": "既読の内容",
        "is_read": True
    }
    await crud.notice.create(db=db_session, obj_in=read_notice_data)

    # 未読のお知らせのみ取得
    unread_notices = await crud.notice.get_unread_by_staff_id(
        db=db_session,
        staff_id=staff.id
    )

    assert len(unread_notices) >= 1
    assert all(notice.is_read is False for notice in unread_notices)


async def test_mark_notice_as_read(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    お知らせを既読にするテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    notice_data = {
        "recipient_staff_id": staff.id,
        "office_id": office.id,
        "type": "calendar_event",
        "title": "既読テスト",
        "content": "既読にするテスト",
        "is_read": False
    }

    created_notice = await crud.notice.create(db=db_session, obj_in=notice_data)
    assert created_notice.is_read is False

    # 既読にする
    updated_notice = await crud.notice.mark_as_read(
        db=db_session,
        notice_id=created_notice.id
    )

    assert updated_notice.is_read is True


async def test_mark_all_notices_as_read(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    スタッフの全お知らせを既読にするテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    # 複数の未読お知らせを作成
    for i in range(3):
        notice_data = {
            "recipient_staff_id": staff.id,
            "office_id": office.id,
            "type": "calendar_event",
            "title": f"未読{i}",
            "content": f"内容{i}",
            "is_read": False
        }
        await crud.notice.create(db=db_session, obj_in=notice_data)

    # 全お知らせを既読にする
    await crud.notice.mark_all_as_read(db=db_session, staff_id=staff.id)

    # 確認
    notices = await crud.notice.get_by_staff_id(db=db_session, staff_id=staff.id)
    assert all(notice.is_read is True for notice in notices)


async def test_delete_notice(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    お知らせ削除テスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    notice_data = {
        "recipient_staff_id": staff.id,
        "office_id": office.id,
        "type": "calendar_event",
        "title": "削除テスト",
        "content": "削除するお知らせ",
        "is_read": False
    }

    created_notice = await crud.notice.create(db=db_session, obj_in=notice_data)
    notice_id = created_notice.id

    # 削除
    removed_notice = await crud.notice.remove(db=db_session, id=notice_id)

    assert removed_notice is not None
    assert removed_notice.id == notice_id


async def test_get_notices_by_office_id(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    事業所IDでお知らせ一覧を取得するテスト
    """
    staff1 = await employee_user_factory()
    office = staff1.office_associations[0].office if staff1.office_associations else None

    staff2 = await employee_user_factory(office=office)

    # 各スタッフ向けにお知らせを作成
    for staff in [staff1, staff2]:
        for i in range(2):
            notice_data = {
                "recipient_staff_id": staff.id,
                "office_id": office.id,
                "type": "calendar_event",
                "title": f"お知らせ for {staff.full_name}",
                "content": f"内容{i}",
                "is_read": False
            }
            await crud.notice.create(db=db_session, obj_in=notice_data)

    # 事業所IDでお知らせ一覧を取得
    office_notices = await crud.notice.get_by_office_id(
        db=db_session,
        office_id=office.id
    )

    assert len(office_notices) >= 4
    assert all(notice.office_id == office.id for notice in office_notices)


async def test_get_notices_by_type(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    お知らせタイプでフィルタリングして取得するテスト
    """
    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    # 異なるタイプのお知らせを作成
    types = ["calendar_event", "system", "calendar_event"]
    for i, notice_type in enumerate(types):
        notice_data = {
            "recipient_staff_id": staff.id,
            "office_id": office.id,
            "type": notice_type,
            "title": f"{notice_type}お知らせ{i}",
            "content": f"内容{i}",
            "is_read": False
        }
        await crud.notice.create(db=db_session, obj_in=notice_data)

    # calendar_eventタイプのみ取得
    calendar_notices = await crud.notice.get_by_type(
        db=db_session,
        staff_id=staff.id,
        notice_type="calendar_event"
    )

    assert len(calendar_notices) >= 2
    assert all(notice.type == "calendar_event" for notice in calendar_notices)


async def test_delete_old_read_notices(
    db_session: AsyncSession,
    office_factory,
    employee_user_factory
) -> None:
    """
    古い既読お知らせを削除するテスト
    """
    from datetime import datetime, timedelta

    staff = await employee_user_factory()
    office = staff.office_associations[0].office if staff.office_associations else None

    # 古い既読お知らせを作成（手動でcreated_atを設定）
    from app.models.notice import Notice

    old_notice = Notice(
        recipient_staff_id=staff.id,
        office_id=office.id,
        type="calendar_event",
        title="古い既読お知らせ",
        content="削除対象",
        is_read=True
    )
    db_session.add(old_notice)
    await db_session.flush()

    # created_atを90日前に設定
    old_notice.created_at = datetime.now() - timedelta(days=90)
    db_session.add(old_notice)
    await db_session.flush()

    # 最近の既読お知らせを作成
    recent_notice_data = {
        "recipient_staff_id": staff.id,
        "office_id": office.id,
        "type": "calendar_event",
        "title": "最近の既読お知らせ",
        "content": "削除されない",
        "is_read": True
    }
    await crud.notice.create(db=db_session, obj_in=recent_notice_data)

    # 30日以上前の既読お知らせを削除
    deleted_count = await crud.notice.delete_old_read_notices(
        db=db_session,
        days_old=30
    )

    assert deleted_count >= 1
