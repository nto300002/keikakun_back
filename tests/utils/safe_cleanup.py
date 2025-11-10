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

        # 本番環境のキーワードチェック
        production_keywords = ['prod', 'production', 'main', 'live']
        if any(keyword in db_url.lower() for keyword in production_keywords):
            logger.error(f"Production database detected in URL: {db_url}")
            return False

        return True

    @staticmethod
    async def delete_factory_generated_data(db: AsyncSession) -> Dict[str, int]:
        """
        conftest.pyのファクトリ関数で生成されたデータのみを削除

        識別方法（命名規則ベース）:
        - Staff: email が '@test.com' で終わる、または 'テスト' を含む
        - Office: name が 'テスト事業所' を含む
        - WelfareRecipient: first_name または last_name が 'テスト' を含む

        Args:
            db: データベースセッション

        Returns:
            削除されたテーブルとレコード数の辞書
        """
        result = {}

        try:
            # 1. テスト事業所のIDを先に取得
            office_ids_query = text("""
                SELECT id FROM offices
                WHERE name LIKE '%テスト事業所%'
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

                # 1-5. role_change_requests を削除
                rcr_result = await db.execute(
                    text("DELETE FROM role_change_requests WHERE office_id = ANY(:office_ids)"),
                    {"office_ids": list(test_office_ids)}
                )
                if rcr_result.rowcount > 0:
                    result["role_change_requests"] = rcr_result.rowcount

                # 1-6. employee_action_requests を削除
                ear_result = await db.execute(
                    text("DELETE FROM employee_action_requests WHERE office_id = ANY(:office_ids)"),
                    {"office_ids": list(test_office_ids)}
                )
                if ear_result.rowcount > 0:
                    result["employee_action_requests"] = ear_result.rowcount

            # 2. テスト事業所を削除
            office_result = await db.execute(
                text("""
                    DELETE FROM offices
                    WHERE name LIKE '%テスト事業所%'
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
