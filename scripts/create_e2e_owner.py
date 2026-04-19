"""
E2Eテスト用 owner スタッフアカウントを作成するスクリプト

GitHub Actions の E2E テストで使用するテスト専用 owner アカウント（事業所付き）を生成する。
作成後、GitHub Actions Secrets に E2E_OWNER_EMAIL / E2E_OWNER_PASSWORD として登録する。

使用方法:
  docker compose exec backend python scripts/create_e2e_owner.py <email> <password>

例:
  docker compose exec backend python scripts/create_e2e_owner.py e2e_owner@example.com "E2ePass123!"

引数:
  - email:    メールアドレス（GitHub Actions Secret の E2E_OWNER_EMAIL に使用）
  - password: パスワード（GitHub Actions Secret の E2E_OWNER_PASSWORD に使用）

作成されるデータ:
  - staffs テーブル:      owner ロールのスタッフ（MFA無効・メール認証済み）
  - offices テーブル:     E2Eテスト用事業所
  - office_staffs テーブル: スタッフと事業所の紐付け
  - billings テーブル:    active ステータスの課金レコード（操作制限なし）

注意:
  - is_test_data=True でマーク → テストDBクリーンアップ対象にならないよう運用で管理
  - MFA は無効化（is_mfa_enabled=False）← ログインをシンプルにするため
  - 本番DBには実行しないこと（dev/staging のみ）
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.billing import Billing
from app.models.enums import StaffRole, OfficeType, BillingStatus
from app.core.security import get_password_hash


async def create_e2e_owner(email: str, password: str) -> bool:
    """
    E2Eテスト用 owner アカウントを作成する

    Args:
        email:    メールアドレス
        password: パスワード（平文）

    Returns:
        成功した場合は True
    """
    async with async_session_maker() as db:
        # --- 重複チェック ---
        existing = await db.execute(select(Staff).where(Staff.email == email))
        if existing.scalar_one_or_none():
            print(f"[skip] Staff with email '{email}' already exists.")
            print("       既存アカウントをそのまま GitHub Actions Secret に登録してください。")
            return True

        # --- 1. Staff（owner）を作成 ---
        staff = Staff(
            email=email,
            hashed_password=get_password_hash(password),
            role=StaffRole.owner,
            first_name="テスト",
            last_name="E2E",
            full_name="E2E テスト",
            is_email_verified=True,   # メール認証をスキップ
            is_mfa_enabled=False,     # MFAを無効化（E2Eログインを簡素化）
            password_changed_at=datetime.now(timezone.utc),
            is_test_data=False,       # 通常のクリーンアップ対象外
        )
        db.add(staff)
        await db.flush()  # staff.id を確定させる

        # --- 2. Office（事業所）を作成 ---
        office = Office(
            name="E2Eテスト事業所",
            type=OfficeType.transition_to_employment,
            created_by=staff.id,
            last_modified_by=staff.id,
            is_test_data=False,
        )
        db.add(office)
        await db.flush()  # office.id を確定させる

        # --- 3. OfficeStaff（スタッフ↔事業所の紐付け）---
        office_staff = OfficeStaff(
            staff_id=staff.id,
            office_id=office.id,
            is_primary=True,
            is_test_data=False,
        )
        db.add(office_staff)

        # --- 4. Billing（active ステータス）---
        now = datetime.now(timezone.utc)
        billing = Billing(
            office_id=office.id,
            billing_status=BillingStatus.active,
            trial_start_date=now,
            trial_end_date=now + timedelta(days=180),
            subscription_start_date=now,
        )
        db.add(billing)

        await db.commit()

        print("=" * 50)
        print("✅ E2Eテスト用 owner アカウントを作成しました")
        print("=" * 50)
        print(f"  Email   : {email}")
        print(f"  Password: {password}")
        print(f"  Staff ID: {staff.id}")
        print(f"  Office  : E2Eテスト事業所 (id={office.id})")
        print(f"  Billing : {BillingStatus.active.value}")
        print()
        print("GitHub Actions Secrets に以下を登録してください:")
        print(f"  E2E_OWNER_EMAIL    = {email}")
        print(f"  E2E_OWNER_PASSWORD = {password}")
        return True


if __name__ == "__main__":
    # CLI 引数優先、なければ環境変数から取得（CI での秘密情報漏洩防止）
    if len(sys.argv) == 3:
        email = sys.argv[1]
        password = sys.argv[2]
    else:
        email = os.environ.get("E2E_OWNER_EMAIL", "")
        password = os.environ.get("E2E_OWNER_PASSWORD", "")

    if not email or not password:
        print("使用方法 (引数): python scripts/create_e2e_owner.py <email> <password>")
        print("使用方法 (env):  E2E_OWNER_EMAIL=... E2E_OWNER_PASSWORD=... python scripts/create_e2e_owner.py")
        sys.exit(1)

    success = asyncio.run(create_e2e_owner(email, password))
    sys.exit(0 if success else 1)
