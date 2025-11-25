"""
メッセージ数上限機能のテスト

事務所ごとにメッセージを50件まで保存し、
超えた場合は古いメッセージから自動削除する
"""
import pytest
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.message import Message
from app.crud.crud_message import crud_message


class TestMessageLimit:
    """メッセージ数上限のテストクラス"""

    @pytest.mark.asyncio
    async def test_message_count_under_limit(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        メッセージ数が上限未満の場合、古いメッセージは削除されない
        """
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        office_id = owner.office_associations[0].office_id

        # 10件のメッセージを作成
        for i in range(10):
            await crud_message.create_personal_message(
                db=db_session,
                sender_staff_id=owner.id,
                recipient_staff_ids=[manager.id],
                office_id=office_id,
                title=f"Test Message {i}",
                body="Test Body",
                priority="normal"
            )

        await db_session.commit()

        # メッセージ数を確認
        stmt = select(func.count(Message.id)).where(
            Message.office_id == office_id,
            Message.is_test_data == False
        )
        result = await db_session.execute(stmt)
        count = result.scalar()

        assert count == 10

    @pytest.mark.asyncio
    async def test_message_count_at_limit(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        メッセージ数がちょうど50件の場合、新規作成時に最も古いメッセージが削除される
        """
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        office_id = owner.office_associations[0].office_id

        # 50件のメッセージを作成
        message_ids = []
        for i in range(50):
            msg = await crud_message.create_personal_message(
                db=db_session,
                sender_staff_id=owner.id,
                recipient_staff_ids=[manager.id],
                office_id=office_id,
                title=f"Test Message {i}",
                body="Test Body",
                priority="normal"
            )
            message_ids.append(msg.id)

        await db_session.commit()

        # 最も古いメッセージのIDを保存
        oldest_message_id = message_ids[0]

        # 51件目のメッセージを作成（制限機能を使用）
        await crud_message.create_personal_message_with_limit(
            db=db_session,
            sender_staff_id=owner.id,
            recipient_staff_ids=[manager.id],
            office_id=office_id,
            title="Test Message 51",
            body="Test Body",
            priority="normal",
            limit=50
        )

        await db_session.commit()

        # メッセージ数が50件のまま
        stmt = select(func.count(Message.id)).where(
            Message.office_id == office_id,
            Message.is_test_data == False
        )
        result = await db_session.execute(stmt)
        count = result.scalar()

        assert count == 50

        # 最も古いメッセージが削除されている
        oldest_msg_stmt = select(Message).where(Message.id == oldest_message_id)
        oldest_msg_result = await db_session.execute(oldest_msg_stmt)
        oldest_msg = oldest_msg_result.scalar_one_or_none()

        assert oldest_msg is None

    @pytest.mark.asyncio
    async def test_message_count_over_limit(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        メッセージ数が上限を超えている場合、
        新規作成時に古いメッセージが複数削除される
        """
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        office_id = owner.office_associations[0].office_id

        # 55件のメッセージを作成（上限を超えた状態）
        message_ids = []
        for i in range(55):
            msg = await crud_message.create_personal_message(
                db=db_session,
                sender_staff_id=owner.id,
                recipient_staff_ids=[manager.id],
                office_id=office_id,
                title=f"Test Message {i}",
                body="Test Body",
                priority="normal"
            )
            message_ids.append(msg.id)

        await db_session.commit()

        # 最も古い5件のメッセージIDを保存
        oldest_5_ids = message_ids[:5]

        # 56件目のメッセージを作成（制限機能を使用）
        await crud_message.create_personal_message_with_limit(
            db=db_session,
            sender_staff_id=owner.id,
            recipient_staff_ids=[manager.id],
            office_id=office_id,
            title="Test Message 56",
            body="Test Body",
            priority="normal",
            limit=50
        )

        await db_session.commit()

        # メッセージ数が50件になっている
        stmt = select(func.count(Message.id)).where(
            Message.office_id == office_id,
            Message.is_test_data == False
        )
        result = await db_session.execute(stmt)
        count = result.scalar()

        assert count == 50

        # 最も古い6件が削除されている（55 - 50 + 1 = 6）
        for old_id in oldest_5_ids:
            old_msg_stmt = select(Message).where(Message.id == old_id)
            old_msg_result = await db_session.execute(old_msg_stmt)
            old_msg = old_msg_result.scalar_one_or_none()
            assert old_msg is None

    @pytest.mark.asyncio
    async def test_message_limit_does_not_affect_other_offices(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        メッセージ数制限は事務所ごとに独立している
        """
        # 事務所Aのユーザー
        owner_a = await owner_user_factory()
        manager_a = await manager_user_factory(office=owner_a.office_associations[0].office)
        office_a_id = owner_a.office_associations[0].office_id

        # 事務所Bのユーザー
        owner_b = await owner_user_factory()
        manager_b = await manager_user_factory(office=owner_b.office_associations[0].office)
        office_b_id = owner_b.office_associations[0].office_id

        # 事務所Aに50件のメッセージを作成
        for i in range(50):
            await crud_message.create_personal_message_with_limit(
                db=db_session,
                sender_staff_id=owner_a.id,
                recipient_staff_ids=[manager_a.id],
                office_id=office_a_id,
                title=f"Office A Message {i}",
                body="Test Body",
                priority="normal",
                limit=50
            )

        # 事務所Bに30件のメッセージを作成
        for i in range(30):
            await crud_message.create_personal_message_with_limit(
                db=db_session,
                sender_staff_id=owner_b.id,
                recipient_staff_ids=[manager_b.id],
                office_id=office_b_id,
                title=f"Office B Message {i}",
                body="Test Body",
                priority="normal",
                limit=50
            )

        await db_session.commit()

        # 事務所Aは50件
        stmt_a = select(func.count(Message.id)).where(
            Message.office_id == office_a_id,
            Message.is_test_data == False
        )
        result_a = await db_session.execute(stmt_a)
        count_a = result_a.scalar()
        assert count_a == 50

        # 事務所Bは30件（影響を受けていない）
        stmt_b = select(func.count(Message.id)).where(
            Message.office_id == office_b_id,
            Message.is_test_data == False
        )
        result_b = await db_session.execute(stmt_b)
        count_b = result_b.scalar()
        assert count_b == 30

    @pytest.mark.asyncio
    async def test_test_data_messages_not_counted_in_limit(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        is_test_data=Trueのメッセージは上限カウントに含まれない
        """
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        office_id = owner.office_associations[0].office_id

        # テストデータとして10件作成
        for i in range(10):
            msg = Message(
                office_id=office_id,
                sender_staff_id=owner.id,
                title=f"Test Data Message {i}",
                body="Test Body",
                message_type="personal",
                priority="normal",
                is_test_data=True
            )
            db_session.add(msg)

        # 通常データとして50件作成
        for i in range(50):
            await crud_message.create_personal_message_with_limit(
                db=db_session,
                sender_staff_id=owner.id,
                recipient_staff_ids=[manager.id],
                office_id=office_id,
                title=f"Real Message {i}",
                body="Test Body",
                priority="normal",
                limit=50
            )

        await db_session.commit()

        # 通常データは50件
        stmt_real = select(func.count(Message.id)).where(
            Message.office_id == office_id,
            Message.is_test_data == False
        )
        result_real = await db_session.execute(stmt_real)
        count_real = result_real.scalar()
        assert count_real == 50

        # テストデータは10件のまま（削除されていない）
        stmt_test = select(func.count(Message.id)).where(
            Message.office_id == office_id,
            Message.is_test_data == True
        )
        result_test = await db_session.execute(stmt_test)
        count_test = result_test.scalar()
        assert count_test == 10
