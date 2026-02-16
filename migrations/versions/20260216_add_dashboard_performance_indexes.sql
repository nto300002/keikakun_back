-- ================================================================
-- ダッシュボードパフォーマンス最適化 - 複合インデックス追加
-- ================================================================
-- 作成日: 2026-02-16
-- 目的: 500事業所以上のスケールに対応
-- 期待効果: 各クエリ10倍高速化、レスポンス時間 3-5秒 → 300-500ms
--
-- 関連ドキュメント:
-- - md_files_design_note/task/kensaku/02_improvement_requirements.md
-- - md_files_design_note/task/kensaku/03_implementation_guide.md
-- ================================================================

-- ================================================================
-- 1. 最新サイクル検索用の部分インデックス
-- ================================================================
-- 対象クエリ: cycle_info_sq サブクエリ
-- 効果: 最新サイクル検索 500ms → 50ms (10倍高速化)
-- 部分インデックス: is_latest_cycle=true のレコードのみ
-- ================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_plan_cycles_recipient_latest
ON support_plan_cycles (welfare_recipient_id, is_latest_cycle)
WHERE is_latest_cycle = true;

COMMENT ON INDEX idx_support_plan_cycles_recipient_latest IS
'最新サイクル検索用の部分インデックス（is_latest_cycle=true のみ）- ダッシュボードフィルター最適化';

-- ================================================================
-- 2. 最新ステータス検索用の部分インデックス
-- ================================================================
-- 対象クエリ: ステータスフィルター、selectinload
-- 効果: ステータスフィルター 300ms → 30ms (10倍高速化)
-- 部分インデックス: is_latest_status=true のレコードのみ
-- ================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_plan_statuses_cycle_latest
ON support_plan_statuses (plan_cycle_id, is_latest_status, step_type)
WHERE is_latest_status = true;

COMMENT ON INDEX idx_support_plan_statuses_cycle_latest IS
'最新ステータス検索用の部分インデックス（is_latest_status=true のみ）- ダッシュボードフィルター最適化';

-- ================================================================
-- 3. ふりがなソート用のインデックス
-- ================================================================
-- 対象クエリ: ORDER BY CONCAT(last_name_furigana, first_name_furigana)
-- 効果: ふりがなソート 200ms → 20ms (10倍高速化)
-- ================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_welfare_recipients_furigana
ON welfare_recipients (last_name_furigana, first_name_furigana);

COMMENT ON INDEX idx_welfare_recipients_furigana IS
'ふりがなソート用のインデックス - ダッシュボードフィルター最適化';

-- ================================================================
-- 4. 事業所別検索用のインデックス
-- ================================================================
-- 対象クエリ: WHERE office_id IN (...)
-- 効果: 事業所フィルター 100ms → 10ms (10倍高速化)
-- ================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_office_welfare_recipients_office
ON office_welfare_recipients (office_id, welfare_recipient_id);

COMMENT ON INDEX idx_office_welfare_recipients_office IS
'事業所別検索用のインデックス - ダッシュボードフィルター最適化';

-- ================================================================
-- インデックス作成結果の確認
-- ================================================================
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE indexname IN (
    'idx_support_plan_cycles_recipient_latest',
    'idx_support_plan_statuses_cycle_latest',
    'idx_welfare_recipients_furigana',
    'idx_office_welfare_recipients_office'
)
ORDER BY tablename, indexname;

-- ================================================================
-- インデックスサイズの確認
-- ================================================================
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS index_size
FROM pg_indexes
WHERE indexname IN (
    'idx_support_plan_cycles_recipient_latest',
    'idx_support_plan_statuses_cycle_latest',
    'idx_welfare_recipients_furigana',
    'idx_office_welfare_recipients_office'
)
ORDER BY indexname;

-- ================================================================
-- ロールバック用SQL（必要に応じて実行）
-- ================================================================
-- DROP INDEX CONCURRENTLY IF EXISTS idx_office_welfare_recipients_office;
-- DROP INDEX CONCURRENTLY IF EXISTS idx_welfare_recipients_furigana;
-- DROP INDEX CONCURRENTLY IF EXISTS idx_support_plan_statuses_cycle_latest;
-- DROP INDEX CONCURRENTLY IF EXISTS idx_support_plan_cycles_recipient_latest;
