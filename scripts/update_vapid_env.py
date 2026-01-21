"""
VAPID鍵ペアをPEMファイルから読み込んで環境変数用の値を生成するスクリプト

使い方:
    docker exec keikakun_app-backend-1 python3 scripts/update_vapid_env.py

出力:
    .envファイルに追加すべき環境変数の値を表示します。
"""
import sys
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

sys.path.insert(0, '/app')


def generate_vapid_env_variables():
    """PEMファイルからVAPID環境変数を生成"""
    print("\n" + "=" * 70)
    print("VAPID環境変数生成ツール")
    print("=" * 70 + "\n")

    try:
        # 秘密鍵を読み込む（PEM形式）
        print("📄 秘密鍵を読み込んでいます: /app/private_key.pem")
        with open('/app/private_key.pem', 'rb') as f:
            private_key_pem = f.read()

        private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
            backend=default_backend()
        )

        # 秘密鍵をDER形式に変換してBase64エンコード
        private_key_der = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        private_key_b64 = base64.urlsafe_b64encode(private_key_der).decode('utf-8').rstrip('=')

        print(f"✅ 秘密鍵の読み込み完了\n")

        # 公開鍵を読み込む（PEM形式）
        print("📄 公開鍵を読み込んでいます: /app/public_key.pem")
        with open('/app/public_key.pem', 'rb') as f:
            public_key_pem = f.read()

        public_key = serialization.load_pem_public_key(
            public_key_pem,
            backend=default_backend()
        )

        # 公開鍵をUncompressedPoint形式に変換してBase64URLエンコード
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        public_key_b64 = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')

        print(f"✅ 公開鍵の読み込み完了\n")

        # 結果を表示
        print("=" * 70)
        print("📋 .envファイルに以下の環境変数を追加してください:")
        print("=" * 70 + "\n")

        print(f"VAPID_PRIVATE_KEY={private_key_b64}")
        print(f"VAPID_PUBLIC_KEY={public_key_b64}")
        print(f"VAPID_SUBJECT=mailto:support@keikakun.com")

        print("\n" + "=" * 70)
        print("⚠️  重要: フロントエンドの.env.localも確認してください")
        print("=" * 70 + "\n")

        print(f"NEXT_PUBLIC_VAPID_PUBLIC_KEY={public_key_b64}")

        print("\n" + "=" * 70)
        print("✅ 環境変数の生成が完了しました")
        print("=" * 70 + "\n")

        print("📝 次のステップ:")
        print("   1. 上記の環境変数を k_back/.env に追加")
        print("   2. Docker コンテナを再起動:")
        print("      docker-compose restart backend")
        print("   3. フロントエンドの.env.localの公開鍵が一致していることを確認")
        print("   4. ブラウザでサイトデータをクリア")
        print("   5. 再度システム通知をONにする")
        print("")

    except FileNotFoundError as e:
        print(f"❌ エラー: PEMファイルが見つかりません: {e}")
        print("\n💡 VAPID鍵ペアを生成してください:")
        print("   docker exec keikakun_app-backend-1 python3 scripts/generate_vapid_keys.py")
        sys.exit(1)

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    generate_vapid_env_variables()
