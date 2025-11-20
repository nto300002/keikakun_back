"""
パスワード侵害チェック（Have I Been Pwned API連携）

k-Anonymity方式を使用して、パスワード全体をAPIに送信せずに
侵害されたパスワードかどうかをチェックします。

参考: https://haveibeenpwned.com/API/v3#PwnedPasswords
"""

import hashlib
import httpx
from typing import Optional
import logging

logger = logging.getLogger(__name__)


async def check_password_breach(password: str, timeout: int = 5) -> tuple[bool, Optional[int]]:
    """
    パスワードが侵害されたデータベースに存在するかチェック

    Args:
        password: チェックするパスワード
        timeout: APIリクエストのタイムアウト（秒）

    Returns:
        tuple[bool, Optional[int]]: (侵害されているか, 侵害回数)
        - (True, 回数): 侵害されている
        - (False, None): 侵害されていない
        - (False, None): API接続失敗時（安全側に倒す）

    Note:
        k-Anonymity方式:
        1. パスワードのSHA-1ハッシュを計算
        2. 最初の5文字のみをAPIに送信
        3. API側で該当する全てのハッシュを返す
        4. クライアント側で完全一致を確認

        例: password "P@ssw0rd" の場合
        SHA-1: 21BD12DC183F740EE76F27B78EB39C8AD972A757
        送信: 21BD1 (最初の5文字)
        受信: 2DC183F740EE76F27B78EB39C8AD972A757:3
              (残りの35文字:侵害回数のリスト)
    """
    try:
        # 1. SHA-1ハッシュを計算
        sha1_hash = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()

        # 2. 最初の5文字と残りに分割
        hash_prefix = sha1_hash[:5]
        hash_suffix = sha1_hash[5:]

        # 3. HIBP APIにリクエスト
        api_url = f"https://api.pwnedpasswords.com/range/{hash_prefix}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url,
                timeout=timeout,
                headers={
                    "User-Agent": "Keikakun-App-Password-Check",
                    "Add-Padding": "true"  # パディングでタイミング攻撃を防ぐ
                }
            )

            if response.status_code != 200:
                logger.warning(
                    f"HIBP API returned status {response.status_code}. "
                    "Allowing password (fail-safe)."
                )
                return False, None

        # 4. レスポンスから該当するハッシュを検索
        for line in response.text.splitlines():
            parts = line.split(':')
            if len(parts) != 2:
                continue

            response_suffix, count_str = parts

            if response_suffix.strip() == hash_suffix:
                # 侵害されたパスワードが見つかった
                breach_count = int(count_str.strip())
                logger.info(
                    f"Password found in breach database "
                    f"(count: {breach_count}, prefix: {hash_prefix})"
                )
                return True, breach_count

        # 5. 侵害されていない
        return False, None

    except httpx.TimeoutException:
        logger.warning("HIBP API timeout. Allowing password (fail-safe).")
        return False, None

    except Exception as e:
        logger.error(f"Error checking password breach: {str(e)}. Allowing password (fail-safe).")
        return False, None


async def check_password_breach_sync(password: str) -> tuple[bool, Optional[int]]:
    """
    同期版: パスワード侵害チェック（非推奨）

    Note:
        Pydantic validatorから呼び出す場合は同期関数が必要だが、
        非同期APIコールができないため、エンドポイント側でチェック推奨
    """
    import asyncio
    try:
        # イベントループを取得または作成
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 非同期関数を同期的に実行
        return loop.run_until_complete(check_password_breach(password))
    except Exception as e:
        logger.error(f"Error in sync password breach check: {str(e)}")
        return False, None
