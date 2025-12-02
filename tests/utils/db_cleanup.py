"""
テストデータベースクリーンアップユーティリティ

テスト実行前後にデータベースをクリーンな状態に保つための機能を提供
"""
import logging
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DatabaseCleanup:
    """データベースクリーンアップ機能を提供するクラス"""

    @staticmethod
    async def truncate_all_tables(db: AsyncSession) -> Dict[str, int]:
        """
        すべてのテーブルをDELETEで削除する（TRUNCATEの代替）

        注意: これは不可逆的な操作です。テストデータベースでのみ使用してください。

        Args:
            db: データベースセッション

        Returns:
            削除されたテーブルと削除前のレコード数の辞書
        """
        result = {}

        # 削除対象のテーブル（依存関係の逆順）
        tables_to_delete = [
            "plan_deliverables",
            "support_plan_statuses",
            "support_plan_cycles",
            "calendar_event_series",
            "calendar_events",
            "office_calendar_accounts",
            "notices",
            "approval_requests",  # 統合テーブル（旧: role_change_requests, employee_action_requests）
            "office_welfare_recipients",
            "welfare_recipients",
            "office_staffs",
            "offices",
            "staffs",
        ]

        try:
            for table in tables_to_delete:
                # 削除前のカウント
                count_query = text(f"SELECT COUNT(*) FROM {table}")
                count_result = await db.execute(count_query)
                count = count_result.scalar()

                if count > 0:
                    # DELETEを使用して全レコードを削除
                    delete_query = text(f"DELETE FROM {table}")
                    await db.execute(delete_query)
                    result[table] = count
                    logger.info(f"Deleted all from {table}: {count} records")

            await db.commit()
            logger.info(f"Successfully deleted all data from {len(result)} tables")

        except Exception as e:
            await db.rollback()
            logger.error(f"Error during delete all: {e}")
            raise

        return result

    @staticmethod
    async def delete_test_data(db: AsyncSession) -> Dict[str, int]:
        """
        テストで作成されたデータのみを削除する（選択的削除）

        conftest.pyで作成される「テスト」という名前を含むデータを削除します。

        Args:
            db: データベースセッション

        Returns:
            削除されたテーブルと削除されたレコード数の辞書
        """
        result = {}

        try:
            # 0. テスト事業所のIDを先に取得
            # 解決策C: is_test_dataフラグも条件に含める（後でofficesを削除する際の条件と一致させる）
            office_ids_query = text("""
                SELECT id FROM offices
                WHERE is_test_data = TRUE
                   OR name LIKE '%テスト%'
                   OR name LIKE '%test%'
                   OR name LIKE '%Test%'
            """)
            office_ids_result = await db.execute(office_ids_query)
            test_office_ids = [row[0] for row in office_ids_result.fetchall()]

            if test_office_ids:
                # 0-0. 福祉受給者関連の支援計画データを先に削除（外部キー制約対応）
                # まず、対象事業所の福祉受給者IDを取得
                welfare_ids_query = text("""
                    SELECT welfare_recipient_id FROM office_welfare_recipients
                    WHERE office_id = ANY(:office_ids)
                """)
                welfare_ids_result = await db.execute(
                    welfare_ids_query,
                    {"office_ids": list(test_office_ids)}
                )
                related_welfare_ids = [row[0] for row in welfare_ids_result.fetchall()]

                if related_welfare_ids:
                    # plan_deliverables を先に削除（plan_cycle_id経由で）
                    await db.execute(
                        text("""
                            DELETE FROM plan_deliverables
                            WHERE plan_cycle_id IN (
                                SELECT id FROM support_plan_cycles
                                WHERE welfare_recipient_id = ANY(:ids)
                            )
                        """),
                        {"ids": list(related_welfare_ids)}
                    )

                    # support_plan_statuses を削除（office_id経由）
                    await db.execute(
                        text("DELETE FROM support_plan_statuses WHERE office_id = ANY(:office_ids)"),
                        {"office_ids": list(test_office_ids)}
                    )

                    # support_plan_cycles を削除（office_id経由）
                    await db.execute(
                        text("DELETE FROM support_plan_cycles WHERE office_id = ANY(:office_ids)"),
                        {"office_ids": list(test_office_ids)}
                    )

                # 0-1. office_staffsを削除
                delete_office_staffs = text("""
                    DELETE FROM office_staffs
                    WHERE office_id = ANY(:office_ids)
                """)
                os_result = await db.execute(
                    delete_office_staffs,
                    {"office_ids": list(test_office_ids)}
                )
                if os_result.rowcount > 0:
                    result["office_staffs"] = os_result.rowcount
                    logger.info(f"Deleted {os_result.rowcount} office_staffs")

                # 0-2. office_welfare_recipientsを削除
                delete_office_recipients = text("""
                    DELETE FROM office_welfare_recipients
                    WHERE office_id = ANY(:office_ids)
                """)
                owr_result = await db.execute(
                    delete_office_recipients,
                    {"office_ids": list(test_office_ids)}
                )
                if owr_result.rowcount > 0:
                    result["office_welfare_recipients"] = owr_result.rowcount
                    logger.info(f"Deleted {owr_result.rowcount} office_welfare_recipients")

                # 0-3. その他の関連データを削除
                # notices
                delete_notices = text("""
                    DELETE FROM notices
                    WHERE office_id = ANY(:office_ids)
                """)
                notices_result = await db.execute(
                    delete_notices,
                    {"office_ids": list(test_office_ids)}
                )
                if notices_result.rowcount > 0:
                    result["notices"] = notices_result.rowcount
                    logger.info(f"Deleted {notices_result.rowcount} notices")

                # approval_requests（統合テーブル）
                delete_apr = text("""
                    DELETE FROM approval_requests
                    WHERE office_id = ANY(:office_ids)
                """)
                apr_result = await db.execute(
                    delete_apr,
                    {"office_ids": list(test_office_ids)}
                )
                if apr_result.rowcount > 0:
                    result["approval_requests"] = apr_result.rowcount
                    logger.info(f"Deleted {apr_result.rowcount} approval_requests")

            # 1. テスト事業所の削除（関連データ削除後）
            # 解決策C: is_test_dataフラグも条件に含める
            office_query = text("""
                DELETE FROM offices
                WHERE is_test_data = TRUE
                   OR name LIKE '%テスト%'
                   OR name LIKE '%test%'
                   OR name LIKE '%Test%'
                RETURNING id
            """)
            office_result = await db.execute(office_query)
            deleted_offices = office_result.fetchall()
            if deleted_offices:
                result["offices"] = len(deleted_offices)
                logger.info(f"Deleted {len(deleted_offices)} test offices")

            # 2. テストスタッフの削除（外部キー制約のため、再割当が必要）
            # まず、削除対象のスタッフIDを取得
            staff_query = text("""
                SELECT id FROM staffs
                WHERE full_name LIKE '%テスト%'
                   OR full_name LIKE '%test%'
                   OR full_name LIKE '%Test%'
                   OR email LIKE '%test%'
                   OR email LIKE '%example.com%'
            """)
            staff_result = await db.execute(staff_query)
            target_staff_ids = [row[0] for row in staff_result.fetchall()]

            if target_staff_ids:
                # 再割当先のスタッフを取得（削除対象外のowner）
                replacement_query = text("""
                    SELECT s.id FROM staffs s
                    INNER JOIN office_staffs os ON s.id = os.staff_id
                    WHERE s.role = 'owner'
                      AND s.id != ALL(:target_ids)
                      AND (s.full_name IS NULL OR s.full_name NOT LIKE '%テスト%')
                    LIMIT 1
                """)
                replacement_result = await db.execute(
                    replacement_query,
                    {"target_ids": list(target_staff_ids)}
                )
                replacement_staff = replacement_result.fetchone()

                if replacement_staff:
                    replacement_id = replacement_staff[0]

                    # offices.created_by を再割当
                    await db.execute(
                        text("""
                            UPDATE offices
                            SET created_by = :replacement_id
                            WHERE created_by = ANY(:target_ids)
                        """),
                        {
                            "replacement_id": replacement_id,
                            "target_ids": list(target_staff_ids)
                        }
                    )

                    # offices.last_modified_by を再割当
                    await db.execute(
                        text("""
                            UPDATE offices
                            SET last_modified_by = :replacement_id
                            WHERE last_modified_by = ANY(:target_ids)
                        """),
                        {
                            "replacement_id": replacement_id,
                            "target_ids": list(target_staff_ids)
                        }
                    )
                else:
                    # 解決策C: replacement staffが見つからない場合、
                    # 削除対象staffを参照しているofficesを先に削除
                    offices_to_delete = await db.execute(
                        text("""
                            DELETE FROM offices
                            WHERE created_by = ANY(:target_ids)
                               OR last_modified_by = ANY(:target_ids)
                            RETURNING id
                        """),
                        {"target_ids": list(target_staff_ids)}
                    )
                    deleted_office_count = len(offices_to_delete.fetchall())
                    if deleted_office_count > 0:
                        logger.info(
                            f"Deleted {deleted_office_count} offices referencing target staffs "
                            "(no replacement staff found)"
                        )

                # スタッフを削除（CASCADE）
                delete_staff_query = text("""
                    DELETE FROM staffs
                    WHERE id = ANY(:target_ids)
                """)
                await db.execute(
                    delete_staff_query,
                    {"target_ids": list(target_staff_ids)}
                )
                result["staffs"] = len(target_staff_ids)
                logger.info(f"Deleted {len(target_staff_ids)} test staff")

            # 3. 通知の削除
            notice_query = text("""
                DELETE FROM notices
                WHERE title LIKE '%テスト%' OR title LIKE '%test%'
            """)
            notice_result = await db.execute(notice_query)
            if notice_result.rowcount > 0:
                result["notices"] = notice_result.rowcount
                logger.info(f"Deleted {notice_result.rowcount} test notices")

            # 4. テスト福祉受給者の削除（CASCADE制約あり）
            # まず関連する支援計画のデータを削除
            welfare_query = text("""
                SELECT id FROM welfare_recipients
                WHERE first_name LIKE '%テスト%'
                   OR last_name LIKE '%テスト%'
                   OR first_name LIKE '%test%'
                   OR last_name LIKE '%test%'
                   OR first_name LIKE '%Test%'
                   OR last_name LIKE '%Test%'
            """)
            welfare_result = await db.execute(welfare_query)
            target_welfare_ids = [row[0] for row in welfare_result.fetchall()]

            if target_welfare_ids:
                # plan_deliverables を削除（support_plan_cycles経由）
                await db.execute(
                    text("""
                        DELETE FROM plan_deliverables
                        WHERE plan_cycle_id IN (
                            SELECT id FROM support_plan_cycles
                            WHERE welfare_recipient_id = ANY(:ids)
                        )
                    """),
                    {"ids": list(target_welfare_ids)}
                )

                # support_plan_statuses を削除
                # support_plan_statusesはwelfare_recipient_idを持っていない可能性があるため、
                # 実際のカラム名を確認して削除
                await db.execute(
                    text("""
                        DELETE FROM support_plan_statuses
                        WHERE id IN (
                            SELECT sps.id FROM support_plan_statuses sps
                            INNER JOIN support_plan_cycles spc ON sps.plan_cycle_id = spc.id
                            WHERE spc.welfare_recipient_id = ANY(:ids)
                        )
                    """),
                    {"ids": list(target_welfare_ids)}
                )

                # support_plan_cycles を削除
                await db.execute(
                    text("DELETE FROM support_plan_cycles WHERE welfare_recipient_id = ANY(:ids)"),
                    {"ids": list(target_welfare_ids)}
                )

                # 福祉受給者本体を削除（CASCADE）
                delete_welfare_query = text("""
                    DELETE FROM welfare_recipients
                    WHERE id = ANY(:ids)
                """)
                welfare_delete_result = await db.execute(
                    delete_welfare_query,
                    {"ids": list(target_welfare_ids)}
                )
                result["welfare_recipients"] = welfare_delete_result.rowcount
                logger.info(f"Deleted {welfare_delete_result.rowcount} test welfare recipients")

            await db.commit()
            logger.info(f"Successfully deleted test data from {len(result)} tables")

        except Exception as e:
            await db.rollback()
            logger.error(f"Error during test data deletion: {e}")
            raise

        return result

    @staticmethod
    async def get_table_counts(db: AsyncSession) -> Dict[str, int]:
        """
        すべてのテーブルのレコード数を取得

        Args:
            db: データベースセッション

        Returns:
            テーブル名とレコード数の辞書
        """
        tables = [
            "offices",
            "staffs",
            "office_staffs",
            "approval_requests",  # 統合テーブル（旧: role_change_requests, employee_action_requests）
            "notices",
            "welfare_recipients",
            "office_welfare_recipients",
            "calendar_events",
            "calendar_event_series",
            "office_calendar_accounts",
            "support_plan_cycles",
            "support_plan_statuses",
            "plan_deliverables",
        ]

        counts = {}
        for table in tables:
            query = text(f"SELECT COUNT(*) FROM {table}")
            result = await db.execute(query)
            counts[table] = result.scalar()

        return counts

    @staticmethod
    async def verify_clean_state(db: AsyncSession) -> tuple[bool, Dict[str, int]]:
        """
        データベースがクリーンな状態か確認

        Args:
            db: データベースセッション

        Returns:
            (クリーンかどうか, テーブルごとのレコード数)
        """
        counts = await DatabaseCleanup.get_table_counts(db)
        is_clean = all(count == 0 for count in counts.values())
        return is_clean, counts

    @staticmethod
    def format_cleanup_report(counts: Dict[str, int]) -> str:
        """
        クリーンアップレポートを整形

        Args:
            counts: テーブル名とレコード数の辞書

        Returns:
            整形されたレポート文字列
        """
        report = "\n=== Database Cleanup Report ===\n"

        if not counts:
            report += "No data was deleted.\n"
        else:
            total = sum(counts.values())
            report += f"Total records deleted: {total}\n\n"
            report += "Breakdown by table:\n"
            for table, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    report += f"  {table}: {count}\n"

        report += "=" * 31 + "\n"
        return report


# グローバルインスタンス
db_cleanup = DatabaseCleanup()
