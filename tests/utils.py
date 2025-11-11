"""
後方互換性のため残しているファイル
新しいインポート元は tests.utils.helpers
"""
# tests/utils/helpers.pyから全ての関数と定数をインポート
from tests.utils.helpers import (
    create_welfare_recipient,
    random_email,
    random_string,
    random_password,
    create_random_staff,
    create_admin_staff,
    create_manager_staff,
    get_staff_password,
    TestDataFactory,
    load_staff_with_office,
    TEST_STAFF_PASSWORD,
    TEST_ADMIN_EMAIL,
    TEST_EMPLOYEE_EMAIL,
    TEST_MANAGER_EMAIL,
)

__all__ = [
    "create_welfare_recipient",
    "random_email",
    "random_string",
    "random_password",
    "create_random_staff",
    "create_admin_staff",
    "create_manager_staff",
    "get_staff_password",
    "TestDataFactory",
    "load_staff_with_office",
    "TEST_STAFF_PASSWORD",
    "TEST_ADMIN_EMAIL",
    "TEST_EMPLOYEE_EMAIL",
    "TEST_MANAGER_EMAIL",
]