"""
SafeTestDataCleanup の is_test_data フラグベースの動作確認テスト

TDD Step 8: RED - このテストは最初は失敗する（SafeTestDataCleanupがまだ更新されていないため）
"""
import pytest
from sqlalchemy import select

from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.notice import Notice
from tests.utils.safe_cleanup import SafeTestDataCleanup


@pytest.mark.asyncio
class TestSafeTestDataCleanupWithFlag:
    """is_test_data フラグベースのクリーンアップ動作を確認"""

    async def test_delete_only_test_data(self, db_session, office_factory, staff_factory):
        """is_test_data=True のデータのみが削除されることを確認"""

        # テストデータを作成 (is_test_data=True)
        test_office = await office_factory(is_test_data=True)
        test_staff = await staff_factory(office_id=test_office.id, is_test_data=True)
        await db_session.flush()

        # 本番データを作成 (is_test_data=False)
        prod_office = await office_factory(name="本番事業所", is_test_data=False)
        prod_staff = await staff_factory(
            office_id=prod_office.id,
            email="real@production.com",
            is_test_data=False
        )
        await db_session.flush()

        # クリーンアップ実行
        result = await SafeTestDataCleanup.delete_test_data(db_session)

        # テストデータが削除されていることを確認
        test_office_exists = await db_session.execute(
            select(Office).where(Office.id == test_office.id)
        )
        assert test_office_exists.scalar_one_or_none() is None, \
            "is_test_data=True のOfficeは削除される必要があります"

        test_staff_exists = await db_session.execute(
            select(Staff).where(Staff.id == test_staff.id)
        )
        assert test_staff_exists.scalar_one_or_none() is None, \
            "is_test_data=True のStaffは削除される必要があります"

        # 本番データが残っていることを確認
        prod_office_exists = await db_session.execute(
            select(Office).where(Office.id == prod_office.id)
        )
        assert prod_office_exists.scalar_one_or_none() is not None, \
            "is_test_data=False のOfficeは残っている必要があります"

        prod_staff_exists = await db_session.execute(
            select(Staff).where(Staff.id == prod_staff.id)
        )
        assert prod_staff_exists.scalar_one_or_none() is not None, \
            "is_test_data=False のStaffは残っている必要があります"

    async def test_cleanup_with_cascade_relationships(
        self, db_session, office_factory, welfare_recipient_factory
    ):
        """CASCADE削除の関係があるデータでも正しく動作することを確認"""

        # テスト事業所と福祉受給者を作成
        test_office = await office_factory(is_test_data=True)
        test_recipient = await welfare_recipient_factory(
            office_id=test_office.id,
            is_test_data=True
        )
        await db_session.flush()

        # クリーンアップ実行
        result = await SafeTestDataCleanup.delete_test_data(db_session)

        # 両方とも削除されていることを確認
        office_exists = await db_session.execute(
            select(Office).where(Office.id == test_office.id)
        )
        assert office_exists.scalar_one_or_none() is None, \
            "is_test_data=True のOfficeは削除される必要があります"

        recipient_exists = await db_session.execute(
            select(WelfareRecipient).where(WelfareRecipient.id == test_recipient.id)
        )
        assert recipient_exists.scalar_one_or_none() is None, \
            "is_test_data=True のWelfareRecipientは削除される必要があります"

    async def test_no_production_data_deleted(self, db_session, office_factory):
        """本番データ(is_test_data=False)が削除されないことを確認"""

        # 本番データを複数作成
        prod_offices = []
        for i in range(5):
            office = await office_factory(
                name=f"本番事業所{i}",
                is_test_data=False
            )
            prod_offices.append(office)
        await db_session.flush()

        # 作成前の本番データ数を記録
        count_before = await db_session.execute(
            select(Office).where(Office.is_test_data == False)
        )
        count_before_num = len(count_before.scalars().all())

        # クリーンアップ実行
        result = await SafeTestDataCleanup.delete_test_data(db_session)

        # 本番データの数が変わっていないことを確認
        count_after = await db_session.execute(
            select(Office).where(Office.is_test_data == False)
        )
        count_after_num = len(count_after.scalars().all())

        assert count_before_num == count_after_num, \
            "is_test_data=False のデータは削除されてはいけません"

    async def test_intermediate_tables_cleaned(
        self, db_session, office_factory, staff_factory, welfare_recipient_factory
    ):
        """中間テーブル（OfficeStaff, OfficeWelfareRecipient）も削除されることを確認"""

        # テストデータを作成
        test_office = await office_factory(is_test_data=True)
        test_staff = await staff_factory(office_id=test_office.id, is_test_data=True)
        test_recipient = await welfare_recipient_factory(
            office_id=test_office.id,
            is_test_data=True
        )
        await db_session.flush()

        # 中間テーブルが作成されていることを確認
        office_staff = await db_session.execute(
            select(OfficeStaff).where(
                OfficeStaff.office_id == test_office.id,
                OfficeStaff.staff_id == test_staff.id
            )
        )
        assert office_staff.scalar_one_or_none() is not None, \
            "OfficeStaff中間テーブルが作成されている必要があります"

        office_recipient = await db_session.execute(
            select(OfficeWelfareRecipient).where(
                OfficeWelfareRecipient.office_id == test_office.id,
                OfficeWelfareRecipient.welfare_recipient_id == test_recipient.id
            )
        )
        assert office_recipient.scalar_one_or_none() is not None, \
            "OfficeWelfareRecipient中間テーブルが作成されている必要があります"

        # クリーンアップ実行
        result = await SafeTestDataCleanup.delete_test_data(db_session)

        # 中間テーブルも削除されていることを確認
        office_staff_after = await db_session.execute(
            select(OfficeStaff).where(
                OfficeStaff.office_id == test_office.id,
                OfficeStaff.staff_id == test_staff.id
            )
        )
        assert office_staff_after.scalar_one_or_none() is None, \
            "is_test_data=True のOfficeStaffは削除される必要があります"

        office_recipient_after = await db_session.execute(
            select(OfficeWelfareRecipient).where(
                OfficeWelfareRecipient.office_id == test_office.id,
                OfficeWelfareRecipient.welfare_recipient_id == test_recipient.id
            )
        )
        assert office_recipient_after.scalar_one_or_none() is None, \
            "is_test_data=True のOfficeWelfareRecipientは削除される必要があります"

    async def test_delete_test_data_returns_counts(
        self, db_session, office_factory, staff_factory
    ):
        """delete_test_data が削除されたレコード数を返すことを確認"""

        # テストデータを作成
        await office_factory(is_test_data=True)
        await office_factory(is_test_data=True)
        await db_session.flush()

        # クリーンアップ実行
        result = await SafeTestDataCleanup.delete_test_data(db_session)

        # 結果が辞書形式で返されることを確認
        assert isinstance(result, dict), "結果は辞書形式である必要があります"

        # offices が削除されたことを確認
        assert "offices" in result, "結果に'offices'キーが含まれている必要があります"
        assert result["offices"] >= 2, "少なくとも2つのOfficeが削除される必要があります"

    async def test_mixed_test_and_production_data(
        self, db_session, office_factory, staff_factory
    ):
        """テストデータと本番データが混在している場合、テストデータのみ削除されることを確認"""

        # テストデータ
        test_office1 = await office_factory(name="テスト事業所1", is_test_data=True)
        test_office2 = await office_factory(name="テスト事業所2", is_test_data=True)

        # 本番データ
        prod_office1 = await office_factory(name="本番事業所1", is_test_data=False)
        prod_office2 = await office_factory(name="本番事業所2", is_test_data=False)

        await db_session.flush()

        # クリーンアップ実行
        result = await SafeTestDataCleanup.delete_test_data(db_session)

        # テストデータが削除されていることを確認
        test_offices = await db_session.execute(
            select(Office).where(Office.is_test_data == True)
        )
        assert len(test_offices.scalars().all()) == 0, \
            "is_test_data=True のOfficeはすべて削除される必要があります"

        # 本番データが残っていることを確認
        prod_offices = await db_session.execute(
            select(Office).where(Office.is_test_data == False)
        )
        assert len(prod_offices.scalars().all()) >= 2, \
            "is_test_data=False のOfficeは残っている必要があります"
