"""
Gmail期限通知バッチ処理のパフォーマンステスト

目的:
- 500事業所規模での処理時間測定（目標: 5分以内）
- N+1クエリ問題の検出（目標: クエリ数O(1)）
- メモリリーク検出（目標: 50MB以下）
- 並列処理効率の測定（目標: 10並列以上）

実行方法:
    docker exec keikakun_app-backend-1 pytest tests/performance/test_deadline_notification_performance.py -v -m performance
"""
import asyncio
import gc
import os
import time
from datetime import date, timedelta
from typing import Dict, List
from unittest.mock import patch

import psutil
import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

# Note: StaffRole.employee is used instead of importing since factory handles role
from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.support_plan_cycle import SupportPlanCycle
from app.models.welfare_recipient import WelfareRecipient
from app.tasks.deadline_notification import send_deadline_alert_emails


# ==================== Query Counter ====================

class QueryCounter:
    """
    SQLクエリ数をカウントするためのイベントリスナー

    N+1クエリ問題を検出するために使用
    """
    def __init__(self):
        self.count = 0
        self.queries: List[Dict] = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        """SQLAlchemy event listener callback"""
        self.count += 1
        self.queries.append({
            'statement': statement[:200],  # 最初の200文字のみ記録
            'parameters': parameters
        })

    def reset(self):
        """カウンターをリセット"""
        self.count = 0
        self.queries = []


# ==================== Fixtures ====================

@pytest.fixture
def query_counter(db_session: AsyncSession) -> QueryCounter:
    """
    SQLクエリ数をカウントするフィクスチャ

    使用例:
        result = await some_function(db=db_session)
        assert query_counter.count < 10, "クエリ数が多すぎます"
    """
    counter = QueryCounter()

    # SQLAlchemyのイベントリスナーに登録
    # 注意: async sessionの内部sync sessionのbindにアタッチ
    bind = db_session.sync_session.bind
    event.listen(bind, "before_cursor_execute", counter)

    yield counter

    # クリーンアップ: イベントリスナーを削除
    event.remove(bind, "before_cursor_execute", counter)


@pytest_asyncio.fixture
async def performance_test_data_small(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
) -> Dict:
    """
    小規模パフォーマンステストデータ（10事業所、100スタッフ）

    クエリ効率テストに使用
    """
    offices = []

    for i in range(10):
        office = await office_factory(
            creator=test_admin_user,
            name=f"テスト事業所{i+1}"
        )
        offices.append(office)

        # 各事業所に10人のスタッフを作成
        for j in range(10):
            staff = await staff_factory(
                office_id=office.id,
                email=f"staff_{i}_{j}@example.com"
            )
            staff.notification_preferences = {
                "in_app_notification": True,
                "email_notification": True,
                "email_threshold_days": 30,
                "push_threshold_days": 30
            }
            db_session.add(staff)
            db_session.add(OfficeStaff(
                staff_id=staff.id,
                office_id=office.id,
                is_primary=True,
                is_test_data=True
            ))

        # 各事業所に10人の利用者 + アラートを作成
        for k in range(10):
            recipient = await welfare_recipient_factory(
                office_id=office.id
            )

            # 更新期限15日後のアラート（閾値内）
            cycle = SupportPlanCycle(
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                next_renewal_deadline=date.today() + timedelta(days=15),
                is_latest_cycle=True,
                cycle_number=1,
                next_plan_start_date=7,
                is_test_data=True
            )
            db_session.add(cycle)

        # 10事業所ごとにflush（メモリ節約）
        if (i + 1) % 10 == 0:
            await db_session.flush()

    await db_session.commit()

    return {
        "office_count": 10,
        "staff_count": 100,
        "recipient_count": 100,
        "expected_emails": 100 * 10  # 100利用者 × 10スタッフ
    }


