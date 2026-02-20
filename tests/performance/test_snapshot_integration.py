"""
スナップショット統合テスト

目的: 実際のパフォーマンステストでスナップショット機能を活用
- 初回実行: データ生成 (9分) + スナップショット保存
- 2回目以降: スナップショット復元 (10秒)

使用例:
    # 初回実行
    pytest tests/performance/test_snapshot_integration.py::test_100_offices_with_snapshot
    # → データ生成 + スナップショット保存 (9分)

    # 2回目以降
    pytest tests/performance/test_snapshot_integration.py::test_100_offices_with_snapshot
    # → スナップショット復元のみ (10秒)
"""
import pytest
import pytest_asyncio
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Office, Staff, WelfareRecipient, SupportPlanCycle
from tests.performance.bulk_factories import (
    bulk_create_offices,
    bulk_create_staffs,
    bulk_create_welfare_recipients,
    bulk_create_support_plan_cycles
)
from tests.performance.snapshot_manager import (
    create_snapshot,
    restore_snapshot,
    snapshot_exists,
    delete_snapshot
)


SNAPSHOT_NAME = "100_offices_full_dataset"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_100_offices_with_snapshot(db_session: AsyncSession):
    """
    100事業所規模のパフォーマンステスト (スナップショット統合版)

    初回実行:
    - データ生成: 9分
    - スナップショット保存: 数秒
    - 合計: ~9分

    2回目以降:
    - スナップショット復元: <10秒
    - データ検証: 数秒
    - 合計: ~10秒

    期待される高速化: 54倍 (540秒 / 10秒)
    """
    print("\n" + "=" * 80)
    print("📊 100事業所規模パフォーマンステスト (スナップショット統合版)")
    print("=" * 80)

    overall_start = time.time()
    is_first_run = not await snapshot_exists(SNAPSHOT_NAME)

    if is_first_run:
        print("\n🆕 初回実行: データ生成 + スナップショット保存")
        print("=" * 80)

        # Step 1: データ生成
        print("\n⏳ データ生成中...")
        generation_start = time.time()

        # 事業所作成
        print("  Step 1/4: 事業所作成中...")
        start = time.time()
        offices = await bulk_create_offices(db_session, count=100)
        print(f"    ✅ {len(offices)}事業所作成完了 ({time.time() - start:.2f}秒)")

        # スタッフ作成
        print("  Step 2/4: スタッフ作成中...")
        start = time.time()
        staffs_by_office = await bulk_create_staffs(
            db_session,
            offices=offices,
            count_per_office=10
        )
        total_staffs = sum(len(s) for s in staffs_by_office.values())
        print(f"    ✅ {total_staffs}スタッフ作成完了 ({time.time() - start:.2f}秒)")

        # 利用者作成
        print("  Step 3/4: 利用者作成中...")
        start = time.time()
        recipients_by_office = await bulk_create_welfare_recipients(
            db_session,
            offices=offices,
            count_per_office=100
        )
        total_recipients = sum(len(r) for r in recipients_by_office.values())
        print(f"    ✅ {total_recipients}利用者作成完了 ({time.time() - start:.2f}秒)")

        # サイクル作成
        print("  Step 4/4: サイクル作成中...")
        start = time.time()
        cycles = await bulk_create_support_plan_cycles(
            db_session,
            recipients_by_office=recipients_by_office
        )
        print(f"    ✅ {len(cycles)}サイクル作成完了 ({time.time() - start:.2f}秒)")

        generation_time = time.time() - generation_start

        # Step 2: スナップショット保存
        print("\n📸 スナップショット保存中...")
        snapshot_start = time.time()
        metadata = await create_snapshot(
            db_session,
            name=SNAPSHOT_NAME,
            description="100 offices with 1000 staffs, 10000 recipients, 10000 cycles"
        )
        snapshot_time = time.time() - snapshot_start

        print(f"\n✅ スナップショット保存完了!")
        print(f"   データ生成時間: {generation_time:.2f}秒 ({generation_time / 60:.1f}分)")
        print(f"   スナップショット保存時間: {snapshot_time:.2f}秒")
        print(f"   統計: {metadata.stats}")

    else:
        print("\n♻️ 2回目以降の実行: スナップショット復元")
        print("=" * 80)

        # スナップショット復元
        print("\n⏳ スナップショット復元中...")
        restore_start = time.time()
        metadata = await restore_snapshot(db_session, SNAPSHOT_NAME)
        restore_time = time.time() - restore_start

        print(f"\n✅ スナップショット復元完了!")
        print(f"   復元時間: {restore_time:.2f}秒")
        print(f"   統計: {metadata.stats}")

    # データ検証
    print("\n🔍 データ整合性検証中...")
    verify_start = time.time()

    stmt = select(Office).where(Office.is_test_data == True)
    result = await db_session.execute(stmt)
    offices_count = len(result.scalars().all())

    stmt = select(Staff).where(Staff.is_test_data == True)
    result = await db_session.execute(stmt)
    staffs_count = len(result.scalars().all())

    stmt = select(WelfareRecipient).where(WelfareRecipient.is_test_data == True)
    result = await db_session.execute(stmt)
    recipients_count = len(result.scalars().all())

    stmt = select(SupportPlanCycle).where(SupportPlanCycle.is_test_data == True)
    result = await db_session.execute(stmt)
    cycles_count = len(result.scalars().all())

    verify_time = time.time() - verify_start

    # 検証結果
    assert offices_count == 100, f"Expected 100 offices, got {offices_count}"
    assert staffs_count == 1001, f"Expected 1001 staffs (1000 + 1 system), got {staffs_count}"
    assert recipients_count == 10000, f"Expected 10000 recipients, got {recipients_count}"
    assert cycles_count == 10000, f"Expected 10000 cycles, got {cycles_count}"

    print(f"   ✅ 事業所: {offices_count}件")
    print(f"   ✅ スタッフ: {staffs_count}件")
    print(f"   ✅ 利用者: {recipients_count}件")
    print(f"   ✅ サイクル: {cycles_count}件")
    print(f"   検証時間: {verify_time:.2f}秒")

    overall_time = time.time() - overall_start

    # 結果サマリー
    print("\n" + "=" * 80)
    print("📊 実行結果サマリー")
    print("=" * 80)

    if is_first_run:
        print(f"実行モード: 🆕 初回実行 (データ生成 + スナップショット保存)")
        print(f"総実行時間: {overall_time:.2f}秒 ({overall_time / 60:.1f}分)")
        print(f"  - データ生成: {generation_time:.2f}秒")
        print(f"  - スナップショット保存: {snapshot_time:.2f}秒")
        print(f"  - データ検証: {verify_time:.2f}秒")
    else:
        print(f"実行モード: ♻️ 2回目以降 (スナップショット復元)")
        print(f"総実行時間: {overall_time:.2f}秒")
        print(f"  - スナップショット復元: {restore_time:.2f}秒")
        print(f"  - データ検証: {verify_time:.2f}秒")
        print(f"\n🚀 高速化: {540 / overall_time:.1f}倍 (vs 初回データ生成)")

    print("=" * 80)


