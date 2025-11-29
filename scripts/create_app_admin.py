"""
app_adminユーザーを新規作成するスクリプト

使用方法:
  docker compose exec backend python scripts/create_app_admin.py <first_name> <last_name> <email> <password> <passphrase>

例:
  docker compose exec backend python scripts/create_app_admin.py "太郎" "山田" admin@example.com "MyPassword123!" "secret123!"

引数:
  - first_name: 名（例: 太郎）
  - last_name: 姓（例: 山田）
  - email: メールアドレス
  - password: パスワード
  - passphrase: 合言葉（セカンドパスワード）

注意:
  - first_name/last_nameは日本語（ひらがな・カタカナ・漢字）のみ使用可能
  - passwordは最低8文字、数字と英字を含む必要がある
  - passphraseは最低8文字、数字と英字を含む必要がある
  - passwordとpassphraseは両方bcryptでハッシュ化されて保存される
  - roleは自動的にapp_adminに設定される
  - full_nameは"{last_name} {first_name}"の形式で自動生成される
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


async def create_app_admin(first_name: str, last_name: str, email: str, password: str, passphrase: str) -> bool:
    """
    app_adminユーザーを新規作成

    Args:
        first_name: 名（平文）
        last_name: 姓（平文）
        email: メールアドレス
        password: パスワード（平文）
        passphrase: 合言葉（平文）

    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    async with async_session_maker() as db:
        # 同じメールアドレスのユーザーが既に存在するかチェック
        result = await db.execute(
            select(Staff).where(Staff.email == email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"Error: User with email '{email}' already exists")
            return False

        # 新しいapp_adminユーザーを作成
        new_admin = Staff(
            email=email,
            hashed_password=get_password_hash(password),
            role=StaffRole.app_admin,
            hashed_passphrase=get_password_hash(passphrase),
            passphrase_changed_at=datetime.now(timezone.utc),
            password_changed_at=datetime.now(timezone.utc),
            is_email_verified=True,  # app_adminは自動的に検証済みとする
            first_name=first_name,
            last_name=last_name,
            full_name=f"{last_name} {first_name}",  # 自動生成: {last_name} {first_name}
            is_test_data=False
        )

        db.add(new_admin)
        await db.commit()
        await db.refresh(new_admin)

        print(f"✓ App admin user created successfully")
        print(f"  ID: {new_admin.id}")
        print(f"  Name: {new_admin.full_name}")
        print(f"  Email: {new_admin.email}")
        print(f"  Role: {new_admin.role.value}")
        print(f"  Created at: {new_admin.created_at.isoformat()}")
        return True


def validate_name(name: str, field_name: str) -> tuple[bool, str]:
    """
    名前のバリデーション（StaffBaseスキーマと同じルール）

    Args:
        name: 検証する名前
        field_name: フィールド名（エラーメッセージ用）

    Returns:
        (有効かどうか, エラーメッセージ)
    """
    import re

    # 空白のトリミング
    name = name.strip()

    if not name:
        return False, f"{field_name} cannot be empty"

    # 50文字制限
    if len(name) > 50:
        return False, f"{field_name} must be 50 characters or less"

    # 数字のみの名前を禁止
    if name.replace(' ', '').replace('　', '').isdigit():
        return False, f"{field_name} cannot be only numbers"

    # 使用可能文字のチェック
    # 日本語（ひらがな・カタカナ・漢字）、全角スペース、・（中点）、々（同じく）のみ許可
    allowed_pattern = r'^[ぁ-ん ァ-ヶー一-龥々・　]+$'
    if not re.match(allowed_pattern, name):
        return False, f"{field_name} must contain only Japanese characters (Hiragana, Katakana, Kanji)"

    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """
    パスワードのバリデーション

    Args:
        password: 検証するパスワード

    Returns:
        (有効かどうか, エラーメッセージ)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"

    # 少なくとも1つの数字を含む
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    # 少なくとも1つの英字を含む
    if not any(c.isalpha() for c in password):
        return False, "Password must contain at least one letter"

    return True, ""


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
    if len(sys.argv) != 6:
        print("Usage: python scripts/create_app_admin.py <first_name> <last_name> <email> <password> <passphrase>")
        print("Example: python scripts/create_app_admin.py '太郎' '山田' admin@example.com 'MyPassword123!' 'secret123!'")
        print()
        print("Requirements:")
        print("  - first_name/last_name: Japanese characters only (Hiragana, Katakana, Kanji)")
        print("  - first_name/last_name: 50 characters or less")
        print("  - Password must be at least 8 characters")
        print("  - Password must contain at least one digit")
        print("  - Password must contain at least one letter")
        print("  - Passphrase must be at least 8 characters")
        print("  - Passphrase must contain at least one digit")
        print("  - Passphrase must contain at least one letter")
        sys.exit(1)

    first_name = sys.argv[1]
    last_name = sys.argv[2]
    email = sys.argv[3]
    password = sys.argv[4]
    passphrase = sys.argv[5]

    # 名前のバリデーション
    is_valid, error_msg = validate_name(first_name, "first_name")
    if not is_valid:
        print(f"Error (first_name): {error_msg}")
        sys.exit(1)

    is_valid, error_msg = validate_name(last_name, "last_name")
    if not is_valid:
        print(f"Error (last_name): {error_msg}")
        sys.exit(1)

    # パスワードのバリデーション
    is_valid, error_msg = validate_password(password)
    if not is_valid:
        print(f"Error (password): {error_msg}")
        sys.exit(1)

    # パスフレーズのバリデーション
    is_valid, error_msg = validate_passphrase(passphrase)
    if not is_valid:
        print(f"Error (passphrase): {error_msg}")
        sys.exit(1)

    # app_adminユーザーを作成
    success = asyncio.run(create_app_admin(first_name, last_name, email, password, passphrase))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
