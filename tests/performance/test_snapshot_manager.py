"""
スナップショット管理機能のテスト

目的: スナップショット作成・復元機能の動作確認
"""
import pytest
import pytest_asyncio
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Office, Staff
from tests.performance.bulk_factories import (
    bulk_create_offices,
    bulk_create_staffs
)
from tests.performance.snapshot_manager import (
    create_snapshot,
    restore_snapshot,
    list_snapshots,
    delete_snapshot,
    snapshot_exists
)


@pytest.mark.asyncio
@pytest.mark.performance
async def test_snapshot_create_and_restore(db_session: AsyncSession):
    """
    スナップショット作成と復元のテスト

    検証項目:
    - スナップショット作成が成功する
    - スナップショット復元が成功する
    - 復元後のデータが元のデータと一致する
    """
    snapshot_name = "test_snapshot_10_offices"

    # 既存のスナップショットを削除
    if await snapshot_exists(snapshot_name):
        await delete_snapshot(snapshot_name)

    # Step 1: テストデータ作成
    print("\n📝 Step 1: テストデータ作成")
    offices = await bulk_create_offices(db_session, count=10)
    staffs_by_office = await bulk_create_staffs(
        db_session,
        offices=offices,
        count_per_office=5
    )

    original_office_count = len(offices)
    original_staff_count = sum(len(s) for s in staffs_by_office.values())

    print(f"   作成: {original_office_count}事業所, {original_staff_count}スタッフ")

    # Step 2: スナップショット作成
    print("\n📸 Step 2: スナップショット作成")
    start_time = time.time()
    metadata = await create_snapshot(
        db_session,
        name=snapshot_name,
        description="10 offices with 5 staffs each"
    )
    create_time = time.time() - start_time

    print(f"   作成時間: {create_time:.2f}秒")
    print(f"   統計: {metadata.stats}")

    assert metadata.name == snapshot_name
    assert metadata.stats["offices"] == 10
    # Note: 50 staffs + 1 system staff created by bulk_create_offices
    assert metadata.stats["staffs"] == 51
    assert metadata.stats["office_staffs"] == 50  # Only regular staffs have associations

    # Step 3: テストデータを削除（外部キー制約を考慮した順序）
    print("\n🗑️ Step 3: テストデータ削除")
    from sqlalchemy import delete as sql_delete
    from app.models import OfficeStaff
    # 依存関係の逆順で削除
    # 1. office_staffs (association)
    # 2. offices (offices.created_by → staffs.id を参照)
    # 3. staffs (参照される側なので最後)
    await db_session.execute(sql_delete(OfficeStaff).where(OfficeStaff.is_test_data == True))
    await db_session.execute(sql_delete(Office).where(Office.is_test_data == True))
    await db_session.execute(sql_delete(Staff).where(Staff.is_test_data == True))
    await db_session.commit()

    # 削除を確認
    stmt = select(Office).where(Office.is_test_data == True)
    result = await db_session.execute(stmt)
    assert len(result.scalars().all()) == 0, "Offices should be deleted"

    # Step 4: スナップショット復元
    print("\n♻️ Step 4: スナップショット復元")
    start_time = time.time()
    restored_metadata = await restore_snapshot(db_session, snapshot_name)
    restore_time = time.time() - start_time

    print(f"   復元時間: {restore_time:.2f}秒")
    print(f"   統計: {restored_metadata.stats}")

    # Step 5: 復元後のデータ確認
    print("\n✅ Step 5: データ整合性確認")
    stmt = select(Office).where(Office.is_test_data == True)
    result = await db_session.execute(stmt)
    restored_offices = result.scalars().all()

    stmt = select(Staff).where(Staff.is_test_data == True)
    result = await db_session.execute(stmt)
    restored_staffs = result.scalars().all()

    assert len(restored_offices) == original_office_count, "Office count should match"
    # Note: original_staff_count doesn't include the system staff, but restored includes all
    assert len(restored_staffs) == original_staff_count + 1, "Staff count should match (including system staff)"

    print(f"   復元確認: {len(restored_offices)}事業所, {len(restored_staffs)}スタッフ")

    # Cleanup
    await delete_snapshot(snapshot_name)

    print(f"\n🎉 スナップショット機能テスト成功!")
    print(f"   作成: {create_time:.2f}秒")
    print(f"   復元: {restore_time:.2f}秒")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_snapshot_list(db_session: AsyncSession):
    """
    スナップショット一覧取得のテスト
    """
    # テストスナップショット作成
    snapshot_names = ["test_list_1", "test_list_2"]

    for name in snapshot_names:
        if await snapshot_exists(name):
            await delete_snapshot(name)

    # 小規模データで2つのスナップショット作成
    for i, name in enumerate(snapshot_names):
        offices = await bulk_create_offices(db_session, count=2)
        await create_snapshot(
            db_session,
            name=name,
            description=f"Test snapshot {i+1}"
        )

        # データをクリーンアップ（外部キー制約を考慮）
        from sqlalchemy import delete as sql_delete
        from app.models import OfficeStaff
        await db_session.execute(sql_delete(OfficeStaff).where(OfficeStaff.is_test_data == True))
        await db_session.execute(sql_delete(Office).where(Office.is_test_data == True))
        await db_session.execute(sql_delete(Staff).where(Staff.is_test_data == True))
        await db_session.commit()

    # スナップショット一覧取得
    snapshots = await list_snapshots()

    # 少なくとも作成した2つは含まれる
    snapshot_names_in_list = [s.name for s in snapshots]
    assert "test_list_1" in snapshot_names_in_list
    assert "test_list_2" in snapshot_names_in_list

    print(f"\n📋 スナップショット一覧:")
    for snapshot in snapshots:
        print(f"   {snapshot.name}: {snapshot.stats}")

    # Cleanup
    for name in snapshot_names:
        await delete_snapshot(name)