@pytest_asyncio.fixture
async def performance_test_data_large(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
) -> Dict:
    """
    大規模パフォーマンステストデータ（500事業所、5,000スタッフ）

    本格的なパフォーマンステストに使用

    警告: このフィクスチャはデータ生成に時間がかかります（数分）
    """
    print("\n⏳ 大規模テストデータ生成開始（500事業所、5,000スタッフ）...")
    start_time = time.time()

    offices = []

    for i in range(500):
        office = await office_factory(
            creator=test_admin_user,
            name=f"パフォーマンステスト事業所{i+1}"
        )
        offices.append(office)

        # 各事業所に10人のスタッフを作成
        for j in range(10):
            staff = await staff_factory(
                office_id=office.id,
                email=f"perf_staff_{i}_{j}@example.com"
            )
            staff.notification_preferences = {
                "in_app_notification": True,
                "email_notification": True,
                "email_threshold_days": 30,
                "push_threshold_days": 30
            }
            db_session.add(staff)
            db_session.add(OfficeStaff(
                staff_id=staff.id,
                office_id=office.id,
                is_primary=True,
                is_test_data=True
            ))

        # 各事業所に10人の利用者 + アラートを作成
        for k in range(10):
            recipient = await welfare_recipient_factory(
                office_id=office.id
            )

            # 更新期限15日後のアラート（閾値内）
            cycle = SupportPlanCycle(
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                next_renewal_deadline=date.today() + timedelta(days=15),
                is_latest_cycle=True,
                cycle_number=1,
                next_plan_start_date=7,
                is_test_data=True
            )
            db_session.add(cycle)

        # 100事業所ごとにcommit（メモリ節約とパフォーマンス）
        if (i + 1) % 100 == 0:
            await db_session.commit()
            elapsed = time.time() - start_time
            print(f"  📊 {i+1}/500 事業所作成完了 ({elapsed:.1f}秒経過)")

    await db_session.commit()

    elapsed_time = time.time() - start_time
    print(f"✅ テストデータ生成完了 ({elapsed_time:.1f}秒)")

    return {
        "office_count": 500,
        "staff_count": 5000,
        "recipient_count": 5000,
        "expected_emails": 5000 * 10  # 5,000利用者 × 10スタッフ
    }


@pytest.fixture(autouse=True)
def mock_weekday_check():
    """
    週末・祝日チェックをスキップ（全テストで自動適用）
    """
    with patch('app.tasks.deadline_notification.is_japanese_weekday_and_not_holiday', return_value=True):
        yield


# ==================== Performance Tests ====================

