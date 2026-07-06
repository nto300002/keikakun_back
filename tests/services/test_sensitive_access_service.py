from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.enums import StaffRole
from app.services.sensitive_access_service import (
    SensitiveFieldGroup,
    TemporaryUnmaskGrant,
    can_view_unmasked,
    create_unmask_audit_log,
    require_unmask_reason,
)


def test_app_admin_without_temporary_grant_cannot_view_sensitive_audit_details():
    assert not can_view_unmasked(
        actor_role=StaffRole.app_admin,
        field_group=SensitiveFieldGroup.audit_log_details,
    )


def test_app_admin_with_active_temporary_grant_can_view_matching_sensitive_details():
    actor_id = uuid4()
    target_id = uuid4()
    now = datetime.now(timezone.utc)
    grant = TemporaryUnmaskGrant(
        actor_id=actor_id,
        target_type="audit_log",
        target_id=target_id,
        field_group=SensitiveFieldGroup.audit_log_details,
        reason="問い合わせ調査のため監査ログ詳細を確認する",
        expires_at=now + timedelta(minutes=30),
        approval_id=uuid4(),
    )

    assert can_view_unmasked(
        actor_role=StaffRole.app_admin,
        field_group=SensitiveFieldGroup.audit_log_details,
        actor_id=actor_id,
        target_type="audit_log",
        target_id=target_id,
        temporary_grant=grant,
        now=now,
    )


def test_expired_temporary_grant_does_not_allow_unmasked_view():
    actor_id = uuid4()
    target_id = uuid4()
    now = datetime.now(timezone.utc)
    grant = TemporaryUnmaskGrant(
        actor_id=actor_id,
        target_type="audit_log",
        target_id=target_id,
        field_group=SensitiveFieldGroup.audit_log_details,
        reason="問い合わせ調査のため監査ログ詳細を確認する",
        expires_at=now - timedelta(seconds=1),
    )

    assert not can_view_unmasked(
        actor_role=StaffRole.app_admin,
        field_group=SensitiveFieldGroup.audit_log_details,
        actor_id=actor_id,
        target_type="audit_log",
        target_id=target_id,
        temporary_grant=grant,
        now=now,
    )


def test_unmask_reason_is_required():
    with pytest.raises(ValueError):
        require_unmask_reason("   ")


def test_push_endpoint_unmasked_value_is_limited_to_self_or_system():
    assert can_view_unmasked(
        actor_role=StaffRole.employee,
        field_group=SensitiveFieldGroup.push_endpoint,
        is_self=True,
    )
    assert can_view_unmasked(
        actor_role="system",
        field_group=SensitiveFieldGroup.push_endpoint,
    )
    assert not can_view_unmasked(
        actor_role=StaffRole.owner,
        field_group=SensitiveFieldGroup.push_endpoint,
        same_office=True,
    )


@pytest.mark.asyncio
async def test_create_unmask_audit_log_records_required_fields(
    db_session,
    staff_factory,
    office_factory,
):
    office = await office_factory(session=db_session, is_test_data=True)
    actor = await staff_factory(
        office_id=office.id,
        role=StaffRole.app_admin,
        session=db_session,
        is_test_data=True,
    )
    target_id = uuid4()
    approval_id = uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    audit_log = await create_unmask_audit_log(
        db=db_session,
        actor_id=actor.id,
        actor_role=StaffRole.app_admin,
        target_type="audit_log",
        target_id=target_id,
        field_group=SensitiveFieldGroup.audit_log_details,
        reason="問い合わせ調査のため監査ログ詳細を確認する",
        approval_id=approval_id,
        expires_at=expires_at,
        result="allowed",
        office_id=office.id,
        is_test_data=True,
    )
    await db_session.commit()

    assert audit_log.action == "privacy.unmask_viewed"
    assert audit_log.staff_id == actor.id
    assert audit_log.actor_role == StaffRole.app_admin.value
    assert audit_log.target_type == "audit_log"
    assert audit_log.target_id == target_id
    assert audit_log.details["field_group"] == SensitiveFieldGroup.audit_log_details.value
    assert audit_log.details["reason"] == "問い合わせ調査のため監査ログ詳細を確認する"
    assert audit_log.details["approval_id"] == str(approval_id)
    assert audit_log.details["result"] == "allowed"
    assert audit_log.details["expires_at"] == expires_at.isoformat()
