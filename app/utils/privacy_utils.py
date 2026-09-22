"""
プライバシー保護ユーティリティ

PII（個人識別情報）をマスキングする関数群
- メールアドレスのマスキング
- 個人名のマスキング

使用例:
    >>> mask_email("test@example.com")
    't***@example.com'

    >>> mask_name("山田 太郎")
    '山田 *'
"""
import hashlib
import ipaddress
import re
from typing import Any, Optional


REDACTED = "<redacted>"
PRESENT = "<present>"
REDACTED_DETAIL_KEY = "redacted_details"
SAFE_AUDIT_STRING_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+\-]{0,127}$")

EMAIL_DETAIL_KEYS = {"email", "mail", "email_address", "new_email", "old_email", "recipient"}
NAME_DETAIL_KEYS = {"name", "full_name", "first_name", "last_name", "staff_name", "recipient_name"}
PRESENT_ONLY_DETAIL_KEYS = {
    "stripe_customer_id",
    "stripe_subscription_id",
    "stripe_payment_method_id",
    "customer_id",
    "subscription_id",
    "payment_method_id",
}
NESTED_AUDIT_ALLOWED_SCALAR_KEYS = {
    "count", "total", "safe_count", "success_count", "failed_count",
    "device_count", "renewal_alert_count", "assessment_alert_count",
    "push_sent_count", "push_failed_count", "email_queued", "send_email_requested",
}
REDACT_DETAIL_KEYS = {
    "address",
    "phone",
    "phone_number",
    "tel",
    "mobile",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "passphrase",
    "secret",
    "api_key",
    "authorization",
    "cookie",
    "raw_payload",
    "raw_details",
    "request_body",
    "response_body",
}
AUDIT_LOG_ACTION_ALLOWED_DETAIL_KEYS = {
    "email_send_failed": {"email_type", "error_type", "retry_count"},
    "inquiry.replied": {"send_email_requested", "email_queued"},
    "staff.deleted": {"deleted_staff_id", "deleted_staff_role"},
    "staff.updated": {"changed_field"},
    "office.updated": {"old_values", "new_values"},
    "withdrawal.requested": {"withdrawal_type", "affected_staff_count", "target_staff_id"},
    "withdrawal.approved": {"withdrawal_type", "execution_result"},
    "withdrawal.rejected": {"withdrawal_type"},
    "staff.soft_deleted": {"archive_id", "withdrawal_request_id", "deletion_type"},
    "office.deleted": {"deleted_staff_count", "withdrawal_request_id"},
    "billing.canceled_on_withdrawal": {"reason", "stripe_cancellation"},
    "deadline_notification_sent": {
        "recipient_email", "office_name", "renewal_alert_count",
        "assessment_alert_count", "staff_name", "email_threshold_days",
    },
    "push_notification_sent": {
        "recipient_email", "office_name", "staff_name", "push_sent_count",
        "push_failed_count", "device_count", "renewal_alert_count",
        "assessment_alert_count",
    },
    "billing.payment_succeeded": {"event_id", "event_type", "source"},
    "billing.payment_failed": {"event_id", "event_type", "source"},
    "billing.subscription_created": {"event_id", "event_type", "source"},
    "billing.subscription_updated": {
        "event_id", "event_type", "cancel_at_period_end", "cancel_at", "source",
    },
    "billing.subscription_deleted": {
        "event_id", "event_type", "has_recent_payment_failed", "source",
    },
    "employment.created": {"recipient_id", "employment_id", "changes"},
    "employment.updated": {"recipient_id", "employment_id", "changes"},
    "terms.agreed": {"terms_version", "privacy_version", "agreed_at"},
    "privacy.unmask_viewed": {"field_group", "approval_id", "expires_at", "result", "reason"},
    "billing.status_changed": {
        "old_status",
        "new_status",
        "reason",
        "change_number",
        "source",
        "event_type",
        "stripe_customer_id",
        "stripe_subscription_id",
    },
    "backup_used": set(),
    "requested": set(),
    "completed": set(),
    "enabled": set(),
    "disabled": set(),
    "UPDATE_NAME": set(),
    "CHANGE_PASSWORD": set(),
    "ATTEMPT_CHANGE_PASSWORD": set(),
    "UPDATE_EMAIL": set(),
    "staff.sensitive_storage_test": {
        "email", "full_name", "access_token", "stripe_customer_id", "changes",
    },
    "webauthn.credential_registered": set(),
    "webauthn.credential_revoked": set(),
    "webauthn.credential_renamed": set(),
}

