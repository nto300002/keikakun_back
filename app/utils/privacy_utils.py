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
from typing import Any, Optional


REDACTED = "<redacted>"
PRESENT = "<present>"

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
