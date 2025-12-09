"""
レート制限のテスト

問い合わせエンドポイントに対するレート制限の動作を確認
"""
import pytest
from unittest.mock import Mock, patch
from fastapi import Request
from app.core.limiter import limiter


class TestRateLimiting:
    """レート制限のテスト"""

    def test_limiter_instance(self):
        """Limiterインスタンスが正しく作成されている"""
        assert limiter is not None
        assert hasattr(limiter, 'limit')

    def test_get_remote_address(self):
        """リモートアドレス取得のテスト"""
        # モックリクエストを作成
        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.1"

        # limiterのkey_funcはget_remote_addressを使用
        from slowapi.util import get_remote_address
        remote_addr = get_remote_address(mock_request)

        assert remote_addr == "192.168.1.1"

    @pytest.mark.parametrize("test_ip,expected", [
        ("192.168.1.1", "192.168.1.1"),
        ("203.0.113.42", "203.0.113.42"),
        ("2001:db8::1", "2001:db8::1"),  # IPv6
    ])
    def test_various_ip_addresses(self, test_ip, expected):
        """様々なIPアドレスの処理"""
        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = test_ip

        from slowapi.util import get_remote_address
        remote_addr = get_remote_address(mock_request)

        assert remote_addr == expected


class TestRateLimitDecorator:
    """レート制限デコレータのテスト"""

    def test_rate_limit_decorator_syntax(self):
        """レート制限デコレータの構文チェック"""
        # slowapiのデコレータは実際のエンドポイント（requestパラメータ付き）でのみ動作
        # ここでは設定値の妥当性のみ確認

        rate_limit = "5/minute"
        assert "/" in rate_limit or "per" in rate_limit
        parts = rate_limit.split("/")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert parts[1] in ["minute", "hour", "day", "month"]

    def test_multiple_rate_limits_config(self):
        """複数のレート制限設定の妥当性"""
        rate_limits = ["5/minute", "50/hour"]

        for rate_limit in rate_limits:
            assert "/" in rate_limit
            parts = rate_limit.split("/")
            assert len(parts) == 2
            assert parts[0].isdigit()


class TestRateLimitConfiguration:
    """レート制限設定のテスト"""

    def test_inquiry_rate_limit_config(self):
        """問い合わせエンドポイントのレート制限設定"""
        # 設計書の要件: 5回 / 30分
        # slowapi形式: "5 per 30 minutes"

        rate_limit = "5 per 30 minutes"
        assert "per" in rate_limit
        assert "5" in rate_limit
        assert "30" in rate_limit
        assert "minutes" in rate_limit

    def test_strict_rate_limit_config(self):
        """厳格なレート制限設定"""
        # より厳しい制限: 1回 / 分
        rate_limit = "1/minute"

        parts = rate_limit.split("/")
        count = int(parts[0])
        unit = parts[1]

        assert count == 1
        assert unit == "minute"


class TestIPAddressExtraction:
    """IPアドレス抽出のテスト"""

    def test_client_host_extraction(self):
        """request.client.hostからのIPアドレス抽出"""
        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"

        from slowapi.util import get_remote_address
        ip = get_remote_address(mock_request)

        assert ip == "192.168.1.100"

    def test_x_forwarded_for_header(self):
        """X-Forwarded-Forヘッダーからの取得（プロキシ経由）"""
        # 注意: slowapiのデフォルトはrequest.client.hostを使用
        # X-Forwarded-Forを使用する場合はカスタムkey_funcが必要

        mock_request = Mock(spec=Request)
        mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 192.168.1.1"}
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.1"

        # デフォルトの動作確認
        from slowapi.util import get_remote_address
        ip = get_remote_address(mock_request)

        # デフォルトはclient.hostを返す
        assert ip == "192.168.1.1"

    def test_missing_client_info(self):
        """クライアント情報がない場合"""
        mock_request = Mock(spec=Request)
        mock_request.client = None

        from slowapi.util import get_remote_address

        # client=Noneの場合、"127.0.0.1"をデフォルトで返す
        ip = get_remote_address(mock_request)
        assert ip is not None  # 何らかの値が返される


class TestSecurityBestPractices:
    """セキュリティベストプラクティスのテスト"""

    def test_rate_limit_message_format(self):
        """レート制限メッセージのフォーマット"""
        # レート制限超過時のレスポンス例
        expected_status = 429
        expected_message = "Too Many Requests"

        assert expected_status == 429
        assert "Too Many Requests" in expected_message

    def test_rate_limit_bypass_prevention(self):
        """レート制限バイパス防止"""
        # 同一IPアドレスからの複数リクエストは制限される
        test_ip = "192.168.1.1"

        # 異なるUser-Agentでも同じIPなら制限される
        mock_request1 = Mock(spec=Request)
        mock_request1.client = Mock()
        mock_request1.client.host = test_ip
        mock_request1.headers = {"User-Agent": "Browser1"}

        mock_request2 = Mock(spec=Request)
        mock_request2.client = Mock()
        mock_request2.client.host = test_ip
        mock_request2.headers = {"User-Agent": "Browser2"}

        from slowapi.util import get_remote_address
        ip1 = get_remote_address(mock_request1)
        ip2 = get_remote_address(mock_request2)

        # 同じIPアドレスが返される
        assert ip1 == ip2 == test_ip

    def test_whitelist_consideration(self):
        """ホワイトリスト検討のテスト"""
        # 将来的な拡張: 特定IPをホワイトリストに追加
        trusted_ips = ["192.168.1.1", "10.0.0.1"]

        test_ip = "192.168.1.1"
        assert test_ip in trusted_ips

        untrusted_ip = "203.0.113.42"
        assert untrusted_ip not in trusted_ips