AUDIT_PRESENCE_ONLY_DETAIL_KEYS = {
    "actor_id", "archive_id", "approval_id", "customer_id", "deleted_staff_id",
    "employment_id", "event_id", "office_id", "recipient_id", "request_id",
    "stripe_customer_id", "stripe_subscription_id", "target_id", "target_staff_id",
    "withdrawal_request_id",
}

WEBHOOK_TOP_LEVEL_KEYS = {
    "id",
    "object",
    "type",
    "created",
    "livemode",
    "pending_webhooks",
    "api_version",
    "data",
}
WEBHOOK_DATA_KEYS = {"object", "previous_attributes"}
WEBHOOK_OBJECT_SAFE_KEYS = {
    "object",
    "amount",
    "amount_due",
    "amount_paid",
    "amount_remaining",
    "currency",
    "status",
    "billing_reason",
    "collection_method",
    "created",
    "current_period_start",
    "current_period_end",
    "period_start",
    "period_end",
}
WEBHOOK_PRESENT_ONLY_KEYS = {
    "id",
    "customer",
    "subscription",
    "invoice",
    "payment_intent",
    "payment_method",
    "charge",
}
EMPLOYEE_ACTION_REQUEST_META_KEYS = {
    "resource_type",
    "action_type",
    "resource_id",
}
WELFARE_RECIPIENT_REDACT_SECTIONS = {
    "contact_address",
    "emergency_contacts",
    "disability_info",
    "disability_details",
}
WELFARE_RECIPIENT_REDACT_BASIC_INFO_KEYS = {
    "first_name_furigana",
    "last_name_furigana",
    "birth_day",
    "birth_date",
    "gender",
}


def mask_email(email: Optional[str]) -> str:
    """
    メールアドレスをマスキング

    ローカル部分の最初の1文字のみ表示し、残りを***に置き換える
    ドメイン部分はそのまま表示

    Args:
        email: メールアドレス（例: "test@example.com"）

    Returns:
        マスキングされたメールアドレス（例: "t***@example.com"）
        不正な形式またはNoneの場合は "***"

    Examples:
        >>> mask_email("test@example.com")
        't***@example.com'

        >>> mask_email("a@example.com")
        'a***@example.com'

        >>> mask_email(None)
        '***'

        >>> mask_email("invalid")
        '***'
    """
    if email is None:
        return "***"

    if "@" not in email:
        return "***"

    try:
        local, domain = email.split("@", 1)
        if len(local) == 0:
            return "***"

        masked_local = local[0] + "***"
        return f"{masked_local}@{domain}"

    except Exception:
        return "***"


def mask_name(name: Optional[str]) -> str:
    """
    個人名をマスキング

    姓は表示し、名を*に置き換える
    スペース区切りの場合は最初の部分のみ表示

    Args:
        name: 個人名（例: "山田 太郎"）

    Returns:
        マスキングされた名前（例: "山田 *"）
        Noneの場合は "***"

    Examples:
        >>> mask_name("山田 太郎")
        '山田 *'

        >>> mask_name("太郎")
        '*'

        >>> mask_name(None)
        '***'
    """
    if name is None:
        return "***"

    if " " in name:
        parts = name.split(" ", 1)
        return f"{parts[0]} *"
    else:
        return "*"


def mask_external_id(value: Optional[Any]) -> Optional[str]:
    """
    外部サービスIDをログ・表示用にpresenceだけへ変換する。
    """
    return PRESENT if value not in (None, "") else None