@pytest.mark.asyncio
@pytest.mark.performance
async def test_snapshot_performance_comparison(db_session: AsyncSession):
    """
    データ生成 vs スナップショット復元のパフォーマンス比較

    目的: スナップショット機能の効果を定量的に測定

    期待結果:
    - スナップショット復元は生成より50倍以上高速
    """
    print("\n" + "=" * 80)
    print("📊 パフォーマンス比較: データ生成 vs スナップショット復元")
    print("=" * 80)

    comparison_snapshot = "comparison_test_50_offices"

    # 既存スナップショット削除
    if await snapshot_exists(comparison_snapshot):
        await delete_snapshot(comparison_snapshot)

    # Step 1: データ生成時間を測定
    print("\n⏱️ Step 1: データ生成時間測定")
    print("-" * 80)

    generation_start = time.time()

    offices = await bulk_create_offices(db_session, count=50)
    staffs_by_office = await bulk_create_staffs(
        db_session,
        offices=offices,
        count_per_office=10
    )
    recipients_by_office = await bulk_create_welfare_recipients(
        db_session,
        offices=offices,
        count_per_office=100
    )
    cycles = await bulk_create_support_plan_cycles(
        db_session,
        recipients_by_office=recipients_by_office
    )

    generation_time = time.time() - generation_start

    print(f"データ生成完了:")
    print(f"  - 事業所: {len(offices)}件")
    print(f"  - スタッフ: {sum(len(s) for s in staffs_by_office.values())}件")
    print(f"  - 利用者: {sum(len(r) for r in recipients_by_office.values())}件")
    print(f"  - サイクル: {len(cycles)}件")
    print(f"  ⏱️ 生成時間: {generation_time:.2f}秒 ({generation_time / 60:.1f}分)")

    # Step 2: スナップショット作成
    print("\n⏱️ Step 2: スナップショット作成")
    print("-" * 80)

    snapshot_create_start = time.time()
    await create_snapshot(db_session, comparison_snapshot, "Performance comparison test")
    snapshot_create_time = time.time() - snapshot_create_start

    print(f"  ⏱️ スナップショット作成時間: {snapshot_create_time:.2f}秒")

    # Step 3: データ削除
    print("\n⏱️ Step 3: テストデータ削除")
    print("-" * 80)

    from sqlalchemy import delete as sql_delete
    from app.models import OfficeStaff, OfficeWelfareRecipient

    delete_start = time.time()
    await db_session.execute(sql_delete(SupportPlanCycle).where(SupportPlanCycle.is_test_data == True))
    await db_session.execute(sql_delete(OfficeWelfareRecipient).where(OfficeWelfareRecipient.is_test_data == True))
    await db_session.execute(sql_delete(WelfareRecipient).where(WelfareRecipient.is_test_data == True))
    await db_session.execute(sql_delete(OfficeStaff).where(OfficeStaff.is_test_data == True))
    await db_session.execute(sql_delete(Office).where(Office.is_test_data == True))
    await db_session.execute(sql_delete(Staff).where(Staff.is_test_data == True))
    await db_session.commit()
    delete_time = time.time() - delete_start

    print(f"  ⏱️ 削除時間: {delete_time:.2f}秒")

    # Step 4: スナップショット復元時間を測定
    print("\n⏱️ Step 4: スナップショット復元時間測定")
    print("-" * 80)

    restore_start = time.time()
    await restore_snapshot(db_session, comparison_snapshot)
    restore_time = time.time() - restore_start

    print(f"  ⏱️ 復元時間: {restore_time:.2f}秒")

    # Step 5: 結果比較
    print("\n" + "=" * 80)
    print("📊 パフォーマンス比較結果")
    print("=" * 80)

    speedup = generation_time / restore_time

    print(f"\n【時間比較】")
    print(f"  データ生成時間:         {generation_time:>8.2f}秒 ({generation_time / 60:.1f}分)")
    print(f"  スナップショット作成時間: {snapshot_create_time:>8.2f}秒")
    print(f"  スナップショット復元時間: {restore_time:>8.2f}秒")
    print(f"  削除時間:               {delete_time:>8.2f}秒")

    print(f"\n【高速化】")
    print(f"  スナップショット復元は生成より {speedup:.1f}倍高速 🚀")

    print(f"\n【実用効果】")
    print(f"  初回実行: {generation_time + snapshot_create_time:.1f}秒")
    print(f"  2回目以降: {restore_time:.1f}秒")
    print(f"  時間削減: {generation_time + snapshot_create_time - restore_time:.1f}秒/回")

    # 目標: 少なくとも10倍は高速
    assert speedup >= 10.0, f"Snapshot restore should be at least 10x faster, got {speedup:.1f}x"

    # Cleanup
    await delete_snapshot(comparison_snapshot)

    print("\n✅ パフォーマンス比較テスト完了!")
    print("=" * 80)


