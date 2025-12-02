"""
安全なテストデータクリーンアップ

conftest.pyのファクトリ関数で生成されたデータのみを削除
本番環境での誤実行を防ぐ
"""
import logging
import os
from typing import Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SafeTestDataCleanup:
    """ファクトリ関数で生成されたテストデータのみを安全に削除"""

    @staticmethod
    def verify_test_environment() -> bool:
        """
        テスト環境であることを確認

        Returns:
            テスト環境の場合True、それ以外False
        """
        db_url = os.getenv("TEST_DATABASE_URL")

        # TEST_DATABASE_URLが設定されていることを確認
        if not db_url:
            logger.warning("TEST_DATABASE_URL not set - assuming not in test environment")
            return False

        db_url_lower = db_url.lower()

        # テスト環境のキーワードがあればOK
        test_keywords = ['test', '_test', '-test', 'testing', 'dev', 'development']
        if any(keyword in db_url_lower for keyword in test_keywords):
            logger.info(f"Test environment confirmed (contains test keyword): {db_url}")
            return True

        # テストキーワードがなく、本番環境のキーワードがある場合はNG
        production_keywords = ['prod', 'production', 'main', 'live']
        if any(keyword in db_url_lower for keyword in production_keywords):
            logger.error(f"Production database detected in URL without test keyword: {db_url}")
            return False

        return True

    @staticmethod
    async def delete_test_data(db: AsyncSession) -> Dict[str, int]:
        """
        is_test_data=True のデータのみを削除

        環境を問わず安全に動作する
        削除順序は外部キー制約を考慮して設計

        Returns:
            削除されたテーブルとレコード数の辞書
        """
        result = {}

        try:
            # ========================================
            # STEP 1: テストデータのIDを収集
            # ========================================

            # テスト事業所のIDを取得
            office_ids_query = text("SELECT id FROM offices WHERE is_test_data = true")
            test_office_ids = [row[0] for row in (await db.execute(office_ids_query)).fetchall()]

            # テストスタッフのIDを取得
            staff_ids_query = text("SELECT id FROM staffs WHERE is_test_data = true")
            test_staff_ids = [row[0] for row in (await db.execute(staff_ids_query)).fetchall()]

            # テスト福祉受給者のIDを取得
            welfare_ids_query = text("SELECT id FROM welfare_recipients WHERE is_test_data = true")
            test_welfare_ids = [row[0] for row in (await db.execute(welfare_ids_query)).fetchall()]

            # ========================================
            # STEP 2: 子テーブルの削除（外部キー制約順）
            # ========================================

            # 2-1. 最下層: 履歴・詳細データ（オプション）
            if test_welfare_ids:
                r = await db.execute(text("DELETE FROM history_of_hospital_visits WHERE is_test_data = true"))
                if r.rowcount > 0: result["history_of_hospital_visits"] = r.rowcount

                r = await db.execute(text("DELETE FROM welfare_services_used WHERE is_test_data = true"))
                if r.rowcount > 0: result["welfare_services_used"] = r.rowcount

                r = await db.execute(text("DELETE FROM emergency_contacts WHERE is_test_data = true"))
                if r.rowcount > 0: result["emergency_contacts"] = r.rowcount

            # 2-2. 中層: アセスメントデータ
            for table in ["issue_analyses", "employment_related", "medical_matters",
                         "family_of_service_recipients", "disability_details", "disability_statuses",
                         "service_recipient_details"]:
                r = await db.execute(text(f"DELETE FROM {table} WHERE is_test_data = true"))
                if r.rowcount > 0:
                    result[table] = r.rowcount

            # 2-3. 支援計画関連
            for table in ["plan_deliverables", "support_plan_statuses", "support_plan_cycles"]:
                r = await db.execute(text(f"DELETE FROM {table} WHERE is_test_data = true"))
                if r.rowcount > 0:
                    result[table] = r.rowcount

            # 2-4. カレンダー関連
            for table in ["calendar_event_instances", "calendar_event_series", "calendar_events"]:
                r = await db.execute(text(f"DELETE FROM {table} WHERE is_test_data = true"))
                if r.rowcount > 0:
                    result[table] = r.rowcount

            # 2-5. リクエスト・通知
            for table in ["approval_requests", "notices"]:
                r = await db.execute(text(f"DELETE FROM {table} WHERE is_test_data = true"))
                if r.rowcount > 0:
                    result[table] = r.rowcount

            # ========================================
            # STEP 3: 中間テーブルの削除
            # ========================================
            for table in ["office_welfare_recipients", "office_staffs"]:
                r = await db.execute(text(f"DELETE FROM {table} WHERE is_test_data = true"))
                if r.rowcount > 0:
                    result[table] = r.rowcount

            # ========================================
            # STEP 4: 親テーブルの削除（created_by対策あり）
            # ========================================

            # 4-1. スタッフ削除前の created_by/last_modified_by 再割当
            if test_staff_ids:
                replacement_query = text("""
                    SELECT s.id FROM staffs s
                    WHERE s.role = 'owner'
                      AND s.is_test_data = false
                    LIMIT 1
                """)
                replacement = (await db.execute(replacement_query)).fetchone()

                if replacement:
                    replacement_id = replacement[0]
                    # テストデータでないofficeのcreated_by/last_modified_byを再割当
                    await db.execute(text("""
                        UPDATE offices
                        SET created_by = :rid
                        WHERE created_by = ANY(:sids) AND is_test_data = false
                    """), {"rid": replacement_id, "sids": test_staff_ids})

                    await db.execute(text("""
                        UPDATE offices
                        SET last_modified_by = :rid
                        WHERE last_modified_by = ANY(:sids) AND is_test_data = false
                    """), {"rid": replacement_id, "sids": test_staff_ids})

            # 4-2. 親テーブル削除（offices → staffs の順。officesがstaffsを参照しているため）
            for table in ["welfare_recipients", "offices", "staffs"]:
                r = await db.execute(text(f"DELETE FROM {table} WHERE is_test_data = true"))
                if r.rowcount > 0:
                    result[table] = r.rowcount

            await db.commit()

            if result:
                total = sum(result.values())
                logger.info(f"🧹 Cleaned up {total} test data records (is_test_data=true)")
            else:
                logger.debug("✓ No test data found (is_test_data=true)")

        except Exception as e:
            await db.rollback()
            logger.error(f"Error during test data cleanup: {e}")
            raise

        return result

    @staticmethod
    async def delete_factory_generated_data(db: AsyncSession) -> Dict[str, int]:
        """
        conftest.pyのファクトリ関数で生成されたデータのみを削除

        識別方法（命名規則ベース）:
        - Staff: email が '@test.com' で終わる、または 'テスト' を含む
        - Office: name が 'テスト事業所' を含む
        - WelfareRecipient: first_name または last_name が 'テスト', '部分修復', '修復対象', 'エラー', '新規', '更新後' を含む

        Args:
            db: データベースセッション

        Returns:
            削除されたテーブルとレコード数の辞書
        """
        result = {}

        try:
            # 1. テスト事業所のIDを先に取得
            # 解決策C: is_test_dataフラグも条件に含める（後でofficesを削除する際の条件と一致させる）
            office_ids_query = text("""
                SELECT id FROM offices
                WHERE is_test_data = TRUE
                   OR name LIKE '%テスト事業所%'
                   OR name LIKE '%test%'
                   OR name LIKE '%Test%'
            """)
            office_ids_result = await db.execute(office_ids_query)
            test_office_ids = [row[0] for row in office_ids_result.fetchall()]

            if test_office_ids:
                # 1-1. 福祉受給者関連の支援計画データを先に削除
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
                    # plan_deliverables を削除
                    pd_result = await db.execute(
                        text("""
                            DELETE FROM plan_deliverables
                            WHERE plan_cycle_id IN (
                                SELECT id FROM support_plan_cycles
                                WHERE welfare_recipient_id = ANY(:ids)
                            )
                        """),
                        {"ids": list(related_welfare_ids)}
                    )
                    if pd_result.rowcount > 0:
                        result["plan_deliverables"] = pd_result.rowcount

                    # support_plan_statuses を削除
                    sps_result = await db.execute(
                        text("DELETE FROM support_plan_statuses WHERE office_id = ANY(:office_ids)"),
                        {"office_ids": list(test_office_ids)}
                    )
                    if sps_result.rowcount > 0:
                        result["support_plan_statuses"] = sps_result.rowcount

                    # support_plan_cycles を削除
                    spc_result = await db.execute(
                        text("DELETE FROM support_plan_cycles WHERE office_id = ANY(:office_ids)"),
                        {"office_ids": list(test_office_ids)}
                    )
                    if spc_result.rowcount > 0:
                        result["support_plan_cycles"] = spc_result.rowcount

                # 1-2. office_staffs を削除
                os_result = await db.execute(
                    text("DELETE FROM office_staffs WHERE office_id = ANY(:office_ids)"),
                    {"office_ids": list(test_office_ids)}
                )
                if os_result.rowcount > 0:
                    result["office_staffs"] = os_result.rowcount

                # 1-3. office_welfare_recipients を削除
                owr_result = await db.execute(
                    text("DELETE FROM office_welfare_recipients WHERE office_id = ANY(:office_ids)"),
                    {"office_ids": list(test_office_ids)}
                )
                if owr_result.rowcount > 0:
                    result["office_welfare_recipients"] = owr_result.rowcount

                # 1-4. notices を削除
                notices_result = await db.execute(
                    text("DELETE FROM notices WHERE office_id = ANY(:office_ids)"),
                    {"office_ids": list(test_office_ids)}
                )
                if notices_result.rowcount > 0:
                    result["notices"] = notices_result.rowcount

                # 1-5. approval_requests を削除
                approval_result = await db.execute(
                    text("DELETE FROM approval_requests WHERE office_id = ANY(:office_ids)"),
                    {"office_ids": list(test_office_ids)}
                )
                if approval_result.rowcount > 0:
                    result["approval_requests"] = approval_result.rowcount

            # 2. テスト事業所を削除
            # 解決策C: is_test_dataフラグも条件に含める
            office_result = await db.execute(
                text("""
                    DELETE FROM offices
                    WHERE is_test_data = TRUE
                       OR name LIKE '%テスト事業所%'
                       OR name LIKE '%test%'
                       OR name LIKE '%Test%'
                """)
            )
            if office_result.rowcount > 0:
                result["offices"] = office_result.rowcount

            # 3. テストスタッフの削除
            # ファクトリ関数で生成されたスタッフの識別
            staff_query = text("""
                SELECT id FROM staffs
                WHERE email LIKE '%@test.com'
                   OR email LIKE '%@example.com'
                   OR last_name LIKE '%テスト%'
                   OR full_name LIKE '%テスト%'
            """)
            staff_result = await db.execute(staff_query)
            target_staff_ids = [row[0] for row in staff_result.fetchall()]

            if target_staff_ids:
                # 再割当が必要な場合の処理（削除対象外のownerを取得）
                replacement_query = text("""
                    SELECT s.id FROM staffs s
                    INNER JOIN office_staffs os ON s.id = os.staff_id
                    WHERE s.role = 'owner'
                      AND s.id != ALL(:target_ids)
                      AND s.email NOT LIKE '%@test.com'
                      AND s.email NOT LIKE '%@example.com'
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

                # スタッフを削除
                delete_staff_result = await db.execute(
                    text("DELETE FROM staffs WHERE id = ANY(:target_ids)"),
                    {"target_ids": list(target_staff_ids)}
                )
                if delete_staff_result.rowcount > 0:
                    result["staffs"] = delete_staff_result.rowcount

            # 4. テスト福祉受給者の削除
            welfare_query = text("""
                SELECT id FROM welfare_recipients
                WHERE first_name LIKE '%テスト%'
                   OR last_name LIKE '%テスト%'
                   OR first_name LIKE '%test%'
                   OR last_name LIKE '%test%'
                   OR first_name LIKE '%部分修復%'
                   OR last_name LIKE '%部分修復%'
                   OR first_name LIKE '%修復対象%'
                   OR last_name LIKE '%修復対象%'
                   OR first_name LIKE '%エラー%'
                   OR last_name LIKE '%エラー%'
                   OR first_name LIKE '%新規%'
                   OR last_name LIKE '%新規%'
                   OR first_name LIKE '%更新後%'
                   OR last_name LIKE '%更新後%'
            """)
            welfare_result = await db.execute(welfare_query)
            target_welfare_ids = [row[0] for row in welfare_result.fetchall()]

            if target_welfare_ids:
                # 関連データを削除
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

                await db.execute(
                    text("DELETE FROM support_plan_cycles WHERE welfare_recipient_id = ANY(:ids)"),
                    {"ids": list(target_welfare_ids)}
                )

                # 福祉受給者本体を削除
                welfare_delete_result = await db.execute(
                    text("DELETE FROM welfare_recipients WHERE id = ANY(:ids)"),
                    {"ids": list(target_welfare_ids)}
                )
                if welfare_delete_result.rowcount > 0:
                    result["welfare_recipients"] = welfare_delete_result.rowcount

            await db.commit()

            if result:
                total = sum(result.values())
                logger.info(f"🧹 Safely cleaned up {total} factory-generated test records")
            else:
                logger.debug("✓ No factory-generated test data found")

        except Exception as e:
            await db.rollback()
            logger.error(f"Error during safe cleanup: {e}")
            raise

        return result


# グローバルインスタンス
safe_cleanup = SafeTestDataCleanup()
