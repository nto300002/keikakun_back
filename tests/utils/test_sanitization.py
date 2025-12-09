"""
サニタイズユーティリティのテスト
"""
import pytest
from app.utils.sanitization import (
    sanitize_html,
    sanitize_text_content,
    sanitize_email,
    contains_spam_patterns,
    validate_honeypot,
    sanitize_inquiry_input
)


class TestSanitizeHTML:
    """HTMLサニタイズのテスト"""

    def test_sanitize_script_tag(self):
        """スクリプトタグのエスケープ"""
        input_text = "<script>alert('XSS')</script>"
        result = sanitize_html(input_text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_sanitize_normal_text(self):
        """通常のテキストはそのまま"""
        input_text = "Normal text"
        result = sanitize_html(input_text)
        assert result == "Normal text"

    def test_sanitize_none(self):
        """Noneはそのまま返す"""
        result = sanitize_html(None)
        assert result is None

    def test_sanitize_mixed_content(self):
        """HTMLと通常テキストの混在"""
        input_text = "Hello <b>World</b>!"
        result = sanitize_html(input_text)
        assert "&lt;b&gt;" in result
        assert "Hello" in result


class TestSanitizeTextContent:
    """テキストコンテンツサニタイズのテスト"""

    def test_remove_html_tags(self):
        """HTMLタグの除去"""
        input_text = "<p>Hello <span>World</span></p>"
        result = sanitize_text_content(input_text)
        assert result == "Hello World"

    def test_remove_control_characters(self):
        """制御文字の除去"""
        input_text = "Hello\x00World\x1F"
        result = sanitize_text_content(input_text)
        assert result == "HelloWorld"

    def test_preserve_newlines(self):
        """改行は保持"""
        input_text = "Hello\nWorld"
        result = sanitize_text_content(input_text)
        assert result == "Hello\nWorld"

    def test_collapse_spaces(self):
        """連続する空白を1つにまとめる"""
        input_text = "Hello    World"
        result = sanitize_text_content(input_text)
        assert result == "Hello World"

    def test_trim_whitespace(self):
        """前後の空白を削除"""
        input_text = "  Hello World  "
        result = sanitize_text_content(input_text)
        assert result == "Hello World"

    def test_max_length(self):
        """最大文字数制限"""
        input_text = "A" * 100
        result = sanitize_text_content(input_text, max_length=50)
        assert len(result) == 50

    def test_none_input(self):
        """Noneはそのまま返す"""
        result = sanitize_text_content(None)
        assert result is None


class TestSanitizeEmail:
    """メールアドレスサニタイズのテスト"""

    def test_valid_email(self):
        """正常なメールアドレス"""
        email = "test@example.com"
        result = sanitize_email(email)
        assert result == "test@example.com"

    def test_uppercase_to_lowercase(self):
        """大文字を小文字に変換"""
        email = "Test@Example.COM"
        result = sanitize_email(email)
        assert result == "test@example.com"

    def test_trim_whitespace(self):
        """前後の空白を削除"""
        email = "  test@example.com  "
        result = sanitize_email(email)
        assert result == "test@example.com"

    def test_invalid_email(self):
        """不正なメールアドレス"""
        with pytest.raises(ValueError):
            sanitize_email("invalid-email")

    def test_none_email(self):
        """Noneはそのまま返す"""
        result = sanitize_email(None)
        assert result is None


class TestContainsSpamPatterns:
    """スパムパターン検出のテスト"""

    def test_multiple_urls(self):
        """複数のURLを含む"""
        text = "Check out http://spam1.com and http://spam2.com and http://spam3.com"
        assert contains_spam_patterns(text) is True

    def test_excessive_uppercase(self):
        """過度な大文字使用"""
        text = "THIS IS A VERY IMPORTANT MESSAGE!!!"
        assert contains_spam_patterns(text) is True

    def test_spam_keywords_english(self):
        """スパムキーワード（英語）"""
        text = "Get free viagra now!"
        assert contains_spam_patterns(text) is True

    def test_spam_keywords_japanese(self):
        """スパムキーワード（日本語）"""
        text = "今すぐクリックして無料で当選！"
        assert contains_spam_patterns(text) is True

    def test_normal_text(self):
        """通常のテキスト"""
        text = "Hello, I have a question about your service."
        assert contains_spam_patterns(text) is False

    def test_empty_text(self):
        """空のテキスト"""
        assert contains_spam_patterns("") is False


class TestValidateHoneypot:
    """ハニーポット検証のテスト"""

    def test_empty_honeypot(self):
        """空のハニーポット（正常）"""
        assert validate_honeypot("") is True

    def test_none_honeypot(self):
        """Noneのハニーポット（正常）"""
        assert validate_honeypot(None) is True

    def test_filled_honeypot(self):
        """値が入っているハニーポット（ボット判定）"""
        assert validate_honeypot("bot-filled") is False


class TestSanitizeInquiryInput:
    """問い合わせ入力サニタイズのテスト"""

    def test_valid_inquiry(self):
        """正常な問い合わせ"""
        result = sanitize_inquiry_input(
            title="質問があります",
            content="サービスについて教えてください。",
            sender_name="山田太郎",
            sender_email="test@example.com",
            honeypot=""
        )
        assert result["title"] == "質問があります"
        assert result["content"] == "サービスについて教えてください。"
        assert result["sender_name"] == "山田太郎"
        assert result["sender_email"] == "test@example.com"

    def test_honeypot_filled(self):
        """ハニーポットが埋められている（ボット判定）"""
        with pytest.raises(ValueError, match="Invalid submission detected"):
            sanitize_inquiry_input(
                title="質問",
                content="内容",
                honeypot="bot-value"
            )

    def test_empty_title(self):
        """空の件名"""
        with pytest.raises(ValueError, match="Title is required"):
            sanitize_inquiry_input(
                title="",
                content="内容",
                honeypot=""
            )

    def test_empty_content(self):
        """空の内容"""
        with pytest.raises(ValueError, match="Content is required"):
            sanitize_inquiry_input(
                title="件名",
                content="",
                honeypot=""
            )

    def test_spam_detected(self):
        """スパム検出"""
        with pytest.raises(ValueError, match="Spam detected"):
            sanitize_inquiry_input(
                title="件名",
                content="今すぐクリックして無料で当選！http://spam1.com http://spam2.com http://spam3.com",
                honeypot=""
            )

    def test_title_too_long(self):
        """件名が長すぎる"""
        result = sanitize_inquiry_input(
            title="A" * 300,
            content="内容",
            honeypot=""
        )
        assert len(result["title"]) == 200

    def test_content_too_long(self):
        """内容が長すぎる"""
        result = sanitize_inquiry_input(
            title="件名",
            content="a" * 25000,  # 小文字にしてスパム判定を回避
            honeypot=""
        )
        assert len(result["content"]) == 20000

    def test_html_in_input(self):
        """HTMLタグを含む入力"""
        result = sanitize_inquiry_input(
            title="<script>alert('XSS')</script>件名",
            content="<b>太字</b>の内容",
            honeypot=""
        )
        assert "<script>" not in result["title"]
        assert "<b>" not in result["content"]

    def test_optional_fields_none(self):
        """任意項目がNone"""
        result = sanitize_inquiry_input(
            title="件名",
            content="内容",
            sender_name=None,
            sender_email=None,
            honeypot=""
        )
        assert result["sender_name"] is None
        assert result["sender_email"] is None

    def test_invalid_email(self):
        """不正なメールアドレス"""
        with pytest.raises(ValueError, match="Invalid email format"):
            sanitize_inquiry_input(
                title="件名",
                content="内容",
                sender_email="invalid-email",
                honeypot=""
            )
