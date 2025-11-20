"""
パスワード侵害チェック（HIBP API連携）のユニットテスト

k-Anonymity方式を使用したHave I Been Pwned APIとの連携機能をテストします。
"""

import pytest
import hashlib
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from app.core.password_breach_check import check_password_breach


class TestPasswordBreachCheck:
    """パスワード侵害チェックのユニットテスト"""

    @pytest.mark.asyncio
    async def test_breached_password_detected(self):
        """侵害されたパスワードが検出されること"""
        # 有名な侵害されたパスワード: "password"
        # SHA-1: 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
        password = "password"
        sha1_hash = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
        hash_prefix = sha1_hash[:5]  # "5BAA6"
        hash_suffix = sha1_hash[5:]  # "1E4C9B93F3F0682250B6CF8331B7EE68FD8"

        # HIBP APIのレスポンスをモック
        mock_response = MagicMock()
        mock_response.status_code = 200
        # APIは "suffix:count" の形式で返す
        mock_response.text = f"{hash_suffix}:3861493\nOTHERHASH:100\nANOTHERHASH:50"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            is_breached, count = await check_password_breach(password)

            assert is_breached is True
            assert count == 3861493
            # APIへの正しいリクエストを確認
            mock_instance.get.assert_called_once()
            call_args = mock_instance.get.call_args
            assert f"/range/{hash_prefix}" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_safe_password_not_breached(self):
        """侵害されていないパスワードが検出されないこと"""
        password = "V3ry$tr0ng&Unique!P@ssw0rd123"
        sha1_hash = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
        hash_prefix = sha1_hash[:5]
        hash_suffix = sha1_hash[5:]

        # HIBP APIのレスポンスをモック（該当するハッシュが含まれていない）
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "DIFFERENTHASH1:100\nDIFFERENTHASH2:50\nDIFFERENTHASH3:25"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            is_breached, count = await check_password_breach(password)

            assert is_breached is False
            assert count is None

    @pytest.mark.asyncio
    async def test_api_timeout_fail_safe(self):
        """APIタイムアウト時にフェイルセーフで許可すること"""
        password = "TestP@ssw0rd123"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            # タイムアウト例外を発生させる
            mock_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            is_breached, count = await check_password_breach(password)

            # フェイルセーフ: タイムアウト時は許可
            assert is_breached is False
            assert count is None

    @pytest.mark.asyncio
    async def test_api_error_fail_safe(self):
        """API接続エラー時にフェイルセーフで許可すること"""
        password = "TestP@ssw0rd123"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            # 一般的な例外を発生させる
            mock_instance.get = AsyncMock(side_effect=Exception("Network error"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            is_breached, count = await check_password_breach(password)

            # フェイルセーフ: エラー時は許可
            assert is_breached is False
            assert count is None

    @pytest.mark.asyncio
    async def test_api_non_200_status_fail_safe(self):
        """API非200ステータス時にフェイルセーフで許可すること"""
        password = "TestP@ssw0rd123"

        mock_response = MagicMock()
        mock_response.status_code = 503  # Service Unavailable

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            is_breached, count = await check_password_breach(password)

            # フェイルセーフ: API障害時は許可
            assert is_breached is False
            assert count is None

    @pytest.mark.asyncio
    async def test_k_anonymity_only_sends_prefix(self):
        """k-Anonymity方式で最初の5文字のみ送信すること"""
        password = "TestP@ssw0rd123"
        sha1_hash = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
        hash_prefix = sha1_hash[:5]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SOMEHASH:100"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            await check_password_breach(password)

            # API呼び出しの引数を確認
            call_args = mock_instance.get.call_args
            url = call_args[0][0]

            # URLに最初の5文字のみが含まれている
            assert f"/range/{hash_prefix}" in url
            # 完全なハッシュは含まれていない
            assert sha1_hash not in url

    @pytest.mark.asyncio
    async def test_api_headers_include_padding(self):
        """APIリクエストにAdd-Paddingヘッダーが含まれること"""
        password = "TestP@ssw0rd123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SOMEHASH:100"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            await check_password_breach(password)

            # ヘッダーを確認
            call_args = mock_instance.get.call_args
            headers = call_args[1]['headers']

            assert 'Add-Padding' in headers
            assert headers['Add-Padding'] == 'true'
            assert 'User-Agent' in headers

    @pytest.mark.asyncio
    async def test_malformed_api_response_handled(self):
        """不正な形式のAPIレスポンスが適切に処理されること"""
        password = "TestP@ssw0rd123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        # 不正な形式（コロンがない）
        mock_response.text = "INVALIDFORMAT\nANOTHERINVALID"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            is_breached, count = await check_password_breach(password)

            # 不正な形式は無視され、侵害なしとして扱われる
            assert is_breached is False
            assert count is None

    @pytest.mark.asyncio
    async def test_custom_timeout_parameter(self):
        """カスタムタイムアウトパラメータが適用されること"""
        password = "TestP@ssw0rd123"
        custom_timeout = 10

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SOMEHASH:100"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            await check_password_breach(password, timeout=custom_timeout)

            # タイムアウト値を確認
            call_args = mock_instance.get.call_args
            assert call_args[1]['timeout'] == custom_timeout
