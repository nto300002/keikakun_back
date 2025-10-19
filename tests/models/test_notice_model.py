import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.notice import Notice
from app.models.enums import StaffRole


class TestNoticeModel:
    """Noticeモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_notice(self, db_session: AsyncSession, employee_user_factory, office_factory):
        """Notice作成のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        notice = Notice(
            recipient_staff_id=staff.id,
            office_id=office.id,
            type="plan_deadline",
            title="計画書の期限が近づいています",
            content="山田太郎さんの個別支援計画書の期限が7日後です。",
            link_url="/plans/123",
            is_read=False
        )
        db_session.add(notice)
        await db_session.commit()
        await db_session.refresh(notice)

        assert notice.id is not None
        assert notice.recipient_staff_id == staff.id
        assert notice.office_id == office.id
        assert notice.type == "plan_deadline"
        assert notice.title == "計画書の期限が近づいています"
        assert notice.content == "山田太郎さんの個別支援計画書の期限が7日後です。"
        assert notice.link_url == "/plans/123"
        assert notice.is_read is False
        assert notice.created_at is not None
        assert notice.updated_at is not None

    @pytest.mark.asyncio
    async def test_notice_default_values(self, db_session: AsyncSession, employee_user_factory, office_factory):
        """Noticeのデフォルト値テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        notice = Notice(
            recipient_staff_id=staff.id,
            office_id=office.id,
            type="system",
            title="システム通知"
        )
        db_session.add(notice)
        await db_session.commit()
        await db_session.refresh(notice)

        # デフォルト値の確認
        assert notice.content is None
        assert notice.link_url is None
        assert notice.is_read is False

    @pytest.mark.asyncio
    async def test_notice_mark_as_read(self, db_session: AsyncSession, employee_user_factory, office_factory):
        """Notice既読化のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        notice = Notice(
            recipient_staff_id=staff.id,
            office_id=office.id,
            type="plan_deadline",
            title="テスト通知",
            is_read=False
        )
        db_session.add(notice)
        await db_session.commit()

        # 既読にマーク
        notice.is_read = True
        await db_session.commit()
        await db_session.refresh(notice)

        assert notice.is_read is True

    @pytest.mark.asyncio
    async def test_notice_foreign_key_staff(self, db_session: AsyncSession, office_factory, employee_user_factory):
        """Noticeのstaff外部キー制約テスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        # 存在しないstaff_idを指定
        fake_staff_id = uuid.uuid4()

        notice = Notice(
            recipient_staff_id=fake_staff_id,
            office_id=office.id,
            type="test",
            title="テスト"
        )

        db_session.add(notice)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_notice_foreign_key_office(self, db_session: AsyncSession, employee_user_factory):
        """NoticeのOffice外部キー制約テスト"""
        staff = await employee_user_factory(with_office=False)

        # 存在しないoffice_idを指定
        fake_office_id = uuid.uuid4()

        notice = Notice(
            recipient_staff_id=staff.id,
            office_id=fake_office_id,
            type="test",
            title="テスト"
        )

        db_session.add(notice)
        print(f"session pending: {db_session.in_transaction()}")
        # flush/commit to force the INSERT and trigger FK constraint check
        with pytest.raises(IntegrityError):
            await db_session.flush()
        # ensure no leftover transaction state
        try:
            await db_session.rollback()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_notice_relationship_with_staff(self, db_session: AsyncSession, employee_user_factory, office_factory):
        """NoticeとStaffのリレーションシップテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        notice = Notice(
            recipient_staff_id=staff.id,
            office_id=office.id,
            type="test",
            title="テスト通知"
        )
        db_session.add(notice)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(notice, ["recipient_staff"])

        assert notice.recipient_staff is not None
        assert notice.recipient_staff.id == staff.id
        assert notice.recipient_staff.email == staff.email

    @pytest.mark.asyncio
    async def test_notice_relationship_with_office(self, db_session: AsyncSession, employee_user_factory, office_factory):
        """NoticeとOfficeのリレーションシップテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        notice = Notice(
            recipient_staff_id=staff.id,
            office_id=office.id,
            type="test",
            title="テスト通知"
        )
        db_session.add(notice)
        await db_session.commit()

        # Eagerロードしてrelationshipを確認
        await db_session.refresh(notice, ["office"])

        assert notice.office is not None
        assert notice.office.id == office.id
        assert notice.office.name == office.name

    @pytest.mark.asyncio
    async def test_notice_updated_at_changes(self, db_session: AsyncSession, employee_user_factory, office_factory):
        """Notice updated_at更新のテスト"""
        staff = await employee_user_factory(with_office=False)
        office = await office_factory(creator=staff)

        notice = Notice(
            recipient_staff_id=staff.id,
            office_id=office.id,
            type="test",
            title="テスト通知"
        )
        db_session.add(notice)
        await db_session.commit()
        await db_session.refresh(notice)

        original_updated_at = notice.updated_at

        # 少し待ってから更新
        import asyncio
        await asyncio.sleep(0.01)

        notice.is_read = True
        await db_session.commit()
        await db_session.refresh(notice)

        # updated_atが更新されていることを確認
        assert notice.updated_at >= original_updated_at
