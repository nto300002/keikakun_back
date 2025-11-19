"""
Factory関数が is_test_data=True でデータを作成することを確認するテスト

TDD Step 4: RED - このテストは最初は失敗する（Factory関数がまだ更新されていないため）
"""
import pytest
from sqlalchemy import select

from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient


@pytest.mark.asyncio
class TestFactoryIsTestData:
    """Factory関数が is_test_data=True でデータを作成することを確認"""

    async def test_office_factory_creates_test_data(self, db_session, office_factory):
        """office_factory が is_test_data=True でOfficeを作成することを確認"""
        office = await office_factory()
        await db_session.flush()

        # データベースから再取得して確認
        result = await db_session.execute(
            select(Office).where(Office.id == office.id)
        )
        db_office = result.scalar_one()

        assert db_office.is_test_data is True, \
            "office_factory で作成されたデータは is_test_data=True である必要があります"

    async def test_service_admin_user_factory_creates_test_data(self, db_session, service_admin_user_factory):
        """service_admin_user_factory が is_test_data=True でStaffを作成することを確認"""
        staff = await service_admin_user_factory()
        await db_session.flush()

        result = await db_session.execute(
            select(Staff).where(Staff.id == staff.id)
        )
        db_staff = result.scalar_one()

        assert db_staff.is_test_data is True, \
            "service_admin_user_factory で作成されたデータは is_test_data=True である必要があります"

    async def test_staff_factory_creates_test_data(self, db_session, office_factory, staff_factory):
        """staff_factory が is_test_data=True でStaffを作成することを確認"""
        office = await office_factory()
        await db_session.flush()

        staff = await staff_factory(office_id=office.id)
        await db_session.flush()

        result = await db_session.execute(
            select(Staff).where(Staff.id == staff.id)
        )
        db_staff = result.scalar_one()

        assert db_staff.is_test_data is True, \
            "staff_factory で作成されたデータは is_test_data=True である必要があります"

    async def test_welfare_recipient_factory_creates_test_data(
        self, db_session, office_factory, welfare_recipient_factory
    ):
        """welfare_recipient_factory が is_test_data=True でWelfareRecipientを作成することを確認"""
        office = await office_factory()
        await db_session.flush()

        recipient = await welfare_recipient_factory(office_id=office.id)
        await db_session.flush()

        result = await db_session.execute(
            select(WelfareRecipient).where(WelfareRecipient.id == recipient.id)
        )
        db_recipient = result.scalar_one()

        assert db_recipient.is_test_data is True, \
            "welfare_recipient_factory で作成されたデータは is_test_data=True である必要があります"

    async def test_factory_with_explicit_is_test_data_false(self, db_session, office_factory):
        """明示的に is_test_data=False を指定した場合、本番データとして作成されることを確認"""
        office = await office_factory(is_test_data=False)
        await db_session.flush()

        result = await db_session.execute(
            select(Office).where(Office.id == office.id)
        )
        db_office = result.scalar_one()

        assert db_office.is_test_data is False, \
            "is_test_data=False を明示的に指定した場合、本番データとして作成される必要があります"

    async def test_office_staff_association_has_test_data_flag(
        self, db_session, office_factory, staff_factory
    ):
        """中間テーブル(OfficeStaff)も is_test_data フラグを持つことを確認"""
        office = await office_factory()
        staff = await staff_factory(office_id=office.id)
        await db_session.flush()

        # OfficeStaff中間テーブルを確認
        result = await db_session.execute(
            select(OfficeStaff).where(
                OfficeStaff.office_id == office.id,
                OfficeStaff.staff_id == staff.id
            )
        )
        office_staff = result.scalar_one()

        assert office_staff.is_test_data is True, \
            "Factory関数で作成された中間テーブルも is_test_data=True である必要があります"

    async def test_office_welfare_recipient_association_has_test_data_flag(
        self, db_session, office_factory, welfare_recipient_factory
    ):
        """中間テーブル(OfficeWelfareRecipient)も is_test_data フラグを持つことを確認"""
        office = await office_factory()
        recipient = await welfare_recipient_factory(office_id=office.id)
        await db_session.flush()

        # OfficeWelfareRecipient中間テーブルを確認
        result = await db_session.execute(
            select(OfficeWelfareRecipient).where(
                OfficeWelfareRecipient.office_id == office.id,
                OfficeWelfareRecipient.welfare_recipient_id == recipient.id
            )
        )
        office_welfare_recipient = result.scalar_one()

        assert office_welfare_recipient.is_test_data is True, \
            "Factory関数で作成された中間テーブルも is_test_data=True である必要があります"
