"""
アーカイブスタッフのCRUD操作

法定保存義務に基づくスタッフアーカイブの作成・管理を行う。
個人情報を匿名化し、法定保存が必要なデータのみを保存する。
"""
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.archived_staff import ArchivedStaff
from app.models.staff import Staff


class CRUDArchivedStaff:
    """アーカイブスタッフのCRUD操作"""

    def _generate_anonymized_id(self, staff_id: uuid.UUID) -> str:
        """
        スタッフIDから匿名化IDを生成

        Args:
            staff_id: 元のスタッフID

        Returns:
            匿名化ID（例: ABC123DEF）
        """
        # SHA-256ハッシュの先頭9文字を使用
        hash_hex = hashlib.sha256(str(staff_id).encode()).hexdigest()
        return hash_hex[:9].upper()

    async def create_from_staff(
        self,
        db: AsyncSession,
        *,
        staff: Staff,
        reason: str,
        deleted_by: uuid.UUID
    ) -> ArchivedStaff:
        """
        Staffレコードからアーカイブを作成

        個人識別情報を匿名化し、法定保存が必要なデータのみを保存する。

        Args:
            db: データベースセッション
            staff: アーカイブ対象のスタッフ
            reason: アーカイブ理由（staff_deletion/staff_withdrawal/office_withdrawal）
            deleted_by: 削除実行者のスタッフID

        Returns:
            作成されたアーカイブレコード
        """
        # 匿名化ID生成
        anon_id = self._generate_anonymized_id(staff.id)

        # 事務所情報取得（スナップショット）
        office_id = None
        office_name = None
        try:
            if staff.office_associations:
                # プライマリ事務所を優先
                primary_assoc = next(
                    (assoc for assoc in staff.office_associations if assoc.is_primary),
                    None
                )
                if primary_assoc and primary_assoc.office:
                    office_id = primary_assoc.office.id
                    office_name = primary_assoc.office.name
                elif staff.office_associations:
                    # プライマリがなければ最初の事務所
                    first_assoc = staff.office_associations[0]
                    if first_assoc.office:
                        office_id = first_assoc.office.id
                        office_name = first_assoc.office.name
        except Exception:
            # リレーションシップがロードされていない場合はNone
            pass

        # 退職日（deleted_atまたは現在日時）
        terminated_at = staff.deleted_at or datetime.now(timezone.utc)

        # 法定保存期限を計算（退職日 + 5年）
        retention_until = ArchivedStaff.calculate_retention_until(terminated_at, years=5)

        # メタデータ
        metadata_dict = {
            "deleted_by_staff_id": str(deleted_by),
            "original_email_domain": staff.email.split("@")[1] if "@" in staff.email else None,
            "mfa_was_enabled": staff.is_mfa_enabled,
            "is_email_verified": staff.is_email_verified,
        }

        # アーカイブレコード作成
        archived_staff = ArchivedStaff(
            original_staff_id=staff.id,
            anonymized_full_name=f"スタッフ-{anon_id}",
            anonymized_email=f"archived-{anon_id}@deleted.local",
            role=staff.role.value,
            office_id=office_id,
            office_name=office_name,
            hired_at=staff.created_at,
            terminated_at=terminated_at,
            archive_reason=reason,
            legal_retention_until=retention_until,
            metadata_=metadata_dict,
            is_test_data=staff.is_test_data if hasattr(staff, 'is_test_data') else False
        )

        db.add(archived_staff)
        await db.flush()
        await db.refresh(archived_staff)

        return archived_staff

    async def get(
        self,
        db: AsyncSession,
        *,
        archive_id: uuid.UUID
    ) -> Optional[ArchivedStaff]:
        """
        IDでアーカイブを取得

        Args:
            db: データベースセッション
            archive_id: アーカイブID

        Returns:
            アーカイブレコード、または None
        """
        stmt = select(ArchivedStaff).where(ArchivedStaff.id == archive_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_original_staff_id(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID
    ) -> Optional[ArchivedStaff]:
        """
        元のスタッフIDでアーカイブを取得

        Args:
            db: データベースセッション
            staff_id: 元のスタッフID

        Returns:
            アーカイブレコード、または None
        """
        stmt = select(ArchivedStaff).where(
            ArchivedStaff.original_staff_id == staff_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        office_id: Optional[uuid.UUID] = None,
        archive_reason: Optional[str] = None,
        exclude_test_data: bool = True
    ) -> Tuple[List[ArchivedStaff], int]:
        """
        アーカイブリストを取得（フィルタリング・ページネーション対応）

        Args:
            db: データベースセッション
            skip: スキップ件数
            limit: 取得件数
            office_id: 事務所IDでフィルタリング（オプション）
            archive_reason: アーカイブ理由でフィルタリング（オプション）
            exclude_test_data: テストデータを除外するか

        Returns:
            (アーカイブリスト, 総件数)
        """
        # 基本クエリ
        stmt = select(ArchivedStaff)
        count_stmt = select(func.count()).select_from(ArchivedStaff)

        # フィルタリング条件
        conditions = []
        if exclude_test_data:
            conditions.append(ArchivedStaff.is_test_data == False)
        if office_id:
            conditions.append(ArchivedStaff.office_id == office_id)
        if archive_reason:
            conditions.append(ArchivedStaff.archive_reason == archive_reason)

        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = count_stmt.where(and_(*conditions))

        # 総件数取得
        count_result = await db.execute(count_stmt)
        total = count_result.scalar()

        # ページネーション（新しい順に並び替え）
        stmt = stmt.order_by(ArchivedStaff.archived_at.desc())
        stmt = stmt.offset(skip).limit(limit)

        # データ取得
        result = await db.execute(stmt)
        archives = list(result.scalars().all())

        return archives, total

    async def get_expired_archives(
        self,
        db: AsyncSession,
        *,
        exclude_test_data: bool = True
    ) -> List[ArchivedStaff]:
        """
        法定保存期限が過ぎたアーカイブを取得

        Args:
            db: データベースセッション
            exclude_test_data: テストデータを除外するか

        Returns:
            期限切れのアーカイブリスト
        """
        now = datetime.now(timezone.utc)

        stmt = select(ArchivedStaff).where(
            ArchivedStaff.legal_retention_until <= now
        )

        if exclude_test_data:
            stmt = stmt.where(ArchivedStaff.is_test_data == False)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def delete_expired_archives(
        self,
        db: AsyncSession,
        *,
        exclude_test_data: bool = True
    ) -> int:
        """
        法定保存期限が過ぎたアーカイブを削除

        Args:
            db: データベースセッション
            exclude_test_data: テストデータを除外するか

        Returns:
            削除されたレコード数
        """
        expired_archives = await self.get_expired_archives(
            db,
            exclude_test_data=exclude_test_data
        )

        count = 0
        for archive in expired_archives:
            await db.delete(archive)
            count += 1

        return count


# グローバルインスタンス
archived_staff = CRUDArchivedStaff()