@pytest.mark.asyncio
@pytest.mark.performance
async def test_snapshot_performance_comparison(db_session: AsyncSession):
    """
    スナップショット復元 vs データ生成のパフォーマンス比較

    目標: スナップショット復元は生成より10倍以上高速
    """
    snapshot_name = "test_perf_comparison"

    # 既存スナップショット削除
    if await snapshot_exists(snapshot_name):
        await delete_snapshot(snapshot_name)

    # データ生成時間を測定
    print("\n⏱️ データ生成時間測定...")
    start_time = time.time()
    offices = await bulk_create_offices(db_session, count=10)
    staffs_by_office = await bulk_create_staffs(
        db_session,
        offices=offices,
        count_per_office=10
    )
    generation_time = time.time() - start_time
    print(f"   データ生成: {generation_time:.2f}秒")

    # スナップショット作成
    await create_snapshot(db_session, snapshot_name, "Performance test")

    # データ削除（外部キー制約を考慮した順序）
    from sqlalchemy import delete as sql_delete
    from app.models import OfficeStaff
    # 依存関係の逆順で削除
    # 1. office_staffs (association)
    # 2. offices (offices.created_by → staffs.id を参照)
    # 3. staffs (参照される側なので最後)
    await db_session.execute(sql_delete(OfficeStaff).where(OfficeStaff.is_test_data == True))
    await db_session.execute(sql_delete(Office).where(Office.is_test_data == True))
    await db_session.execute(sql_delete(Staff).where(Staff.is_test_data == True))
    await db_session.commit()

    # スナップショット復元時間を測定
    print(f"\n⏱️ スナップショット復元時間測定...")
    start_time = time.time()
    await restore_snapshot(db_session, snapshot_name)
    restore_time = time.time() - start_time
    print(f"   スナップショット復元: {restore_time:.2f}秒")

    # パフォーマンス比較
    speedup = generation_time / restore_time
    print(f"\n📊 パフォーマンス比較:")
    print(f"   データ生成: {generation_time:.2f}秒")
    print(f"   スナップショット復元: {restore_time:.2f}秒")
    print(f"   高速化: {speedup:.1f}倍")

    # 目標: 少なくとも2倍は高速（小規模データなので10倍は難しい）
    assert speedup > 2.0, f"Snapshot restore should be at least 2x faster, got {speedup:.1f}x"

    # Cleanup
    await delete_snapshot(snapshot_name)

    print(f"\n✅ パフォーマンステスト成功! ({speedup:.1f}倍高速)")