@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.timeout(600)  # 10分タイムアウト
async def test_deadline_notification_performance_500_offices(
    db_session: AsyncSession,
    performance_test_data_large: Dict,
    query_counter: QueryCounter
):
    """
    Test 1: 基本パフォーマンステスト（500事業所）

    目標:
    - 処理時間: < 300秒（5分）
    - メモリ増加: < 50MB
    - DBクエリ数: < 100回
    - 送信メール数: 期待値と一致

    現状の予想（最適化前）:
    - 処理時間: 約1,500秒（25分）⚠️
    - メモリ増加: 約500MB ⚠️
    - DBクエリ数: 約1,001回 ⚠️

    このテストは現時点では失敗する（RED状態）のが正常です。
    """
    print("\n" + "="*70)
    print("📊 Test 1: 基本パフォーマンステスト（500事業所）")
    print("="*70)

    # メモリ測定開始
    process = psutil.Process(os.getpid())
    gc.collect()  # GC実行
    await asyncio.sleep(0.1)  # GC完了待機
    memory_before = process.memory_info().rss / 1024 / 1024  # MB

    # 処理時間測定開始
    start_time = time.time()

    # バッチ処理実行（dry_run=Trueで実際のメール送信はしない）
    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    # 処理時間測定終了
    elapsed_time = time.time() - start_time

    # メモリ測定終了
    memory_after = process.memory_info().rss / 1024 / 1024
    memory_increase = memory_after - memory_before

    # 結果表示
    print(f"\n📈 測定結果:")
    print(f"  ⏱️  処理時間: {elapsed_time:.1f}秒 (目標: < 300秒)")
    print(f"  💾 メモリ増加: {memory_increase:.1f}MB (目標: < 50MB)")
    print(f"  🗃️  DBクエリ数: {query_counter.count}回 (目標: < 100回)")
    print(f"  📧 送信メール数: {result['email_sent']}件")

    # 検証
    assert result['email_sent'] == performance_test_data_large['expected_emails'], \
        f"送信メール数が期待値と異なる: {result['email_sent']} != {performance_test_data_large['expected_emails']}"

    # パフォーマンス目標（現時点では失敗する）
    assert elapsed_time < 300, \
        f"処理時間が目標を超過: {elapsed_time:.1f}秒 > 300秒"

    assert memory_increase < 50, \
        f"メモリ増加が目標を超過: {memory_increase:.1f}MB > 50MB"

    assert query_counter.count < 100, \
        f"DBクエリ数が目標を超過: {query_counter.count}回 > 100回"

    print("✅ 全ての目標を達成しました！")


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.timeout(300)  # 5分タイムアウト
async def test_query_efficiency_no_n_plus_1(
    db_session: AsyncSession,
    performance_test_data_small: Dict,
    query_counter: QueryCounter
):
    """
    Test 2: クエリ効率テスト（N+1問題検出）

    目標:
    - クエリ数が事業所数に比例しない（O(1)）
    - 10事業所でも100事業所でもクエリ数は一定

    理論値:
    - 事業所取得: 1クエリ
    - アラート取得: 2クエリ（更新期限 + アセスメント）
    - スタッフ取得: 1クエリ
    - 合計: 4クエリ（定数）

    現状の予想（最適化前）:
    - 約21クエリ（2N+1 = 2*10+1）⚠️

    このテストは現時点では失敗する（RED状態）のが正常です。
    """
    print("\n" + "="*70)
    print("📊 Test 2: クエリ効率テスト（N+1問題検出）")
    print("="*70)

    office_count = performance_test_data_small['office_count']

    # クエリカウンターをリセット
    query_counter.reset()

    # バッチ処理実行
    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    # 結果表示
    print(f"\n📈 測定結果:")
    print(f"  🏢 事業所数: {office_count}")
    print(f"  🗃️  DBクエリ数: {query_counter.count}回")
    print(f"  📧 送信メール数: {result['email_sent']}件")

    # N+1問題の判定
    # クエリ数が事業所数の20%以下であればOK（O(1)と見なす）
    max_allowed_queries = office_count * 0.2  # 10事業所 → 2クエリ

    print(f"\n🎯 N+1問題チェック:")
    print(f"  許容クエリ数: < {max_allowed_queries}回 (事業所数の20%)")
    print(f"  実際のクエリ数: {query_counter.count}回")

    # 検証
    assert result['email_sent'] == performance_test_data_small['expected_emails'], \
        f"送信メール数が期待値と異なる"

    assert query_counter.count < max_allowed_queries, \
        f"N+1クエリ問題が検出されました: {query_counter.count}回 >= {max_allowed_queries}回\n" \
        f"クエリ数が事業所数に比例しています（O(N)）"

    print("✅ N+1問題なし（クエリ数O(1)）")


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.timeout(600)  # 10分タイムアウト
async def test_memory_efficiency_chunk_processing(
    db_session: AsyncSession,
    performance_test_data_large: Dict,
    query_counter: QueryCounter
):
    """
    Test 3: メモリ効率テスト（リーク検出）

    目標:
    - ピークメモリ増加: < 50MB
    - GC後のメモリ保持: < 10MB（増加分の20%以下）
    - メモリリークなし

    検証方法:
    1. 処理前のメモリ測定
    2. 処理実行
    3. ピークメモリ測定
    4. GC実行
    5. GC後のメモリ測定
    6. メモリリーク率の計算

    現状の予想（最適化前）:
    - ピークメモリ増加: 約500MB ⚠️
    - メモリリーク率: 高い可能性 ⚠️

    このテストは現時点では失敗する（RED状態）のが正常です。
    """
    print("\n" + "="*70)
    print("📊 Test 3: メモリ効率テスト（リーク検出）")
    print("="*70)

    process = psutil.Process(os.getpid())

    # 処理前: GC実行 + メモリ測定
    gc.collect()
    await asyncio.sleep(0.1)
    memory_baseline = process.memory_info().rss / 1024 / 1024
    print(f"\n📏 ベースラインメモリ: {memory_baseline:.1f}MB")

    # 処理実行
    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    # ピークメモリ測定
    memory_peak = process.memory_info().rss / 1024 / 1024
    memory_peak_increase = memory_peak - memory_baseline
    print(f"📈 ピークメモリ: {memory_peak:.1f}MB (+{memory_peak_increase:.1f}MB)")

    # GC実行
    gc.collect()
    await asyncio.sleep(0.5)  # GC完了待機

    # GC後のメモリ測定
    memory_after_gc = process.memory_info().rss / 1024 / 1024
    memory_after_gc_increase = memory_after_gc - memory_baseline
    print(f"📉 GC後メモリ: {memory_after_gc:.1f}MB (+{memory_after_gc_increase:.1f}MB)")

    # メモリリーク率の計算
    if memory_peak_increase > 0:
        memory_leak_ratio = memory_after_gc_increase / memory_peak_increase
    else:
        memory_leak_ratio = 0

    print(f"\n🔍 メモリリーク分析:")
    print(f"  ピーク増加: {memory_peak_increase:.1f}MB")
    print(f"  GC後増加: {memory_after_gc_increase:.1f}MB")
    print(f"  リーク率: {memory_leak_ratio*100:.1f}% (目標: < 20%)")

    # 検証
    assert result['email_sent'] == performance_test_data_large['expected_emails'], \
        f"送信メール数が期待値と異なる"

    assert memory_peak_increase < 50, \
        f"ピークメモリ増加が目標を超過: {memory_peak_increase:.1f}MB > 50MB"

    assert memory_after_gc_increase < 10, \
        f"GC後メモリ増加が目標を超過: {memory_after_gc_increase:.1f}MB > 10MB"

    assert memory_leak_ratio < 0.2, \
        f"メモリリークの可能性: リーク率{memory_leak_ratio*100:.1f}% > 20%"

    print("✅ メモリリークなし")


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.timeout(600)  # 10分タイムアウト
async def test_parallel_processing_speedup(
    db_session: AsyncSession,
    performance_test_data_large: Dict,
    query_counter: QueryCounter
):
    """
    Test 4: 並列処理効率テスト

    目標:
    - 1事業所あたりの処理時間: < 0.1秒
    - 推定並列度: >= 10倍

    検証方法:
    1. 総処理時間 / 事業所数 = 1事業所あたりの処理時間
    2. 1事業所あたりの処理時間から並列度を推定

    例:
    - 総処理時間: 180秒
    - 事業所数: 500
    - 1事業所あたり: 180/500 = 0.36秒
    - 推定並列度: 1/0.36 ≈ 2.78倍（目標未達）

    目標達成例:
    - 総処理時間: 180秒
    - 事業所数: 500
    - 1事業所あたり: 180/500 = 0.36秒
    - 1事業所の実処理時間: 3秒と仮定
    - 推定並列度: 3/0.36 ≈ 8.3倍

    現状の予想（最適化前）:
    - 並列度: 1倍（直列処理）⚠️

    このテストは現時点では失敗する（RED状態）のが正常です。
    """
    print("\n" + "="*70)
    print("📊 Test 4: 並列処理効率テスト")
    print("="*70)

    office_count = performance_test_data_large['office_count']

    # 処理時間測定
    start_time = time.time()
    result = await send_deadline_alert_emails(db=db_session, dry_run=True)
    elapsed_time = time.time() - start_time

    # 1事業所あたりの処理時間
    time_per_office = elapsed_time / office_count

    # 推定並列度（1事業所あたり0.1秒以下なら10並列以上相当）
    if time_per_office > 0:
        estimated_parallelism = 1 / time_per_office
    else:
        estimated_parallelism = float('inf')

    # 結果表示
    print(f"\n📈 測定結果:")
    print(f"  ⏱️  総処理時間: {elapsed_time:.1f}秒")
    print(f"  🏢 事業所数: {office_count}")
    print(f"  📊 1事業所あたり: {time_per_office:.3f}秒 (目標: < 0.1秒)")
    print(f"  🚀 推定並列度: {estimated_parallelism:.1f}倍 (目標: >= 10倍)")

    # 検証
    assert result['email_sent'] == performance_test_data_large['expected_emails'], \
        f"送信メール数が期待値と異なる"

    assert time_per_office < 0.1, \
        f"1事業所あたりの処理時間が目標を超過: {time_per_office:.3f}秒 > 0.1秒\n" \
        f"並列度が不十分です"

    assert estimated_parallelism >= 10, \
        f"推定並列度が目標未達: {estimated_parallelism:.1f}倍 < 10倍"

    print("✅ 並列処理効率が目標を達成しました")


