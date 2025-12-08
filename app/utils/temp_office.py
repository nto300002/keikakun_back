"""
一時的なシステム事務所の作成・削除ユーティリティ

問い合わせ機能など、app_adminが関与するがoffice_idが必須の場合に使用
"""
import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.office import Office
from app.models.enums import OfficeType

logger = logging.getLogger(__name__)


async def create_temporary_system_office(
    db: AsyncSession,
    created_by_staff_id: uuid.UUID
) -> Office:
    """
    一時的なシステム事務所を作成します。

    Args:
        db: データベースセッション
        created_by_staff_id: 作成者のスタッフID（通常はapp_admin）

    Returns:
        作成されたOfficeインスタンス
    """
    temp_office = Office(
        id=uuid.uuid4(),
        name="__TEMP_SYSTEM__",
        type=OfficeType.type_A_office,
        created_by=created_by_staff_id,
        last_modified_by=created_by_staff_id,
        is_test_data=False,
        is_deleted=False
    )

    db.add(temp_office)
    await db.flush()

    logger.info(f"一時的なシステム事務所を作成: {temp_office.id}")
    return temp_office


async def delete_temporary_system_office(
    db: AsyncSession,
    office_id: uuid.UUID
) -> bool:
    """
    一時的なシステム事務所を削除します。

    Args:
        db: データベースセッション
        office_id: 削除する事務所のID

    Returns:
        削除に成功したかどうか
    """
    try:
        stmt = select(Office).where(
            Office.id == office_id,
            Office.name == "__TEMP_SYSTEM__"
        )
        result = await db.execute(stmt)
        office = result.scalar_one_or_none()

        if office:
            await db.delete(office)
            await db.flush()
            logger.info(f"一時的なシステム事務所を削除: {office_id}")
            return True
        else:
            logger.warning(f"一時的なシステム事務所が見つかりません: {office_id}")
            return False
    except Exception as e:
        logger.error(f"一時的なシステム事務所の削除に失敗: {office_id} - {str(e)}")
        return False


@asynccontextmanager
async def temporary_system_office(
    db: AsyncSession,
    created_by_staff_id: uuid.UUID
):
    """
    一時的なシステム事務所のコンテキストマネージャー

    使用例:
        async with temporary_system_office(db, admin_id) as office:
            # officeを使用した処理
            message = Message(office_id=office.id, ...)
            db.add(message)
            await db.commit()
        # コンテキスト終了時に自動的にofficeが削除される

    Args:
        db: データベースセッション
        created_by_staff_id: 作成者のスタッフID

    Yields:
        作成されたOfficeインスタンス
    """
    office = await create_temporary_system_office(db, created_by_staff_id)

    try:
        yield office
    finally:
        # 正常終了・例外発生いずれの場合も削除
        await delete_temporary_system_office(db, office.id)


async def get_or_create_system_office(
    db: AsyncSession,
    admin_staff_id: uuid.UUID
) -> uuid.UUID:
    """
    既存のシステム事務所を取得、なければ作成します。

    システム事務所は削除せず、複数の問い合わせで再利用されます。
    計算量: O(1) - インデックスを使用した効率的な検索

    Args:
        db: データベースセッション
        admin_staff_id: 管理者スタッフID

    Returns:
        システム事務所のID
    """
    # 既存の一時システム事務所を検索
    # LIMIT 1 で最初の1件のみ取得（複数存在する場合でも効率的）
    # is_deleted インデックスと name フィルタで高速検索
    stmt = select(Office.id).where(
        Office.name == "__TEMP_SYSTEM__",
        Office.is_deleted == False  # noqa: E712
    ).limit(1)

    result = await db.execute(stmt)
    existing_office_id = result.scalar_one_or_none()

    if existing_office_id:
        logger.info(f"既存のシステム事務所を再利用: {existing_office_id}")
        return existing_office_id

    # なければ新規作成
    logger.info("新しいシステム事務所を作成します")
    new_office = await create_temporary_system_office(db, admin_staff_id)
    await db.flush()  # IDを確定させる
    return new_office.id
