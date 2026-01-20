"""
VAPID鍵ペア生成スクリプト

RFC 8292に準拠したP-256曲線のVAPID鍵ペアを生成します。
生成された鍵は環境変数に設定してください。
"""
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64


def generate_vapid_keys():
    """
    VAPID鍵ペアを生成

    Returns:
        tuple: (private_key_pem, private_key_der_base64, public_key_base64url)
    """
    # P-256曲線で秘密鍵を生成
    private_key = ec.generate_private_key(ec.SECP256R1())

    # 秘密鍵をPEM形式にシリアライズ（参考用）
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    # 秘密鍵をDER形式にシリアライズ（pywebpush用）
    private_key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # DER形式をBase64エンコード（pywebpushが要求する形式）
    private_key_der_base64 = base64.b64encode(private_key_der).decode('utf-8')

    # 公開鍵を取得
    public_key = private_key.public_key()

    # 公開鍵を非圧縮形式（X9.62）でシリアライズ
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    # Base64URL エンコード（パディングなし）
    public_key_base64url = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')

    return private_key_pem, private_key_der_base64, public_key_base64url


if __name__ == "__main__":
    print("=" * 80)
    print("VAPID鍵ペア生成 (RFC 8292準拠 - DER形式)")
    print("=" * 80)
    print()

    private_key_pem, private_key_der_base64, public_key_base64url = generate_vapid_keys()

    print("【.envファイル用 - コピー&ペーストしてください】")
    print()
    print(f'VAPID_PRIVATE_KEY_DER={private_key_der_base64}')
    print(f'VAPID_PUBLIC_KEY={public_key_base64url}')
    print()

    print("=" * 80)
    print()
    print("【確認用: PEM形式（参考のみ）】")
    print(private_key_pem)
    print()

    print("=" * 80)
    print()
    print("【フロントエンド用 - app/test/push-notification/page.tsx】")
    print()
    print(f'const VAPID_PUBLIC_KEY = "{public_key_base64url}";')
    print()

    print("=" * 80)
    print()
    print("【設定手順】")
    print("1. 上記の VAPID_PRIVATE_KEY_DER と VAPID_PUBLIC_KEY を")
    print("   .env ファイルにコピー&ペーストしてください")
    print()
    print("2. app/core/config.py を更新（次のステップで自動修正）")
    print()
    print("3. フロントエンドのVAPID_PUBLIC_KEY定数を更新:")
    print("   app/test/push-notification/page.tsx")
    print()
    print("4. Docker Composeを再起動:")
    print("   docker-compose down")
    print("   docker-compose up -d")
    print()
    print("=" * 80)
    print()
    print("重要: pywebpushはDER形式のBase64エンコードを要求します")
    print("      PEM形式ではなく、DER形式（バイナリ）を使用しています")
    print("=" * 80)
