"""
メッセージモデルのテスト

TDD: REDフェーズ - モデル実装前に失敗するテストを作成
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import uuid

from app.models.message import Message, MessageRecipient, MessageType, MessagePriority
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.enums import OfficeType, StaffRole


@pytest.fixture
async def test_creator(db_session: AsyncSession):
    """テスト用の事務所作成者を作成"""
    creator = Staff(
        id=uuid.uuid4(),
        email="creator@example.com",
        first_name="作成",
        last_name="太郎",
        full_name="太郎 作成",
        role=StaffRole.owner,
        hashed_password="dummy_hash"
    )
    db_session.add(creator)
    await db_session.commit()
    await db_session.refresh(creator)
    return creator


@pytest.fixture
async def test_office(db_session: AsyncSession, test_creator: Staff):
    """テスト用事務所を作成"""
    office = Office(
        id=uuid.uuid4(),
        name="テスト事務所",
        type=OfficeType.type_A_office,
        created_by=test_creator.id,
        last_modified_by=test_creator.id
    )
    db_session.add(office)
    await db_session.commit()
    await db_session.refresh(office)

    # 作成者とOfficeを関連付け
    office_staff = OfficeStaff(
        staff_id=test_creator.id,
        office_id=office.id,
        is_primary=True
    )
    db_session.add(office_staff)
    await db_session.commit()

    return office


@pytest.fixture
async def test_sender(db_session: AsyncSession, test_office: Office):
    """テスト用送信者スタッフを作成"""
    sender = Staff(
        id=uuid.uuid4(),
        email="sender@example.com",
        first_name="送信",
        last_name="太郎",
        full_name="太郎 送信",
        role=StaffRole.owner,
        hashed_password="dummy_hash"
    )
    db_session.add(sender)
    await db_session.commit()
    await db_session.refresh(sender)

    # SenderとOfficeを関連付け
    office_staff = OfficeStaff(
        staff_id=sender.id,
        office_id=test_office.id,
        is_primary=True
    )
    db_session.add(office_staff)
    await db_session.commit()

    return sender


@pytest.fixture
async def test_recipient(db_session: AsyncSession, test_office: Office):
    """テスト用受信者スタッフを作成"""
    recipient = Staff(
        id=uuid.uuid4(),
        email="recipient@example.com",
        first_name="受信",
        last_name="太郎",
        full_name="太郎 受信",
        role=StaffRole.employee,
        hashed_password="dummy_hash"
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    # RecipientとOfficeを関連付け
    office_staff = OfficeStaff(
        staff_id=recipient.id,
        office_id=test_office.id,
        is_primary=True
    )
    db_session.add(office_staff)
    await db_session.commit()

    return recipient


class TestMessageModel:
    """Messageモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_message(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_office: Office
    ):
        """メッセージを作成できること"""
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            message_type=MessageType.personal,
            priority=MessagePriority.normal,
            title="テストメッセージ",
            content="これはテストです"
        )

        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        assert message.id is not None
        assert message.sender_staff_id == test_sender.id
        assert message.office_id == test_office.id
        assert message.message_type == MessageType.personal
        assert message.priority == MessagePriority.normal
        assert message.title == "テストメッセージ"
        assert message.content == "これはテストです"
        assert message.created_at is not None
        assert message.updated_at is not None

    @pytest.mark.asyncio
    async def test_message_defaults(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_office: Office
    ):
        """メッセージのデフォルト値が正しく設定されること"""
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            title="デフォルト値テスト",
            content="デフォルト値をテスト"
        )

        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        # デフォルト値の確認
        assert message.message_type == MessageType.personal  # デフォルト: personal
        assert message.priority == MessagePriority.normal  # デフォルト: normal

    @pytest.mark.asyncio
    async def test_message_relationships(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_office: Office
    ):
        """メッセージのリレーションシップが正しく機能すること"""
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            title="リレーションシップテスト",
            content="リレーションシップをテスト"
        )

        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        # sender リレーションシップの確認
        await db_session.refresh(message, ["sender"])
        assert message.sender is not None
        assert message.sender.id == test_sender.id
        assert message.sender.full_name == "太郎 送信"

        # office リレーションシップの確認
        await db_session.refresh(message, ["office"])
        assert message.office is not None
        assert message.office.id == test_office.id
        assert message.office.name == "テスト事務所"

    @pytest.mark.asyncio
    async def test_message_type_enum(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_office: Office
    ):
        """MessageType enumが正しく機能すること"""
        # personal タイプ
        message_personal = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            message_type=MessageType.personal,
            title="個別メッセージ",
            content="個別メッセージです"
        )
        db_session.add(message_personal)

        # announcement タイプ
        message_announcement = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            message_type=MessageType.announcement,
            title="お知らせ",
            content="全員へのお知らせです"
        )
        db_session.add(message_announcement)

        await db_session.commit()
        await db_session.refresh(message_personal)
        await db_session.refresh(message_announcement)

        assert message_personal.message_type == MessageType.personal
        assert message_announcement.message_type == MessageType.announcement

    @pytest.mark.asyncio
    async def test_message_priority_enum(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_office: Office
    ):
        """MessagePriority enumが正しく機能すること"""
        # urgent 優先度
        message_urgent = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            priority=MessagePriority.urgent,
            title="緊急メッセージ",
            content="緊急です"
        )
        db_session.add(message_urgent)

        # low 優先度
        message_low = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            priority=MessagePriority.low,
            title="低優先度メッセージ",
            content="低優先度です"
        )
        db_session.add(message_low)

        await db_session.commit()
        await db_session.refresh(message_urgent)
        await db_session.refresh(message_low)

        assert message_urgent.priority == MessagePriority.urgent
        assert message_low.priority == MessagePriority.low