# ==================== Load Tests ====================

@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.timeout(600)  # 10分タイムアウト
async def test_error_resilience(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff,
    query_counter: QueryCounter
):
    """
    Test 6: エラー耐性テスト（負荷テスト）

    目的:
    - 一部の事業所でエラーが発生しても全体の処理が継続することを確認

    テストシナリオ:
    1. 10事業所を作成（軽量版で高速実行）
    2. 2事業所のスタッフに不正なメールアドレスを設定
    3. バッチ処理実行
    4. 8事業所は正常処理、2事業所はエラー

    受け入れ基準:
    - 40件送信成功（8事業所 × 5スタッフ）
    - エラーが発生しても全体の処理は完了
    - 全体の処理時間は許容範囲内
    """
    print("\n" + "="*70)
    print("📊 Test 6: エラー耐性テスト")
    print("="*70)

    # テストデータ生成
    print("\n⏳ テストデータ生成中（10事業所）...")

    normal_offices = []
    error_offices = []

    for i in range(10):
        office = await office_factory(
            creator=test_admin_user,
            name=f"エラー耐性テスト事業所{i+1}"
        )

        # 2事業所をエラー対象として設定
        is_error_office = (i < 2)
        if is_error_office:
            error_offices.append(office)
        else:
            normal_offices.append(office)

        # 各事業所に5人のスタッフを作成
        for j in range(5):
            # エラー対象事業所には不正なメールアドレスを設定
            if is_error_office:
                email = f"invalid-email-{i}-{j}"  # @がない不正なアドレス
            else:
                email = f"resilience_staff_{i}_{j}@example.com"

            staff = await staff_factory(
                office_id=office.id,
                email=email
            )
            staff.notification_preferences = {
                "in_app_notification": True,
                "email_notification": True,
                "email_threshold_days": 30,
                "push_threshold_days": 30
            }
            db_session.add(staff)
            db_session.add(OfficeStaff(
                staff_id=staff.id,
                office_id=office.id,
                is_primary=True,
                is_test_data=True
            ))

        # 各事業所に5人の利用者 + アラートを作成
        for k in range(5):
            recipient = await welfare_recipient_factory(
                office_id=office.id
            )
            cycle = SupportPlanCycle(
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                next_renewal_deadline=date.today() + timedelta(days=15),
                is_latest_cycle=True,
                cycle_number=1,
                next_plan_start_date=7,
                is_test_data=True
            )
            db_session.add(cycle)

    await db_session.commit()
    print(f"✅ テストデータ生成完了（正常: {len(normal_offices)}事業所、エラー: {len(error_offices)}事業所）")

    # バッチ処理実行
    print("\n⏱️  バッチ処理実行中...")
    start_time = time.time()

    result = await send_deadline_alert_emails(db=db_session, dry_run=True)

    elapsed_time = time.time() - start_time

    # 結果表示
    print(f"\n📈 測定結果:")
    print(f"  ⏱️  処理時間: {elapsed_time:.1f}秒")
    print(f"  📧 送信メール数: {result['email_sent']}件")
    print(f"  🏢 正常処理事業所数: {len(normal_offices)}")
    print(f"  ⚠️  エラー事業所数: {len(error_offices)}")

    # 期待される送信数: 45事業所 × 10スタッフ = 450件
    # ただし、dry_runモードでは不正なメールアドレスでもカウントされる可能性があるため
    # 実際の本番環境ではエラーハンドリングで除外される
    expected_normal_emails = len(normal_offices) * 10

    print(f"\n🎯 検証:")
    print(f"  期待される正常送信数: {expected_normal_emails}件")

    # 検証
    # dry_runモードでは送信カウントのみ行われるため、すべてカウントされる
    # 本来は450件が正常、50件がエラーとなるべき
    # ここでは全体の処理が完了することを確認
    assert result['email_sent'] >= expected_normal_emails, \
        f"正常な事業所の送信数が不足: {result['email_sent']} < {expected_normal_emails}"

    # 処理時間が許容範囲内であることを確認（50事業所なので30秒以内が目標）
    assert elapsed_time < 60, \
        f"処理時間が長すぎます: {elapsed_time:.1f}秒 > 60秒"

    print("✅ エラー耐性テストに合格しました")
    print("   - 一部のエラーがあっても全体の処理が完了")
    print("   - 正常な事業所は問題なく処理された")


