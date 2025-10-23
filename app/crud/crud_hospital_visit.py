"""
通院歴のCRUD操作
"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import UUID, desc

from app.models.assessment import HistoryOfHospitalVisits, MedicalMatters
from app.schemas.assessment import HospitalVisitCreate, HospitalVisitUpdate, MedicalInfoCreate
from app.models.enums import MedicalCareInsurance, AidingType
from fastapi.encoders import jsonable_encoder


class CRUDHospitalVisit:
    """通院歴のCRUD操作クラス"""

    async def get_hospital_visits(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID
    ) -> List[HistoryOfHospitalVisits]:
        """
        指定された利用者IDの通院歴を全て取得
        JOINを使用してmedical_mattersテーブルと結合

        Args:
            db: データベースセッション
            recipient_id: 利用者ID

        Returns:
            通院歴のリスト（date_startedの降順）
        """
        stmt = (
            select(HistoryOfHospitalVisits)
            .join(MedicalMatters, HistoryOfHospitalVisits.medical_matters_id == MedicalMatters.id)
            .where(MedicalMatters.welfare_recipient_id == recipient_id)
            .order_by(desc(HistoryOfHospitalVisits.date_started))
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        *,
        recipient_id: UUID,
        obj_in: HospitalVisitCreate
    ) -> HistoryOfHospitalVisits:
        """
        新しい通院歴を追加
        医療基本情報が存在しない場合は、先にデフォルト値で作成

        Args:
            db: データベースセッション
            recipient_id: 利用者ID
            obj_in: 作成データ

        Returns:
            作成された通院歴
        """
        # recipient_idからmedical_matters_idを取得
        # 存在しない場合は先に作成
        stmt = select(MedicalMatters).where(
            MedicalMatters.welfare_recipient_id == recipient_id
        )
        result = await db.execute(stmt)
        medical_matters = result.scalars().first()

        if not medical_matters:
            # 医療基本情報が存在しない場合、デフォルト値で作成
            medical_matters = MedicalMatters(
                welfare_recipient_id=recipient_id,
                medical_care_insurance=MedicalCareInsurance.national_health_insurance,
                aiding=AidingType.none,
                history_of_hospitalization_in_the_past_2_years=False
            )
            db.add(medical_matters)
            await db.flush()  # IDを取得するためにflush

        # 通院歴を作成
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = HistoryOfHospitalVisits(
            **obj_in_data,
            medical_matters_id=medical_matters.id
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        visit_id: int,
        obj_in: HospitalVisitUpdate
    ) -> Optional[HistoryOfHospitalVisits]:
        """
        指定されたIDの通院歴を更新

        Args:
            db: データベースセッション
            visit_id: 通院歴ID
            obj_in: 更新データ

        Returns:
            更新された通院歴、存在しない場合はNone
        """
        stmt = select(HistoryOfHospitalVisits).where(
            HistoryOfHospitalVisits.id == visit_id
        )
        result = await db.execute(stmt)
        db_obj = result.scalars().first()

        if not db_obj:
            return None

        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(
        self,
        db: AsyncSession,
        *,
        visit_id: int
    ) -> bool:
        """
        指定されたIDの通院歴を削除

        Args:
            db: データベースセッション
            visit_id: 通院歴ID

        Returns:
            削除成功ならTrue、失敗ならFalse
        """
        stmt = select(HistoryOfHospitalVisits).where(
            HistoryOfHospitalVisits.id == visit_id
        )
        result = await db.execute(stmt)
        db_obj = result.scalars().first()

        if not db_obj:
            return False

        await db.delete(db_obj)
        await db.commit()
        return True


crud_hospital_visit = CRUDHospitalVisit()