class TestMessageRecipientModel:
    """MessageRecipientモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_message_recipient(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_recipient: Staff,
        test_office: Office
    ):
        """メッセージ受信者を作成できること"""
        # メッセージを作成
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            title="受信者テスト",
            content="受信者をテスト"
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        # 受信者を作成
        recipient = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=test_recipient.id
        )
        db_session.add(recipient)
        await db_session.commit()
        await db_session.refresh(recipient)

        assert recipient.id is not None
        assert recipient.message_id == message.id
        assert recipient.recipient_staff_id == test_recipient.id
        assert recipient.is_read is False  # デフォルト: False
        assert recipient.read_at is None
        assert recipient.is_archived is False  # デフォルト: False
        assert recipient.created_at is not None
        assert recipient.updated_at is not None

    @pytest.mark.asyncio
    async def test_message_recipient_unique_constraint(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_recipient: Staff,
        test_office: Office
    ):
        """同じメッセージに同じ受信者を複数回追加できないこと"""
        from sqlalchemy.exc import IntegrityError

        # メッセージを作成
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            title="ユニーク制約テスト",
            content="ユニーク制約をテスト"
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        # 1つ目の受信者を作成
        recipient1 = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=test_recipient.id
        )
        db_session.add(recipient1)
        await db_session.commit()

        # 2つ目の受信者（同じメッセージ、同じスタッフ）を作成しようとする
        recipient2 = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=test_recipient.id
        )
        db_session.add(recipient2)

        # ユニーク制約違反でエラーが発生すること
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_mark_as_read(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_recipient: Staff,
        test_office: Office
    ):
        """メッセージを既読化できること"""
        # メッセージと受信者を作成
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            title="既読テスト",
            content="既読をテスト"
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        recipient = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=test_recipient.id
        )
        db_session.add(recipient)
        await db_session.commit()
        await db_session.refresh(recipient)

        # 最初は未読
        assert recipient.is_read is False
        assert recipient.read_at is None

        # 既読化
        recipient.is_read = True
        recipient.read_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(recipient)

        # 既読になっていること
        assert recipient.is_read is True
        assert recipient.read_at is not None

    @pytest.mark.asyncio
    async def test_message_recipient_relationships(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_recipient: Staff,
        test_office: Office
    ):
        """MessageRecipientのリレーションシップが正しく機能すること"""
        # メッセージと受信者を作成
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            title="リレーションテスト",
            content="リレーションをテスト"
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        recipient = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=test_recipient.id
        )
        db_session.add(recipient)
        await db_session.commit()
        await db_session.refresh(recipient)

        # message リレーションシップの確認
        await db_session.refresh(recipient, ["message"])
        assert recipient.message is not None
        assert recipient.message.id == message.id
        assert recipient.message.title == "リレーションテスト"

        # recipient_staff リレーションシップの確認
        await db_session.refresh(recipient, ["recipient_staff"])
        assert recipient.recipient_staff is not None
        assert recipient.recipient_staff.id == test_recipient.id
        assert recipient.recipient_staff.full_name == "太郎 受信"

    @pytest.mark.asyncio
    async def test_message_with_multiple_recipients(
        self,
        db_session: AsyncSession,
        test_sender: Staff,
        test_recipient: Staff,
        test_office: Office
    ):
        """1つのメッセージに複数の受信者を追加できること"""
        # 追加の受信者を作成
        recipient2 = Staff(
            id=uuid.uuid4(),
            email="recipient2@example.com",
            first_name="受信2",
            last_name="太郎",
            full_name="太郎 受信2",
            role=StaffRole.employee,
            hashed_password="dummy_hash"
        )
        db_session.add(recipient2)
        await db_session.commit()
        await db_session.refresh(recipient2)

        # Recipient2とOfficeを関連付け
        office_staff2 = OfficeStaff(
            staff_id=recipient2.id,
            office_id=test_office.id,
            is_primary=True
        )
        db_session.add(office_staff2)
        await db_session.commit()

        # メッセージを作成
        message = Message(
            sender_staff_id=test_sender.id,
            office_id=test_office.id,
            title="複数受信者テスト",
            content="複数受信者をテスト"
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        # 受信者1を追加
        mr1 = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=test_recipient.id
        )
        db_session.add(mr1)

        # 受信者2を追加
        mr2 = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=recipient2.id
        )
        db_session.add(mr2)

        await db_session.commit()

        # メッセージに紐づく受信者が2人いることを確認
        stmt = select(MessageRecipient).where(MessageRecipient.message_id == message.id)
        result = await db_session.execute(stmt)
        recipients = result.scalars().all()

        assert len(recipients) == 2
        recipient_ids = {r.recipient_staff_id for r in recipients}
        assert test_recipient.id in recipient_ids
        assert recipient2.id in recipient_ids
