from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.enums import StaffRole


class SensitiveFieldGroup(str, Enum):
    """マスク解除可否を判定する機微情報グループ。"""

    audit_log_details = "audit_log_details"
    inquiry_detail = "inquiry_detail"
    billing_webhook = "billing_webhook"
    office_contact = "office_contact"
    office_staff_contact = "office_staff_contact"
    approval_request_data = "approval_request_data"
    push_endpoint = "push_endpoint"
    email_failure_details = "email_failure_details"
    mfa_bootstrap_secret = "mfa_bootstrap_secret"
    welfare_recipient_detail = "welfare_recipient_detail"


APP_ADMIN_TEMPORARY_GRANT_GROUPS = {
    SensitiveFieldGroup.audit_log_details,
    SensitiveFieldGroup.inquiry_detail,
    SensitiveFieldGroup.billing_webhook,
    SensitiveFieldGroup.approval_request_data,
    SensitiveFieldGroup.email_failure_details,
}

SAME_OFFICE_ADMIN_GROUPS = {
    SensitiveFieldGroup.office_contact,
    SensitiveFieldGroup.office_staff_contact,
    SensitiveFieldGroup.approval_request_data,
    SensitiveFieldGroup.welfare_recipient_detail,
}

MFA_BOOTSTRAP_ROLES = {
    StaffRole.owner.value,
    StaffRole.manager.value,
}


@dataclass(frozen=True)
class TemporaryUnmaskGrant:
    """理由と期限付きの一時的なマスク解除許可。"""

    actor_id: UUID
    target_type: str
    target_id: UUID
    field_group: SensitiveFieldGroup
    reason: str
    expires_at: datetime
    approval_id: Optional[UUID] = None

    def is_active(self, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        return self.expires_at > current_time

    def matches(
        self,
        *,
        actor_id: Optional[UUID],
        target_type: Optional[str],
        target_id: Optional[UUID],
        field_group: SensitiveFieldGroup,
        now: Optional[datetime] = None,
    ) -> bool:
        return (
            self.is_active(now)
            and actor_id == self.actor_id
            and target_type == self.target_type
            and target_id == self.target_id
            and field_group == self.field_group
            and bool(require_unmask_reason(self.reason))
        )


def _role_value(actor_role: StaffRole | str) -> str:
    return actor_role.value if isinstance(actor_role, StaffRole) else str(actor_role)


def require_unmask_reason(reason: str) -> str:
    """マスク解除理由を必須化し、空文字なら拒否する。"""

    normalized = reason.strip()
    if not normalized:
        raise ValueError("Mask解除理由は必須です")
    return normalized


def can_view_unmasked(
    *,
    actor_role: StaffRole | str,
    field_group: SensitiveFieldGroup,
    actor_id: Optional[UUID] = None,
    target_type: Optional[str] = None,
    target_id: Optional[UUID] = None,
    is_self: bool = False,
    same_office: bool = False,
    temporary_grant: Optional[TemporaryUnmaskGrant] = None,
    now: Optional[datetime] = None,
) -> bool:
    """
    マスク解除済みの値を閲覧できるかを判定する。

    通常 app_admin は最小情報のみを閲覧し、機微グループの生値は
    理由・対象・期限付きの一時許可がある場合だけ許可する。
    """

    role = _role_value(actor_role)

    if role == "system":
        return True

    if field_group == SensitiveFieldGroup.push_endpoint:
        return is_self

    if field_group == SensitiveFieldGroup.mfa_bootstrap_secret:
        return is_self or (same_office and role in MFA_BOOTSTRAP_ROLES)

    if (
        field_group in SAME_OFFICE_ADMIN_GROUPS
        and same_office
        and role in {StaffRole.owner.value, StaffRole.manager.value}
    ):
        return True

    if role == StaffRole.app_admin.value and field_group in APP_ADMIN_TEMPORARY_GRANT_GROUPS:
        if temporary_grant is None:
            return False
        return temporary_grant.matches(
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            field_group=field_group,
            now=now,
        )

    return False


def permission_matrix() -> dict[str, dict[str, str]]:
    """ドキュメント・テストで参照できる権限別表示表。"""

    return {
        SensitiveFieldGroup.audit_log_details.value: {
            "default": "masked",
            "app_admin": "masked",
            "app_admin_with_temporary_grant": "unmasked",
            "system": "unmasked",
        },
        SensitiveFieldGroup.inquiry_detail.value: {
            "default": "masked",
            "app_admin": "masked",
            "app_admin_with_temporary_grant": "unmasked",
            "system": "unmasked",
        },
        SensitiveFieldGroup.billing_webhook.value: {
            "default": "masked",
            "app_admin": "masked",
            "app_admin_with_temporary_grant": "unmasked",
            "system": "unmasked",
        },
        SensitiveFieldGroup.office_contact.value: {
            "default": "masked",
            "same_office_owner_manager": "unmasked",
            "app_admin": "masked",
        },
        SensitiveFieldGroup.office_staff_contact.value: {
            "default": "masked",
            "same_office_owner_manager": "unmasked",
            "app_admin": "masked",
        },
        SensitiveFieldGroup.approval_request_data.value: {
            "default": "masked",
            "same_office_owner_manager": "unmasked",
            "app_admin_with_temporary_grant": "unmasked",
        },
        SensitiveFieldGroup.push_endpoint.value: {
            "default": "masked",
            "self": "unmasked",
            "system": "unmasked",
        },
        SensitiveFieldGroup.email_failure_details.value: {
            "default": "masked",
            "app_admin": "masked",
            "app_admin_with_temporary_grant": "unmasked",
            "system": "unmasked",
        },
        SensitiveFieldGroup.mfa_bootstrap_secret.value: {
            "default": "never_redisplay",
            "self_initial_issue": "unmasked_once",
            "same_office_owner_manager_initial_issue": "unmasked_once",
        },
        SensitiveFieldGroup.welfare_recipient_detail.value: {
            "default": "masked",
            "same_office_owner_manager": "unmasked",
            "same_office_employee": "masked",
        },
    }


async def create_unmask_audit_log(
    *,
    db: AsyncSession,
    actor_id: Optional[UUID],
    actor_role: StaffRole | str,
    target_type: str,
    target_id: Optional[UUID],
    field_group: SensitiveFieldGroup,
    reason: str,
    expires_at: datetime,
    result: str,
    approval_id: Optional[UUID] = None,
    office_id: Optional[UUID] = None,
    is_test_data: bool = False,
):
    """マスク解除済み閲覧イベントを既存の監査ログに記録する。"""

    normalized_reason = require_unmask_reason(reason)
    details = {
        "field_group": field_group.value,
        "reason": normalized_reason,
        "approval_id": str(approval_id) if approval_id else None,
        "expires_at": expires_at.isoformat(),
        "result": result,
    }

    return await crud.audit_log.create_log(
        db=db,
        actor_id=actor_id,
        actor_role=_role_value(actor_role),
        action="privacy.unmask_viewed",
        target_type=target_type,
        target_id=target_id,
        office_id=office_id,
        details=details,
        is_test_data=is_test_data,
    )
