"""
app_admin用の合言葉を設定するスクリプト

使用方法:
  docker compose exec backend python scripts/set_admin_passphrase.py <email> <passphrase>

例:
  docker compose exec backend python scripts/set_admin_passphrase.py admin@example.com "secret123!"

注意:
  - app_admin ロールを持つユーザーにのみ設定可能
  - 合言葉は最低8文字必要
  - 合言葉はbcryptでハッシュ化されて保存される
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.staff import Staff
from app.models.enums import StaffRole
from app.core.security import get_password_hash


async def set_passphrase(email: str, passphrase: str) -> bool:
    """
    app_adminユーザーの合言葉を設定

    Args:
        email: app_adminのメールアドレス
        passphrase: 設定する合言葉（平文）

    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    async with async_session_maker() as db:
        # app_adminを取得
        result = await db.execute(
            select(Staff).where(
                Staff.email == email,
                Staff.role == StaffRole.app_admin
            )
        )
        admin = result.scalar_one_or_none()

        if not admin:
            print(f"Error: app_admin with email '{email}' not found")
            print("Note: This script only works for users with role='app_admin'")
            return False

        # 合言葉をハッシュ化して設定
        admin.hashed_passphrase = get_password_hash(passphrase)
        admin.passphrase_changed_at = datetime.now(timezone.utc)
        await db.commit()

        print(f"Passphrase successfully set for {email}")
        print(f"  Changed at: {admin.passphrase_changed_at.isoformat()}")
        return True


def validate_passphrase(passphrase: str) -> tuple[bool, str]:
    """
    合言葉のバリデーション

    Args:
        passphrase: 検証する合言葉

    Returns:
        (有効かどうか, エラーメッセージ)
    """
    if len(passphrase) < 8:
        return False, "Passphrase must be at least 8 characters"

    # 少なくとも1つの数字を含む
    if not any(c.isdigit() for c in passphrase):
        return False, "Passphrase must contain at least one digit"

    # 少なくとも1つの英字を含む
    if not any(c.isalpha() for c in passphrase):
        return False, "Passphrase must contain at least one letter"

    return True, ""


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/set_admin_passphrase.py <email> <passphrase>")
        print("Example: python scripts/set_admin_passphrase.py admin@example.com 'my_secret123!'")
        print()
        print("Requirements:")
        print("  - Passphrase must be at least 8 characters")
        print("  - Passphrase must contain at least one digit")
        print("  - Passphrase must contain at least one letter")
        sys.exit(1)

    email = sys.argv[1]
    passphrase = sys.argv[2]

    # パスフレーズのバリデーション
    is_valid, error_msg = validate_passphrase(passphrase)
    if not is_valid:
        print(f"Error: {error_msg}")
        sys.exit(1)

    # 合言葉を設定
    success = asyncio.run(set_passphrase(email, passphrase))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