def mask_ip_address(value: Optional[str]) -> Optional[str]:
    """Mask an audit IP to a network prefix without retaining the host address."""
    if not value:
        return value
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError:
            return REDACTED
        prefix = 24 if network.version == 4 else 64
        return f"{network.network_address}/{prefix}"

    prefix = 24 if address.version == 4 else 64
    network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    return f"{network.network_address}/{prefix}"


def hash_user_agent(value: Optional[str]) -> Optional[str]:
    """Store a short correlation hash rather than the raw User-Agent."""
    if not value:
        return value
    if value == REDACTED:
        return REDACTED
    if re.fullmatch(r"ua:[0-9a-f]{16}", value):
        return value
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"ua:{digest}"


def sanitize_log_value(value: Any) -> Any:
    """
    ログ出力用に値を安全な表現へ変換する。

    dict/listは再帰的に処理し、文字列などの単一値は外部IDとしてpresence化する。
    """
    if isinstance(value, dict):
        return {
            key: _sanitize_log_dict_value(str(key), item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [sanitize_log_value(item) for item in value]

    return mask_external_id(value)


def _sanitize_log_dict_value(key: str, value: Any) -> Any:
    normalized_key = key.lower()

    if _matches_detail_key(normalized_key, EMAIL_DETAIL_KEYS):
        return mask_email(str(value)) if value is not None else "***"

    if _matches_detail_key(normalized_key, NAME_DETAIL_KEYS):
        return mask_name(str(value)) if value is not None else "***"

    if (
        normalized_key in WEBHOOK_PRESENT_ONLY_KEYS
        or _matches_detail_key(normalized_key, PRESENT_ONLY_DETAIL_KEYS)
    ):
        return mask_external_id(value)

    if _matches_detail_key(normalized_key, REDACT_DETAIL_KEYS):
        return REDACTED if value not in (None, "") else None

    return sanitize_log_value(value)


def mask_employee_action_request_data_for_display(value: Any) -> Any:
    """
    Employee action request_dataの表示用マスキング。

    承認判断用のメタ情報は残し、利用者ドメインの詳細情報は表示用に最小化する。
    """
    if not isinstance(value, dict):
        return value

    masked: dict[str, Any] = {}
    resource_type = value.get("resource_type")

    for key, item in value.items():
        if key in EMPLOYEE_ACTION_REQUEST_META_KEYS:
            masked[key] = item
        elif key == "original_request_data" and resource_type == "welfare_recipient":
            masked[key] = _mask_welfare_recipient_request_data(item)
        elif key == "original_request_data":
            masked[key] = mask_sensitive_details_for_display(item)
        else:
            masked[key] = mask_sensitive_details_for_display(item)

    return masked


def _mask_welfare_recipient_request_data(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    masked: dict[str, Any] = {}
    for key, item in value.items():
        if key in WELFARE_RECIPIENT_REDACT_SECTIONS:
            masked[key] = REDACTED
        elif key == "basic_info":
            masked[key] = _mask_welfare_recipient_basic_info(item)
        else:
            masked[key] = mask_sensitive_details_for_display(item)

    return masked


def _mask_welfare_recipient_basic_info(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    masked: dict[str, Any] = {}
    for key, item in value.items():
        if key == "last_name":
            masked[key] = f"{item} *" if item else "***"
        elif key == "first_name":
            masked[key] = "*"
        elif key in WELFARE_RECIPIENT_REDACT_BASIC_INFO_KEYS:
            masked[key] = REDACTED if item not in (None, "") else None
        else:
            masked[key] = mask_sensitive_details_for_display(item)

    return masked


def mask_sensitive_details_for_display(value: Any) -> Any:
    """
    表示用の任意detailsから個人情報・秘密情報を除去する。

    監査ログの保存値は変更せず、APIレスポンス生成時の表示データにだけ使う。
    """
    if isinstance(value, dict):
        return {
            key: _mask_detail_value(str(key), detail_value)
            for key, detail_value in value.items()
        }

    if isinstance(value, list):
        return [mask_sensitive_details_for_display(item) for item in value]

    return value


def sanitize_audit_log_details_for_storage(value: Any, *, action: Optional[str] = None) -> Any:
    """
    監査ログ保存用のdetails sanitizer。

    保存前に明らかな機微情報を除去し、表示時マスクだけに依存しない。
    非機微な件数・状態などの監査に必要な値は保持する。
    """
    if not action:
        return _redact_unknown_details(value)

    allowed_keys = AUDIT_LOG_ACTION_ALLOWED_DETAIL_KEYS.get(action)
    if allowed_keys is None:
        return _redact_unknown_details(value)

    if action == "email_send_failed" and isinstance(value, dict):
        allowed_email_keys = {
            "recipient", "subject", "error", "error_type", "email_type", "retry_count",
        }
        sanitized = {
            key: _sanitize_email_failure_detail(key, item)
            for key, item in value.items()
            if key in allowed_email_keys
        }
        if len(sanitized) != len(value):
            sanitized[REDACTED_DETAIL_KEY] = REDACTED
        return sanitized

    if not isinstance(value, dict):
        return REDACTED if value not in (None, "") else None

    sanitized = {
        key: _sanitize_allowed_audit_detail(key, item)
        for key, item in value.items()
        if key in allowed_keys
    }
    if len(sanitized) != len(value):
        sanitized[REDACTED_DETAIL_KEY] = REDACTED
    return sanitized


def _redact_unknown_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {REDACTED_DETAIL_KEY: REDACTED} if value else {}
    return REDACTED if value not in (None, "") else None


def _sanitize_allowed_audit_detail(key: str, value: Any) -> Any:
    normalized_key = key.lower()
    if normalized_key in AUDIT_PRESENCE_ONLY_DETAIL_KEYS or normalized_key == "id" or normalized_key.endswith("_id"):
        return PRESENT if value not in (None, "") else None
    if _matches_detail_key(normalized_key, EMAIL_DETAIL_KEYS):
        return mask_email(str(value)) if value is not None else "***"
    if _matches_detail_key(normalized_key, NAME_DETAIL_KEYS):
        return mask_name(str(value)) if value is not None else "***"
    if _matches_detail_key(normalized_key, REDACT_DETAIL_KEYS):
        return REDACTED if value not in (None, "") else None
    if isinstance(value, (dict, list)):
        return _sanitize_nested_audit_value(value)
    return _sanitize_allowed_scalar(value)


def _sanitize_allowed_scalar(value: Any) -> Any:
    """Keep only bounded, control-character-free audit scalar values."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if -(10**12) <= value <= 10**12 else REDACTED
    if isinstance(value, float):
        return value if value == value and abs(value) <= 10**12 else REDACTED
    if isinstance(value, str):
        return value if SAFE_AUDIT_STRING_PATTERN.fullmatch(value) else REDACTED
    return REDACTED


def _sanitize_nested_audit_value(value: Any) -> Any:
    """Keep only non-string metrics and known masked fields in nested details."""
    if isinstance(value, list):
        return [_sanitize_nested_audit_value(item) for item in value]
    if not isinstance(value, dict):
        return value if isinstance(value, (bool, int, float)) else REDACTED

    sanitized: dict[str, Any] = {}
    unknown_key_found = False
    for key, item in value.items():
        normalized_key = str(key).lower()
        if _matches_detail_key(normalized_key, EMAIL_DETAIL_KEYS):
            sanitized[key] = mask_email(str(item)) if item is not None else "***"
        elif _matches_detail_key(normalized_key, NAME_DETAIL_KEYS):
            sanitized[key] = mask_name(str(item)) if item is not None else "***"
        elif (
            normalized_key in AUDIT_PRESENCE_ONLY_DETAIL_KEYS
            or normalized_key == "id"
            or normalized_key.endswith("_id")
            or _matches_detail_key(normalized_key, PRESENT_ONLY_DETAIL_KEYS)
        ):
            sanitized[key] = PRESENT if item not in (None, "") else None
        elif _matches_detail_key(normalized_key, REDACT_DETAIL_KEYS):
            sanitized[key] = REDACTED if item not in (None, "") else None
        elif normalized_key in NESTED_AUDIT_ALLOWED_SCALAR_KEYS:
            sanitized[key] = _sanitize_allowed_scalar(item)
        else:
            unknown_key_found = True
    if unknown_key_found:
        sanitized[REDACTED_DETAIL_KEY] = REDACTED
    return sanitized


def _sanitize_email_failure_detail(key: str, value: Any) -> Any:
    if key in {"recipient", "subject", "error"}:
        return REDACTED if value not in (None, "") else None
    if key == "error_type":
        return value if isinstance(value, str) and value.isidentifier() else REDACTED
    if key == "email_type":
        normalized = str(value or "")
        return normalized if re.fullmatch(r"[a-z0-9_.-]{1,64}", normalized) else REDACTED
    if key == "retry_count":
        return value if isinstance(value, int) and 0 <= value <= 100 else REDACTED
    return REDACTED


def _mask_detail_value(key: str, value: Any) -> Any:
    normalized_key = key.lower()

    if _matches_detail_key(normalized_key, EMAIL_DETAIL_KEYS):
        return mask_email(str(value)) if value is not None else "***"

    if _matches_detail_key(normalized_key, NAME_DETAIL_KEYS):
        return mask_name(str(value)) if value is not None else "***"

    if _matches_detail_key(normalized_key, PRESENT_ONLY_DETAIL_KEYS):
        return PRESENT if value not in (None, "") else None

    if _matches_detail_key(normalized_key, REDACT_DETAIL_KEYS):
        return REDACTED if value not in (None, "") else None

    return mask_sensitive_details_for_display(value)


def _matches_detail_key(key: str, sensitive_keys: set[str]) -> bool:
    return any(
        key == sensitive_key
        or key.endswith(f"_{sensitive_key}")
        or sensitive_key in key
        for sensitive_key in sensitive_keys
    )


def mask_webhook_payload_for_display(value: Any) -> Any:
    """
    Webhook payload表示用にallowlistベースでマスキングする。

    保存用payloadは変更せず、APIレスポンスや管理画面表示に使う。
    """
    return _mask_webhook_payload_value(value, path=())


def _mask_webhook_payload_value(value: Any, path: tuple[str, ...]) -> Any:
    if isinstance(value, list):
        return [_mask_webhook_payload_value(item, path=path) for item in value]

    if not isinstance(value, dict):
        return value

    masked: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key).lower()
        masked[key] = _mask_webhook_key_value(normalized_key, item, path)
    return masked


def _mask_webhook_key_value(key: str, value: Any, path: tuple[str, ...]) -> Any:
    if path == ():
        if key not in WEBHOOK_TOP_LEVEL_KEYS:
            return REDACTED
        if key == "data":
            return _mask_webhook_payload_value(value, path=("data",))
        return value

    if path == ("data",):
        if key not in WEBHOOK_DATA_KEYS:
            return REDACTED
        return _mask_webhook_payload_value(value, path=("data", key))

    if path in {("data", "object"), ("data", "previous_attributes")}:
        if _matches_detail_key(key, EMAIL_DETAIL_KEYS):
            return mask_email(str(value)) if value is not None else "***"

        if _matches_detail_key(key, NAME_DETAIL_KEYS):
            return mask_name(str(value)) if value is not None else "***"

        if _matches_detail_key(key, REDACT_DETAIL_KEYS):
            return REDACTED if value not in (None, "") else None

        if key in WEBHOOK_PRESENT_ONLY_KEYS:
            return PRESENT if value not in (None, "") else None

        if key in WEBHOOK_OBJECT_SAFE_KEYS:
            return _mask_webhook_payload_value(value, path=path + (key,))

        return REDACTED

    return REDACTED
