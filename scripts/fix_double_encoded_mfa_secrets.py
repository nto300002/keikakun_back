"""
二重Base64エンコードされたMFAシークレットを修正するスクリプト

使用方法:
    python -m scripts.fix_double_encoded_mfa_secrets

このスクリプトは以下を実行します:
1. MFAシークレットを持つ全スタッフを取得
2. 既存の二重エンコード方式で復号化
3. 新しい単一エンコード方式で再暗号化
4. データベースを更新
"""

import asyncio
import base64
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet

from app.db.session import async_session_maker
from app.models.staff import Staff
from app.core.config import settings


def get_encryption_key() -> bytes:
    """暗号化キーを取得（app.core.securityと同じロジック）"""
    import os
    key_source = os.getenv("ENCRYPTION_KEY", os.getenv("SECRET_KEY", "test_secret_key_for_pytest"))
    key_bytes = key_source.encode()[:32].ljust(32, b'0')
    return base64.urlsafe_b64encode(key_bytes)


async def fix_double_encoded_secrets():
    """
    二重Base64エンコードされたMFAシークレットを修正
    """
    print("=" * 70)
    print("MFA二重エンコード修復スクリプト")
    print("=" * 70)
    print()

    fernet = Fernet(get_encryption_key())

    async with async_session_maker() as db:
        # MFAシークレットを持つ全スタッフを取得
        result = await db.execute(
            select(Staff).where(Staff.mfa_secret.isnot(None))
        )
        staffs = result.scalars().all()

        if not staffs:
            print("✅ MFAシークレットを持つスタッフが見つかりませんでした。")
            return

        print(f"🔍 {len(staffs)} 人のスタッフのMFAシークレットを確認します...\n")

        fixed_count = 0
        already_correct_count = 0
        failed_count = 0

        for staff in staffs:
            try:
                print(f"処理中: staff_id={staff.id}")

                # 既存の二重デコード方式で復号化を試行
                try:
                    encrypted_bytes = base64.urlsafe_b64decode(staff.mfa_secret.encode())
                    decrypted = fernet.decrypt(encrypted_bytes)
                    factor_value = decrypted.decode()

                    # 二重エンコードされていた場合
                    print(f"  ⚠️  二重エンコードを検出しました")
                    print(f"  📝 復号化されたMFA factor length: {len(factor_value)}")

                    # 正しい方法で再暗号化（単一エンコード）
                    new_encrypted = fernet.encrypt(factor_value.encode()).decode()

                    # データベースを更新
                    staff.mfa_secret = new_encrypted
                    fixed_count += 1
                    print(f"  ✅ 修正完了: staff_id={staff.id}")

                except Exception as e1:
                    # 二重デコードに失敗した場合、既に正しい形式の可能性がある
                    try:
                        # 新しい単一エンコード方式で復号化を試行
                        decrypted = fernet.decrypt(staff.mfa_secret.encode())
                        plain_secret = decrypted.decode()

                        # 成功したら既に正しい形式
                        already_correct_count += 1
                        print(f"  ℹ️  既に正しい形式です（修正不要）")

                    except Exception as e2:
                        # どちらの方式でも復号化できない場合
                        failed_count += 1
                        print(f"  ❌ 復号化失敗: staff_id={staff.id}")
                        print(f"     二重デコードエラー: {type(e1).__name__}")
                        print(f"     単一デコードエラー: {type(e2).__name__}")
                        print(f"     ⚠️  このスタッフはMFAの再設定が必要です")

                print()

            except Exception as e:
                failed_count += 1
                print(f"  ❌ 処理エラー: staff_id={staff.id} - {type(e).__name__}\n")

        # 変更をコミット
        if fixed_count > 0:
            await db.commit()
            print("💾 データベースの変更をコミットしました\n")

        # 結果サマリー
        print("=" * 70)
        print("修復結果サマリー")
        print("=" * 70)
        print(f"✅ 修正完了:     {fixed_count} 人")
        print(f"ℹ️  修正不要:     {already_correct_count} 人")
        print(f"❌ 修正失敗:     {failed_count} 人")
        print(f"📊 合計:         {len(staffs)} 人")
        print()

        if failed_count > 0:
            print("⚠️  警告: 修正に失敗したスタッフはMFAの再設定が必要です")
            print("   管理者画面から各スタッフのMFAを無効化→有効化してください")

        if fixed_count > 0:
            print(f"\n🎉 {fixed_count} 人のMFAシークレットを正常に修正しました！")


async def main():
    """メイン処理"""
    try:
        await fix_double_encoded_secrets()
    except KeyboardInterrupt:
        print("\n\n⚠️  処理が中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ エラーが発生しました: {type(e).__name__}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
