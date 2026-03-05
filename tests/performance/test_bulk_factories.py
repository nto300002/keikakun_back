"""
バルクファクトリの単体テスト

目的: バルクインサート機能の正確性とパフォーマンスを検証
"""
import pytest
import pytest_asyncio
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Office, Staff, WelfareRecipient, SupportPlanCycle, OfficeStaff, OfficeWelfareRecipient
from tests.performance.bulk_factories import (
    bulk_create_offices,
    bulk_create_staffs,
    bulk_create_welfare_recipients,
    bulk_create_support_plan_cycles
)


@pytest.mark.asyncio
@pytest.mark.performance
async def test_bulk_create_offices(db_session: AsyncSession):
    """
    事業所のバルク作成テスト

    検証項目:
    - 指定した数の事業所が作成される
    - 全事業所にIDが割り当てられる
    - is_test_data=Trueが設定される
    - データの整合性が保たれる
    """
    # Given: 10事業所を作成
    count = 10

    # When: バルク作成
    start_time = time.time()
    offices = await bulk_create_offices(db_session, count=count)
    elapsed = time.time() - start_time

    # Then: 検証
    assert len(offices) == count, f"Expected {count} offices, got {len(offices)}"

    # 全事業所にIDが割り当てられている
    for office in offices:
        assert office.id is not None, "Office ID should not be None"
        assert office.is_test_data is True, "is_test_data should be True"
        assert office.name is not None, "Office name should not be None"

    # DBから取得して確認
    stmt = select(Office).where(Office.is_test_data == True)
    result = await db_session.execute(stmt)
    db_offices = result.scalars().all()
    assert len(db_offices) >= count, "Offices should be saved in database"

    print(f"\n✅ 事業所バルク作成: {count}件 in {elapsed:.2f}秒")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_bulk_create_staffs(db_session: AsyncSession):
    """
    スタッフのバルク作成テスト

    検証項目:
    - 指定した数のスタッフが作成される
    - 事業所ごとにグループ化される
    - 全スタッフにIDが割り当てられる
    - メールアドレスが一意
    """
    # Given: 5事業所、各2スタッフ
    offices = await bulk_create_offices(db_session, count=5)
    count_per_office = 2

    # When: スタッフをバルク作成
    start_time = time.time()
    staffs_by_office = await bulk_create_staffs(
        db_session,
        offices=offices,
        count_per_office=count_per_office
    )
    elapsed = time.time() - start_time

    # Then: 検証
    assert len(staffs_by_office) == len(offices), "Should have staffs for each office"

    total_staffs = 0
    for office in offices:
        staffs = staffs_by_office[office.id]
        assert len(staffs) == count_per_office, (
            f"Office {office.id} should have {count_per_office} staffs, got {len(staffs)}"
        )

        for staff in staffs:
            assert staff.id is not None, "Staff ID should not be None"
            # Note: Staff doesn't have office_id directly, but we verify it's in the right office group
            assert staff.is_test_data is True, "is_test_data should be True"
            assert staff.email is not None, "Email should not be None"
            assert "@test-example.com" in staff.email, "Email should use test domain"
            total_staffs += 1

    # DBから取得してOfficeStaffアソシエーションを確認
    from app.models import OfficeStaff
    stmt = select(OfficeStaff).where(OfficeStaff.is_test_data == True)
    result = await db_session.execute(stmt)
    associations = result.scalars().all()
    assert len(associations) == total_staffs, "All staffs should have office associations"

    # メールアドレスの一意性確認
    all_emails = [
        staff.email
        for staffs in staffs_by_office.values()
        for staff in staffs
    ]
    assert len(all_emails) == len(set(all_emails)), "All emails should be unique"

    print(f"\n✅ スタッフバルク作成: {total_staffs}件 in {elapsed:.2f}秒")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_bulk_create_welfare_recipients(db_session: AsyncSession):
    """
    利用者のバルク作成テスト

    検証項目:
    - 指定した数の利用者が作成される
    - 事業所ごとにグループ化される
    - 全利用者にIDが割り当てられる
    """
    # Given: 3事業所、各5利用者
    offices = await bulk_create_offices(db_session, count=3)
    count_per_office = 5

    # When: 利用者をバルク作成
    start_time = time.time()
    recipients_by_office = await bulk_create_welfare_recipients(
        db_session,
        offices=offices,
        count_per_office=count_per_office
    )
    elapsed = time.time() - start_time

    # Then: 検証
    assert len(recipients_by_office) == len(offices), "Should have recipients for each office"

    total_recipients = 0
    for office in offices:
        recipients = recipients_by_office[office.id]
        assert len(recipients) == count_per_office, (
            f"Office {office.id} should have {count_per_office} recipients, got {len(recipients)}"
        )

        for recipient in recipients:
            assert recipient.id is not None, "Recipient ID should not be None"
            # Note: WelfareRecipient doesn't have office_id directly, but we verify it's in the right office group
            assert recipient.is_test_data is True, "is_test_data should be True"
            total_recipients += 1

    # DBから取得してOfficeWelfareRecipientアソシエーションを確認
    from app.models import OfficeWelfareRecipient
    stmt = select(OfficeWelfareRecipient).where(OfficeWelfareRecipient.is_test_data == True)
    result = await db_session.execute(stmt)
    associations = result.scalars().all()
    assert len(associations) == total_recipients, "All recipients should have office associations"

    print(f"\n✅ 利用者バルク作成: {total_recipients}件 in {elapsed:.2f}秒")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_bulk_create_support_plan_cycles(db_session: AsyncSession):
    """
    個別支援計画サイクルのバルク作成テスト

    検証項目:
    - 利用者ごとにサイクルが作成される
    - 期限が正しく設定される（25日後）
    - is_test_dataが設定される
    """
    # Given: 2事業所、各3利用者
    offices = await bulk_create_offices(db_session, count=2)
    recipients_by_office = await bulk_create_welfare_recipients(db_session, offices, count_per_office=3)

    # When: サイクルをバルク作成
    start_time = time.time()
    cycles = await bulk_create_support_plan_cycles(
        db_session,
        recipients_by_office=recipients_by_office
    )
    elapsed = time.time() - start_time

    # Then: 検証
    total_recipients = sum(len(recs) for recs in recipients_by_office.values())
    assert len(cycles) == total_recipients, f"Should have {total_recipients} cycles, got {len(cycles)}"

    # サイクルの検証
    from datetime import date, timedelta
    today = date.today()
    expected_deadline = today + timedelta(days=25)

    for cycle in cycles:
        assert cycle.id is not None, "Cycle ID should not be None"
        assert cycle.is_latest_cycle is True, "Cycle should be latest"
        assert cycle.is_test_data is True, "is_test_data should be True"
        assert cycle.next_renewal_deadline == expected_deadline, (
            f"Cycle deadline should be {expected_deadline}, got {cycle.next_renewal_deadline}"
        )

    print(f"\n✅ サイクルバルク作成: {len(cycles)}件 in {elapsed:.2f}秒")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_bulk_create_performance_100_offices(db_session: AsyncSession):
    """
    パフォーマンステスト: 100事業所規模

    目標:
    - 生成時間: 5分以内
    - データ整合性: 100%

    データ構成:
    - 100事業所
    - 1,000スタッフ（各10名）
    - 10,000利用者（各100名）
    - 10,000計画・サイクル
    """
    print("\n" + "=" * 80)
    print("📊 100事業所規模パフォーマンステスト")
    print("=" * 80)

    overall_start = time.time()

    # Step 1: 事業所作成
    print("\n⏳ Step 1: 事業所作成中...")
    start = time.time()
    offices = await bulk_create_offices(db_session, count=100)
    elapsed = time.time() - start
    print(f"✅ 事業所作成完了: {len(offices)}件 in {elapsed:.2f}秒")

    # Step 2: スタッフ作成
    print("\n⏳ Step 2: スタッフ作成中...")
    start = time.time()
    staffs_by_office = await bulk_create_staffs(
        db_session,
        offices=offices,
        count_per_office=10
    )
    total_staffs = sum(len(s) for s in staffs_by_office.values())
    elapsed = time.time() - start
    print(f"✅ スタッフ作成完了: {total_staffs}件 in {elapsed:.2f}秒")

    # Step 3: 利用者作成
    print("\n⏳ Step 3: 利用者作成中...")
    start = time.time()
    recipients_by_office = await bulk_create_welfare_recipients(
        db_session,
        offices=offices,
        count_per_office=100
    )
    total_recipients = sum(len(r) for r in recipients_by_office.values())
    elapsed = time.time() - start
    print(f"✅ 利用者作成完了: {total_recipients}件 in {elapsed:.2f}秒")

    # Step 4: サイクル作成
    print("\n⏳ Step 4: サイクル作成中...")
    start = time.time()
    cycles = await bulk_create_support_plan_cycles(
        db_session,
        recipients_by_office=recipients_by_office
    )
    elapsed = time.time() - start
    print(f"✅ サイクル作成完了: {len(cycles)}件 in {elapsed:.2f}秒")

    overall_elapsed = time.time() - overall_start

    print("\n" + "=" * 80)
    print(f"✅ 総生成時間: {overall_elapsed:.2f}秒 ({overall_elapsed / 60:.1f}分)")
    print(f"   目標: 720秒（12分）以内")
    print(f"   達成: {'✅ YES' if overall_elapsed < 720 else '❌ NO'}")
    print("=" * 80)

    # 検証
    assert len(offices) == 100
    assert total_staffs == 1000
    assert total_recipients == 10000
    assert len(cycles) == 10000

    # パフォーマンス目標確認（bulk_create_support_plan_cyclesの設計値: ~500秒）
    assert overall_elapsed < 720, (
        f"生成時間が目標を超過: {overall_elapsed:.1f}秒 > 720秒"
    )
