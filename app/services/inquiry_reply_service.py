"""問い合わせ返信の保存とメール送信準備を扱うサービス。"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_audit_log import audit_log as crud_audit_log
from app.crud.crud_inquiry import crud_inquiry
from app.models.staff import Staff


@dataclass(frozen=True)
class InquiryReplyEmail:
    """コミット後に送信する返信メールの情報。"""

    recipient_email: str
    recipient_name: str | None
    inquiry_title: str
    inquiry_created_at: str
    reply_content: str


@dataclass(frozen=True)
class InquiryReplyResult:
    """永続化済みの返信と、任意メール送信に必要な情報。"""

    reply_message_id: UUID
    email: InquiryReplyEmail | None


class InquiryReplyService:
    """問い合わせ返信のユースケースを実行する。"""

    async def reply_to_inquiry(
        self,
        db: AsyncSession,
        *,
        inquiry_id: UUID,
        current_user: Staff,
        reply_content: str,
        send_email: bool,
    ) -> InquiryReplyResult:
        """返信の保存と状態更新を単一トランザクションで完了する。"""
        try:
            inquiry = await crud_inquiry.get_inquiry_by_id(db=db, inquiry_id=inquiry_id)
            if not inquiry or not inquiry.message:
                raise ValueError("問い合わせが見つかりません")

            email = None
            if send_email and inquiry.sender_email:
                email = InquiryReplyEmail(
                    recipient_email=inquiry.sender_email,
                    recipient_name=inquiry.sender_name,
                    inquiry_title=inquiry.message.title,
                    inquiry_created_at=inquiry.created_at.isoformat() if inquiry.created_at else "",
                    reply_content=reply_content,
                )

            reply_message = await crud_inquiry.create_reply(
                db=db,
                inquiry_id=inquiry_id,
                reply_staff_id=current_user.id,
                reply_content=reply_content,
                send_email=email is not None,
                inquiry=inquiry,
            )
            await crud_audit_log.create_log(
                db=db,
                actor_id=current_user.id,
                actor_role=current_user.role.value,
                action="inquiry.replied",
                target_type="inquiry",
                target_id=inquiry.id,
                office_id=inquiry.message.office_id,
                details={"send_email_requested": send_email, "email_queued": email is not None},
                is_test_data=inquiry.is_test_data,
                auto_commit=False,
            )
            await db.commit()

            return InquiryReplyResult(reply_message_id=reply_message.id, email=email)
        except Exception:
            await db.rollback()
            raise


inquiry_reply_service = InquiryReplyService()