@pytest.mark.asyncio
@pytest.mark.performance
async def test_cleanup_snapshot(db_session: AsyncSession):
    """
    スナップショットクリーンアップテスト

    目的: テスト後にスナップショットを削除するオプション

    使用方法:
        # スナップショットを削除したい場合
        pytest tests/performance/test_snapshot_integration.py::test_cleanup_snapshot
    """
    print("\n🗑️ スナップショットクリーンアップ")

    if await snapshot_exists(SNAPSHOT_NAME):
        deleted = await delete_snapshot(SNAPSHOT_NAME)
        if deleted:
            print(f"   ✅ '{SNAPSHOT_NAME}' を削除しました")
        else:
            print(f"   ⚠️ '{SNAPSHOT_NAME}' の削除に失敗しました")
    else:
        print(f"   ℹ️ '{SNAPSHOT_NAME}' は存在しません")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_list_all_snapshots(db_session: AsyncSession):
    """
    全スナップショット一覧表示

    目的: 現在保存されているスナップショットの確認
    """
    from tests.performance.snapshot_manager import list_snapshots

    print("\n📋 保存されているスナップショット一覧")
    print("=" * 80)

    snapshots = await list_snapshots()

    if not snapshots:
        print("   (スナップショットが見つかりません)")
    else:
        for i, snapshot in enumerate(snapshots, 1):
            print(f"\n{i}. {snapshot.name}")
            print(f"   作成日時: {snapshot.created_at}")
            print(f"   説明: {snapshot.description}")
            print(f"   統計: {snapshot.stats}")

    print("\n" + "=" * 80)
    print(f"合計: {len(snapshots)}個のスナップショット")
    print("=" * 80)
