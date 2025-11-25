import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash
from app.models.enums import StaffRole
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.schemas.staff import AdminCreate, StaffCreate


class CRUDStaff:
    async def get(self, db: AsyncSession, *, id: uuid.UUID) -> Staff | None:
        query = select(Staff).filter(Staff.id == id).options(
            # 文字列ではなく、クラス属性を直接指定する
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office),
            selectinload(Staff.mfa_backup_codes)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, *, email: str) -> Staff | None:
        query = select(Staff).filter(Staff.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_admin(self, db: AsyncSession, *, obj_in: AdminCreate) -> Staff:
        db_obj = Staff(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            full_name=f"{obj_in.last_name} {obj_in.first_name}",
            role=StaffRole.owner,
        )
        db.add(db_obj)
        await db.flush()  # トランザクションはテスト側で管理するためcommitはしない
        await db.refresh(db_obj)
        return db_obj

    async def create_staff(self, db: AsyncSession, *, obj_in: StaffCreate) -> Staff:
        db_obj = Staff(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            full_name=f"{obj_in.last_name} {obj_in.first_name}",
            role=obj_in.role,
        )
        db.add(db_obj)
        await db.flush()  # トランザクションはテスト側で管理するためcommitはしない
        await db.refresh(db_obj)
        return db_obj

    async def get_staff_with_primary_office(self, db: AsyncSession, *, staff_id: uuid.UUID) -> tuple[Staff, Office] | None:
        """
        スタッフIDに基づいて、スタッフとそのプライマリ事業所を取得します。
        """
        query = (
            select(Staff, Office)
            .join(OfficeStaff, Staff.id == OfficeStaff.staff_id)
            .join(Office, OfficeStaff.office_id == Office.id)
            .where(Staff.id == staff_id, OfficeStaff.is_primary == True)
        )
        result = await db.execute(query)
        return result.one_or_none()

    async def get_by_office_id(
        self,
        db: AsyncSession,
        *,
        office_id: uuid.UUID,
        exclude_deleted: bool = True
    ) -> list[Staff]:
        """
        事業所IDに基づいて、その事業所に所属する全スタッフを取得します。

        Args:
            db: データベースセッション
            office_id: 事業所ID
            exclude_deleted: 削除済みスタッフを除外するか（デフォルト: True）

        Returns:
            スタッフのリスト
        """
        query = (
            select(Staff)
            .join(OfficeStaff, Staff.id == OfficeStaff.staff_id)
            .where(OfficeStaff.office_id == office_id)
            .options(selectinload(Staff.office_associations).selectinload(OfficeStaff.office))
        )

        # 削除済みスタッフを除外
        if exclude_deleted:
            query = query.where(Staff.is_deleted == False)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_owners_in_office(
        self,
        db: AsyncSession,
        *,
        office_id: uuid.UUID
    ) -> int:
        """
        事務所内の有効なOwnerの数を取得

        Args:
            db: データベースセッション
            office_id: 事業所ID

        Returns:
            Ownerの数（削除済みは除外）
        """
        query = (
            select(func.count(Staff.id))
            .join(OfficeStaff, Staff.id == OfficeStaff.staff_id)
            .where(
                and_(
                    OfficeStaff.office_id == office_id,
                    Staff.role == StaffRole.owner,
                    Staff.is_deleted == False
                )
            )
        )
        result = await db.execute(query)
        count = result.scalar()
        return count if count else 0

    async def soft_delete(
        self,
        db: AsyncSession,
        *,
        staff_id: uuid.UUID,
        deleted_by: uuid.UUID
    ) -> Staff:
        """
        スタッフを論理削除

        Args:
            db: データベースセッション
            staff_id: 削除対象スタッフID
            deleted_by: 削除実行者ID

        Returns:
            削除されたスタッフ

        Note:
            - commitはエンドポイント層で行う
            - トランザクション管理は呼び出し側で行う
        """
        # スタッフを取得
        stmt = select(Staff).where(Staff.id == staff_id)
        result = await db.execute(stmt)
        staff = result.scalar_one()

        # 論理削除
        staff.is_deleted = True
        staff.deleted_at = datetime.now(timezone.utc)
        staff.deleted_by = deleted_by

        db.add(staff)
        await db.flush()

        return staff


staff = CRUDStaff()