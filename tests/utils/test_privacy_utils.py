"""
PII保護ユーティリティのテスト

テスト対象:
- メールアドレスのマスキング
- 個人名のマスキング（オプション）
"""
import pytest

from app.utils.privacy_utils import (
    mask_email,
    mask_employee_action_request_data_for_display,
    mask_external_id,
    mask_name,
    mask_sensitive_details_for_display,
    mask_webhook_payload_for_display,
    sanitize_log_value,
)


def test_mask_email_standard():
    """
    標準的なメールアドレスのマスキング

    検証内容:
    - test@example.com → t***@example.com
    """
    result = mask_email("test@example.com")
    assert result == "t***@example.com"


def test_mask_email_short():
    """
    短いメールアドレスのマスキング

    検証内容:
    - a@example.com → a***@example.com
    """
    result = mask_email("a@example.com")
    assert result == "a***@example.com"


def test_mask_email_long_local_part():
    """
    長いローカル部分のメールアドレスのマスキング

    検証内容:
    - verylongemail@example.com → v***@example.com
    """
    result = mask_email("verylongemail@example.com")
    assert result == "v***@example.com"


def test_mask_email_none():
    """
    Noneの場合の処理

    検証内容:
    - None → "***"
    """
    result = mask_email(None)
    assert result == "***"


def test_mask_email_invalid():
    """
    不正な形式の場合の処理

    検証内容:
    - "invalid" → "***"
    """
    result = mask_email("invalid")
    assert result == "***"


def test_mask_name_full():
    """
    フルネームのマスキング

    検証内容:
    - "山田 太郎" → "山田 *"
    """
    result = mask_name("山田 太郎")
    assert result == "山田 *"


def test_mask_name_single():
    """
    単一の名前のマスキング

    検証内容:
    - "太郎" → "*"
    """
    result = mask_name("太郎")
    assert result == "*"


def test_mask_name_none():
    """
    Noneの場合の処理

    検証内容:
    - None → "***"
    """
    result = mask_name(None)
    assert result == "***"


def test_mask_external_id_returns_presence_only():
    """
    外部サービスIDはログ用にpresenceだけへ変換する
    """
    assert mask_external_id("cus_1234567890abcdef") == "<present>"
    assert mask_external_id("") is None
    assert mask_external_id(None) is None


def test_sanitize_log_value_masks_nested_sensitive_values():
    """
    ログ用の再帰sanitizer
    """
    result = sanitize_log_value({
        "customer": "cus_1234567890abcdef",
        "invoice": "in_1234567890abcdef",
        "email": "payer@example.com",
        "client_secret": "secret-value",
        "items": [{"payment_intent": "pi_1234567890abcdef"}],
    })

    assert result == {
        "customer": "<present>",
        "invoice": "<present>",
        "email": "p***@example.com",
        "client_secret": "<redacted>",
        "items": [{"payment_intent": "<present>"}],
    }


def test_mask_employee_action_request_data_for_display_masks_welfare_recipient_sections():
    """
    Employee action request_data表示用の福祉利用者ドメインマスキング
    """
    result = mask_employee_action_request_data_for_display({
        "resource_type": "welfare_recipient",
        "action_type": "create",
        "original_request_data": {
            "basic_info": {
                "last_name": "山田",
                "first_name": "太郎",
                "last_name_furigana": "ヤマダ",
                "birth_day": "1990-01-01",
            },
            "contact_address": {"phone_number": "090-1234-5678"},
            "emergency_contacts": [{"name": "山田 花子"}],
            "disability_info": {"disability_type": "精神障害"},
            "disability_details": [{"notes": "詳細な病歴"}],
        },
    })

    assert result == {
        "resource_type": "welfare_recipient",
        "action_type": "create",
        "original_request_data": {
            "basic_info": {
                "last_name": "山田 *",
                "first_name": "*",
                "last_name_furigana": "<redacted>",
                "birth_day": "<redacted>",
            },
            "contact_address": "<redacted>",
            "emergency_contacts": "<redacted>",
            "disability_info": "<redacted>",
            "disability_details": "<redacted>",
        },
    }


def test_mask_sensitive_details_for_display_recursively_masks_known_sensitive_keys():
    """
    監査ログdetails表示用の再帰マスキング

    検証内容:
    - 個人情報・秘密情報はキー名ベースでマスキングされる
    - 非機微な件数などは保持される
    """
    result = mask_sensitive_details_for_display({
        "email": "sensitive.user@example.com",
        "full_name": "山田 太郎",
        "stripe_customer_id": "cus_1234567890abcdef",
        "access_token": "raw-access-token-value",
        "raw_payload": {"customer_email": "customer@example.com"},
        "changes": {
            "address": "東京都新宿区1-2-3",
            "phone_number": "090-1234-5678",
            "recipient": "reply-target@example.com",
            "safe_count": 2,
        },
    })

    assert result == {
        "email": "s***@example.com",
        "full_name": "山田 *",
        "stripe_customer_id": "<present>",
        "access_token": "<redacted>",
        "raw_payload": "<redacted>",
        "changes": {
            "address": "<redacted>",
            "phone_number": "<redacted>",
            "recipient": "r***@example.com",
            "safe_count": 2,
        },
    }


def test_mask_webhook_payload_for_display_uses_allowlist_and_masks_sensitive_values():
    """
    Webhook payload表示用のallowlistマスキング

    検証内容:
    - Stripe処理確認に必要な最小フィールドは保持される
    - 顧客メール、氏名、住所、秘密値、未定義keyは生値で残らない
    """
    result = mask_webhook_payload_for_display({
        "id": "evt_test_123",
        "type": "invoice.payment_succeeded",
        "livemode": False,
        "data": {
            "object": {
                "id": "in_1234567890abcdef",
                "object": "invoice",
                "customer": "cus_1234567890abcdef",
                "subscription": "sub_1234567890abcdef",
                "amount_paid": 6000,
                "currency": "jpy",
                "status": "paid",
                "customer_email": "payer@example.com",
                "customer_name": "山田 太郎",
                "customer_address": {"line1": "東京都新宿区1-2-3"},
                "metadata": {"internal_note": "raw note"},
                "client_secret": "secret-value",
            },
        },
        "unexpected": "raw unexpected value",
    })

    assert result["id"] == "evt_test_123"
    assert result["type"] == "invoice.payment_succeeded"
    assert result["livemode"] is False
    assert result["data"]["object"]["id"] == "<present>"
    assert result["data"]["object"]["customer"] == "<present>"
    assert result["data"]["object"]["subscription"] == "<present>"
    assert result["data"]["object"]["amount_paid"] == 6000
    assert result["data"]["object"]["currency"] == "jpy"
    assert result["data"]["object"]["status"] == "paid"
    assert result["data"]["object"]["customer_email"] == "p***@example.com"
    assert result["data"]["object"]["customer_name"] == "山田 *"
    assert result["data"]["object"]["customer_address"] == "<redacted>"
    assert result["data"]["object"]["metadata"] == "<redacted>"
    assert result["data"]["object"]["client_secret"] == "<redacted>"
    assert result["unexpected"] == "<redacted>"
    assert "payer@example.com" not in str(result)
    assert "山田 太郎" not in str(result)
    assert "東京都新宿区1-2-3" not in str(result)
    assert "secret-value" not in str(result)
    assert "raw unexpected value" not in str(result)