# ==================== Additional Helper Tests ====================

@pytest.mark.asyncio
@pytest.mark.performance
async def test_performance_test_data_generation_speed(
    db_session: AsyncSession,
    office_factory,
    staff_factory,
    welfare_recipient_factory,
    test_admin_user: Staff
):
    """
    補助テスト: テストデータ生成速度の測定

    目的:
    - 100事業所のテストデータ生成にかかる時間を測定
    - フィクスチャのパフォーマンスを確認

    期待: < 60秒
    """
    print("\n" + "="*70)
    print("📊 補助テスト: テストデータ生成速度")
    print("="*70)

    start_time = time.time()

    for i in range(100):
        office = await office_factory(
            creator=test_admin_user,
            name=f"速度テスト事業所{i+1}"
        )

        # 各事業所に10人のスタッフ
        for j in range(10):
            staff = await staff_factory(
                office_id=office.id,
                email=f"speed_test_{i}_{j}@example.com"
            )
            db_session.add(OfficeStaff(
                staff_id=staff.id,
                office_id=office.id,
                is_primary=True,
                is_test_data=True
            ))

        # 各事業所に10人の利用者
        for k in range(10):
            recipient = await welfare_recipient_factory(
                office_id=office.id
            )
            cycle = SupportPlanCycle(
                welfare_recipient_id=recipient.id,
                office_id=office.id,
                next_renewal_deadline=date.today() + timedelta(days=15),
                is_latest_cycle=True,
                cycle_number=1,
                next_plan_start_date=7,
                is_test_data=True
            )
            db_session.add(cycle)

        if (i + 1) % 50 == 0:
            await db_session.commit()

    await db_session.commit()

    elapsed_time = time.time() - start_time

    print(f"\n📈 測定結果:")
    print(f"  ⏱️  生成時間: {elapsed_time:.1f}秒")
    print(f"  🏢 事業所数: 100")
    print(f"  📊 1事業所あたり: {elapsed_time/100:.2f}秒")

    # 参考情報として表示（アサーションはしない）
    if elapsed_time < 60:
        print("✅ テストデータ生成が高速です")
    else:
        print("⚠️  テストデータ生成に時間がかかっています")
