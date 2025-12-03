"""
物理削除クリーンアップサービス

論理削除から30日経過したレコードを物理削除するバッチ処理
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from typing import Dict, Any
import logging

from app.models.staff import Staff
from app.models.office import Office, OfficeStaff

logger = logging.getLogger(__name__)


class CleanupService:
    """論理削除レコードの物理削除サービス"""

    async def cleanup_soft_deleted_records(
        self,
        db: AsyncSession,
        days_threshold: int = 30
    ) -> Dict[str, Any]:
        """
        論理削除から指定日数経過したレコードを物理削除

        Args:
            db: データベースセッション
            days_threshold: 論理削除からの経過日数（デフォルト30日）

        Returns:
            削除結果のサマリー
        """
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        result = {
            "threshold_date": threshold_date,
            "deleted_staff_count": 0,
            "deleted_office_count": 0,
            "deleted_archive_count": 0,
            "errors": []
        }

        try:
            # スタッフの物理削除
            staff_count = await self._cleanup_staff(db, threshold_date)
            result["deleted_staff_count"] = staff_count

            # 事務所の物理削除
            office_count = await self._cleanup_offices(db, threshold_date)
            result["deleted_office_count"] = office_count

            # アーカイブの削除（法定保存期限切れ）
            archive_count = await self._cleanup_expired_archives(db)
            result["deleted_archive_count"] = archive_count

            # 監査ログは記録しない（staff_idが必須のため）
            # ログはlogger経由で記録される

            await db.commit()

            logger.info(
                f"Physical deletion completed: "
                f"{staff_count} staff, {office_count} offices, "
                f"{result['deleted_archive_count']} archives deleted"
            )

        except Exception as e:
            await db.rollback()
            error_msg = f"Cleanup failed: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            raise

        return result

    async def _cleanup_staff(
        self,
        db: AsyncSession,
        threshold_date: datetime
    ) -> int:
        """
        論理削除から指定日数経過したスタッフを物理削除

        Args:
            db: データベースセッション
            threshold_date: 閾値日時（これより前に削除されたレコードを対象）

        Returns:
            削除されたレコード数
        """
        # 削除対象のスタッフを取得
        stmt = select(Staff).where(
            and_(
                Staff.is_deleted == True,
                Staff.deleted_at.isnot(None),
                Staff.deleted_at <= threshold_date
            )
        )
        result = await db.execute(stmt)
        staff_to_delete = result.scalars().all()

        if not staff_to_delete:
            return 0

        # 監査ログに記録（物理削除前）
        staff_ids_to_delete = []
        for staff in staff_to_delete:
            staff_ids_to_delete.append(staff.id)
            logger.info(
                f"Physically deleting staff: id={staff.id}, "
                f"email={staff.email}, deleted_at={staff.deleted_at}"
            )

        # 関連するOfficeStaffレコードを先に削除
        if staff_ids_to_delete:
            office_staff_delete_stmt = delete(OfficeStaff).where(
                OfficeStaff.staff_id.in_(staff_ids_to_delete)
            )
            await db.execute(office_staff_delete_stmt)

        # 物理削除実行
        delete_stmt = delete(Staff).where(
            and_(
                Staff.is_deleted == True,
                Staff.deleted_at.isnot(None),
                Staff.deleted_at <= threshold_date
            )
        )
        delete_result = await db.execute(delete_stmt)

        return delete_result.rowcount

    async def _cleanup_offices(
        self,
        db: AsyncSession,
        threshold_date: datetime
    ) -> int:
        """
        論理削除から指定日数経過した事務所を物理削除

        Args:
            db: データベースセッション
            threshold_date: 閾値日時（これより前に削除されたレコードを対象）

        Returns:
            削除されたレコード数
        """
        # 削除対象の事務所を取得
        stmt = select(Office).where(
            and_(
                Office.is_deleted == True,
                Office.deleted_at.isnot(None),
                Office.deleted_at <= threshold_date
            )
        )
        result = await db.execute(stmt)
        offices_to_delete = result.scalars().all()

        if not offices_to_delete:
            return 0

        # 監査ログに記録（物理削除前）
        office_ids_to_delete = []
        for office in offices_to_delete:
            office_ids_to_delete.append(office.id)
            logger.info(
                f"Physically deleting office: id={office.id}, "
                f"name={office.name}, deleted_at={office.deleted_at}"
            )

        # 関連するOfficeStaffレコードを先に削除
        if office_ids_to_delete:
            office_staff_delete_stmt = delete(OfficeStaff).where(
                OfficeStaff.office_id.in_(office_ids_to_delete)
            )
            await db.execute(office_staff_delete_stmt)

        # 物理削除実行
        delete_stmt = delete(Office).where(
            and_(
                Office.is_deleted == True,
                Office.deleted_at.isnot(None),
                Office.deleted_at <= threshold_date
            )
        )
        delete_result = await db.execute(delete_stmt)

        return delete_result.rowcount

    async def _cleanup_expired_archives(
        self,
        db: AsyncSession
    ) -> int:
        """
        法定保存期限が過ぎたアーカイブを削除

        Args:
            db: データベースセッション

        Returns:
            削除されたレコード数
        """
        from app.crud.crud_archived_staff import crud_archived_staff as archived_staff

        # 削除対象のアーカイブを取得
        count = await archived_staff.delete_expired_archives(
            db,
            exclude_test_data=True
        )

        if count > 0:
            logger.info(
                f"Expired archives cleanup: {count} archives deleted"
            )

        return count


# シングルトンインスタンス
cleanup_service = CleanupService()
