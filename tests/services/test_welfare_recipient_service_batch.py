"""
バッチクエリ機能のテスト

N+1クエリ問題を解消するためのバッチクエリメソッドをテストする
"""
import pytest
import pytest_asyncio
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.services.welfare_recipient_service import WelfareRecipientService
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle
from app.models.enums import StaffRole, OfficeType, GenderType


@pytest_asyncio.fixture
async def test_offices_with_data(db_session: AsyncSession):
    """
    テスト用に3つの事業所を作成し、それぞれにスタッフと利用者を配置

    Returns:
        dict: {
            "admin": Staff,
            "offices": [Office, Office, Office],
            "office_ids": [UUID, UUID, UUID]
        }
    """
    # 管理者作成
    admin = Staff(
        first_name="管理者",
        last_name="テスト",
        full_name="テスト 管理者",
        email="admin_batch@example.com",
        hashed_password="dummy",
        role=StaffRole.owner,
        is_test_data=True
    )
    db_session.add(admin)
    await db_session.flush()

    offices = []

    for i in range(3):
        # 事業所作成
        office = Office(
            name=f"バッチテスト事業所{i+1}",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db_session.add(office)
        await db_session.flush()
        offices.append(office)

        # 各事業所に2人のスタッフ
        for j in range(2):
            staff = Staff(
                first_name=f"スタッフ{j+1}",
                last_name=f"事業所{i+1}",
                full_name=f"事業所{i+1} スタッフ{j+1}",
                email=f"staff_batch_{i}_{j}@example.com",
                hashed_password="dummy",
                role=StaffRole.employee,
                notification_preferences={
                    "email_notification": True,
                    "system_notification": False,
                    "email_threshold_days": 30,
                    "push_threshold_days": 10
                },
                is_test_data=True
            )
            db_session.add(staff)
            await db_session.flush()

            # 事業所とスタッフの関連
            db_session.add(OfficeStaff(
                staff_id=staff.id,
                office_id=office.id,
                is_primary=(j == 0)
            ))

        # 各事業所に2人の利用者 + 更新期限アラート
        for k in range(2):
            recipient = WelfareRecipient(
                first_name=f"利用者{k+1}",
                last_name=f"事業所{i+1}",
                first_name_furigana=f"リヨウシャ{k+1}",
                last_name_furigana=f"ジギョウショ{i+1}",
                birth_day=date.today() - timedelta(days=365*30),
                gender=GenderType.male,
                is_test_data=True
            )
            db_session.add(recipient)
            await db_session.flush()

            # 事業所と利用者の関連
            db_session.add(OfficeWelfareRecipient(
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                is_test_data=True
            ))

            # 更新期限アラート（15日後）
            cycle = SupportPlanCycle(
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                next_renewal_deadline=date.today() + timedelta(days=15),
                is_latest_cycle=True,
                cycle_number=1,
                next_plan_start_date=22,
                is_test_data=True
            )
            db_session.add(cycle)

    await db_session.commit()

    return {
        "admin": admin,
        "offices": offices,
        "office_ids": [office.id for office in offices]
    }


@pytest.mark.asyncio
async def test_get_deadline_alerts_batch(
    db_session: AsyncSession,
    test_offices_with_data: dict
):
    """
    【バッチクエリテスト】複数事業所のアラートを一括取得

    検証項目:
    - 3つの事業所全てのアラートが取得できる
    - 各事業所に2人の利用者（2件のアラート）が存在する
    - データが正しい事業所IDでグループ化されている
    """
    office_ids = test_offices_with_data["office_ids"]

    # バッチでアラート取得
    alerts_by_office = await WelfareRecipientService.get_deadline_alerts_batch(
        db=db_session,
        office_ids=office_ids,
        threshold_days=30
    )

    # 検証: 3つの事業所全てのアラートが取得できる
    assert len(alerts_by_office) == 3, f"Expected 3 offices, got {len(alerts_by_office)}"

    # 検証: 各事業所に2件のアラートが存在する
    for office_id in office_ids:
        assert office_id in alerts_by_office, f"Office {office_id} not found in results"
        alerts_response = alerts_by_office[office_id]

        # 各事業所に2人の利用者 → 2件のアラート
        assert alerts_response.total >= 2, (
            f"Office {office_id}: expected >= 2 alerts, got {alerts_response.total}"
        )
        assert len(alerts_response.alerts) >= 2, (
            f"Office {office_id}: expected >= 2 alert items, got {len(alerts_response.alerts)}"
        )

        # アラートの内容確認
        for alert in alerts_response.alerts:
            assert alert.alert_type in ["renewal_deadline", "assessment_incomplete"]
            assert alert.full_name is not None
            assert alert.current_cycle_number >= 1


@pytest.mark.asyncio
async def test_get_deadline_alerts_batch_empty_offices(
    db_session: AsyncSession
):
    """
    【エッジケーステスト】事業所IDリストが空の場合

    検証項目:
    - 空の辞書が返される
    - エラーが発生しない
    """
    alerts_by_office = await WelfareRecipientService.get_deadline_alerts_batch(
        db=db_session,
        office_ids=[],
        threshold_days=30
    )

    assert alerts_by_office == {}


@pytest.mark.asyncio
async def test_get_staffs_by_offices_batch(
    db_session: AsyncSession,
    test_offices_with_data: dict
):
    """
    【バッチクエリテスト】複数事業所のスタッフを一括取得

    検証項目:
    - 3つの事業所全てのスタッフが取得できる
    - 各事業所に2人のスタッフが存在する
    - スタッフ情報が正しく取得できる
    """
    office_ids = test_offices_with_data["office_ids"]

    # バッチでスタッフ取得
    staffs_by_office = await WelfareRecipientService.get_staffs_by_offices_batch(
        db=db_session,
        office_ids=office_ids
    )

    # 検証: 3つの事業所全てのスタッフが取得できる
    assert len(staffs_by_office) == 3, f"Expected 3 offices, got {len(staffs_by_office)}"

    # 検証: 各事業所に2人のスタッフが存在する
    for office_id in office_ids:
        assert office_id in staffs_by_office, f"Office {office_id} not found in results"
        staffs = staffs_by_office[office_id]

        # 各事業所に2人のスタッフ
        assert len(staffs) == 2, (
            f"Office {office_id}: expected 2 staff, got {len(staffs)}"
        )

        # スタッフ情報の確認
        for staff in staffs:
            assert staff.email is not None
            assert staff.deleted_at is None
            assert staff.notification_preferences is not None


@pytest.mark.asyncio
async def test_get_staffs_by_offices_batch_empty_offices(
    db_session: AsyncSession
):
    """
    【エッジケーステスト】事業所IDリストが空の場合

    検証項目:
    - 空の辞書が返される
    - エラーが発生しない
    """
    staffs_by_office = await WelfareRecipientService.get_staffs_by_offices_batch(
        db=db_session,
        office_ids=[]
    )

    assert staffs_by_office == {}


@pytest.mark.asyncio
async def test_batch_query_consistency(
    db_session: AsyncSession,
    test_offices_with_data: dict
):
    """
    【整合性テスト】個別取得とバッチ取得で結果が一致するか

    検証項目:
    - バッチクエリの結果が個別クエリと同じ
    - データの整合性が保たれている
    """
    office_ids = test_offices_with_data["office_ids"]

    # バッチで取得
    alerts_batch = await WelfareRecipientService.get_deadline_alerts_batch(
        db=db_session,
        office_ids=office_ids,
        threshold_days=30
    )

    # 個別に取得して比較
    for office_id in office_ids:
        alerts_individual = await WelfareRecipientService.get_deadline_alerts(
            db=db_session,
            office_id=office_id,
            threshold_days=30,
            limit=None,
            offset=0
        )

        # 検証: 件数が一致
        assert alerts_batch[office_id].total == alerts_individual.total, (
            f"Office {office_id}: batch total {alerts_batch[office_id].total} != "
            f"individual total {alerts_individual.total}"
        )

        # 検証: アラート数が一致
        assert len(alerts_batch[office_id].alerts) == len(alerts_individual.alerts), (
            f"Office {office_id}: batch alerts {len(alerts_batch[office_id].alerts)} != "
            f"individual alerts {len(alerts_individual.alerts)}"
        )


@pytest.mark.asyncio
async def test_batch_query_filters_test_data(
    db_session: AsyncSession,
    test_offices_with_data: dict
):
    """
    【フィルタリングテスト】is_test_dataフラグが正しく機能するか

    検証項目:
    - TESTING=1の環境ではis_test_data=Trueのデータのみ取得
    """
    import os

    # TESTING=1を設定
    original_testing = os.getenv("TESTING")
    os.environ["TESTING"] = "1"

    try:
        office_ids = test_offices_with_data["office_ids"]

        # バッチでアラート取得
        alerts_by_office = await WelfareRecipientService.get_deadline_alerts_batch(
            db=db_session,
            office_ids=office_ids,
            threshold_days=30
        )

        # テストデータが取得できることを確認
        assert len(alerts_by_office) == 3

        for office_id in office_ids:
            assert alerts_by_office[office_id].total >= 2

    finally:
        # 環境変数を元に戻す
        if original_testing is None:
            os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = original_testing
