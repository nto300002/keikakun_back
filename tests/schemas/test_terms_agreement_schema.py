import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
import uuid

from app.schemas.terms_agreement import (
    TermsAgreementBase,
    TermsAgreementCreate,
    TermsAgreementUpdate,
    TermsAgreementRead,
    AgreeToTermsRequest,
    AgreeToTermsResponse
)


class TestTermsAgreementBase:
    """TermsAgreementBaseスキーマのテスト"""

    def test_base_valid(self):
        """正常なデータでTermsAgreementBaseモデルが作成できることをテスト"""
        valid_data = {
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
        base = TermsAgreementBase(**valid_data)
        assert base.terms_version == "1.0"
        assert base.privacy_version == "1.0"

    def test_base_optional_fields(self):
        """バージョンフィールドがオプショナルであることをテスト"""
        empty_data = {}
        base = TermsAgreementBase(**empty_data)
        assert base.terms_version is None
        assert base.privacy_version is None

    def test_base_none_values(self):
        """Noneが明示的に設定できることをテスト"""
        none_data = {
            "terms_version": None,
            "privacy_version": None
        }
        base = TermsAgreementBase(**none_data)
        assert base.terms_version is None
        assert base.privacy_version is None


class TestTermsAgreementCreate:
    """TermsAgreementCreateスキーマのテスト"""

    def test_create_valid_with_all_fields(self):
        """すべてのフィールドを含む正常なデータでモデルが作成できることをテスト"""
        staff_id = uuid.uuid4()
        valid_data = {
            "staff_id": staff_id,
            "terms_version": "1.0",
            "privacy_version": "1.0",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        create = TermsAgreementCreate(**valid_data)
        assert create.staff_id == staff_id
        assert create.terms_version == "1.0"
        assert create.privacy_version == "1.0"
        assert create.ip_address == "192.168.1.1"
        assert create.user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    def test_create_valid_minimal(self):
        """最小限の必須フィールドでモデルが作成できることをテスト"""
        staff_id = uuid.uuid4()
        minimal_data = {
            "staff_id": staff_id
        }
        create = TermsAgreementCreate(**minimal_data)
        assert create.staff_id == staff_id
        assert create.terms_version is None
        assert create.privacy_version is None
        assert create.ip_address is None
        assert create.user_agent is None

    def test_create_missing_staff_id(self):
        """staff_idが欠落している場合にValidationErrorが発生することをテスト"""
        invalid_data = {
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
        with pytest.raises(ValidationError) as exc_info:
            TermsAgreementCreate(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("staff_id",) for error in errors)

    def test_create_invalid_staff_id_type(self):
        """staff_idが不正な型の場合にValidationErrorが発生することをテスト"""
        invalid_data = {
            "staff_id": "not-a-uuid",
            "terms_version": "1.0"
        }
        with pytest.raises(ValidationError) as exc_info:
            TermsAgreementCreate(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("staff_id",) for error in errors)

    def test_create_with_ipv4_address(self):
        """IPv4アドレスが正しく設定できることをテスト"""
        valid_data = {
            "staff_id": uuid.uuid4(),
            "ip_address": "192.168.0.1"
        }
        create = TermsAgreementCreate(**valid_data)
        assert create.ip_address == "192.168.0.1"

    def test_create_with_ipv6_address(self):
        """IPv6アドレスが正しく設定できることをテスト"""
        valid_data = {
            "staff_id": uuid.uuid4(),
            "ip_address": "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        }
        create = TermsAgreementCreate(**valid_data)
        assert create.ip_address == "2001:0db8:85a3:0000:0000:8a2e:0370:7334"

    def test_create_with_long_user_agent(self):
        """長いユーザーエージェント文字列が設定できることをテスト"""
        long_ua = "Mozilla/5.0 " + "a" * 400
        valid_data = {
            "staff_id": uuid.uuid4(),
            "user_agent": long_ua
        }
        create = TermsAgreementCreate(**valid_data)
        assert create.user_agent == long_ua


class TestTermsAgreementUpdate:
    """TermsAgreementUpdateスキーマのテスト"""

    def test_update_all_fields(self):
        """すべてのフィールドを更新するモデルが作成できることをテスト"""
        now = datetime.now(timezone.utc)
        update_data = {
            "terms_of_service_agreed_at": now,
            "privacy_policy_agreed_at": now,
            "terms_version": "1.1",
            "privacy_version": "1.1",
            "ip_address": "10.0.0.1",
            "user_agent": "Updated User Agent"
        }
        update = TermsAgreementUpdate(**update_data)
        assert update.terms_of_service_agreed_at == now
        assert update.privacy_policy_agreed_at == now
        assert update.terms_version == "1.1"
        assert update.privacy_version == "1.1"
        assert update.ip_address == "10.0.0.1"
        assert update.user_agent == "Updated User Agent"

    def test_update_partial(self):
        """部分的な更新データでモデルが作成できることをテスト"""
        now = datetime.now(timezone.utc)
        update_data = {
            "terms_of_service_agreed_at": now,
            "terms_version": "2.0"
        }
        update = TermsAgreementUpdate(**update_data)
        assert update.terms_of_service_agreed_at == now
        assert update.terms_version == "2.0"
        assert update.privacy_policy_agreed_at is None
        assert update.privacy_version is None

    def test_update_empty(self):
        """空の更新データでモデルが作成できることをテスト"""
        update_data = {}
        update = TermsAgreementUpdate(**update_data)
        assert update.terms_of_service_agreed_at is None
        assert update.privacy_policy_agreed_at is None
        assert update.terms_version is None
        assert update.privacy_version is None
        assert update.ip_address is None
        assert update.user_agent is None

    def test_update_only_terms(self):
        """利用規約のみ更新するケースをテスト"""
        now = datetime.now(timezone.utc)
        update_data = {
            "terms_of_service_agreed_at": now,
            "terms_version": "2.0"
        }
        update = TermsAgreementUpdate(**update_data)
        assert update.terms_of_service_agreed_at == now
        assert update.terms_version == "2.0"
        assert update.privacy_policy_agreed_at is None

    def test_update_only_privacy(self):
        """プライバシーポリシーのみ更新するケースをテスト"""
        now = datetime.now(timezone.utc)
        update_data = {
            "privacy_policy_agreed_at": now,
            "privacy_version": "2.0"
        }
        update = TermsAgreementUpdate(**update_data)
        assert update.privacy_policy_agreed_at == now
        assert update.privacy_version == "2.0"
        assert update.terms_of_service_agreed_at is None


class TestTermsAgreementRead:
    """TermsAgreementReadスキーマのテスト"""

    def test_read_valid_with_all_fields(self):
        """すべてのフィールドを含む正常なデータでモデルが作成できることをテスト"""
        agreement_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        read_data = {
            "id": agreement_id,
            "staff_id": staff_id,
            "terms_of_service_agreed_at": now,
            "privacy_policy_agreed_at": now,
            "terms_version": "1.0",
            "privacy_version": "1.0",
            "created_at": now,
            "updated_at": now
        }
        read = TermsAgreementRead(**read_data)
        assert read.id == agreement_id
        assert read.staff_id == staff_id
        assert read.terms_of_service_agreed_at == now
        assert read.privacy_policy_agreed_at == now
        assert read.terms_version == "1.0"
        assert read.privacy_version == "1.0"
        assert read.created_at == now
        assert read.updated_at == now

    def test_read_with_none_agreed_at(self):
        """同意日時がNoneの場合でもモデルが作成できることをテスト"""
        agreement_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        read_data = {
            "id": agreement_id,
            "staff_id": staff_id,
            "terms_of_service_agreed_at": None,
            "privacy_policy_agreed_at": None,
            "terms_version": None,
            "privacy_version": None,
            "created_at": now,
            "updated_at": now
        }
        read = TermsAgreementRead(**read_data)
        assert read.terms_of_service_agreed_at is None
        assert read.privacy_policy_agreed_at is None
        assert read.terms_version is None
        assert read.privacy_version is None

    def test_read_missing_required_id(self):
        """idが欠落している場合にValidationErrorが発生することをテスト"""
        staff_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        invalid_data = {
            # idが欠落
            "staff_id": staff_id,
            "created_at": now,
            "updated_at": now
        }
        with pytest.raises(ValidationError) as exc_info:
            TermsAgreementRead(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("id",) for error in errors)

    def test_read_missing_required_staff_id(self):
        """staff_idが欠落している場合にValidationErrorが発生することをテスト"""
        agreement_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        invalid_data = {
            "id": agreement_id,
            # staff_idが欠落
            "created_at": now,
            "updated_at": now
        }
        with pytest.raises(ValidationError) as exc_info:
            TermsAgreementRead(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("staff_id",) for error in errors)

    def test_read_from_attributes(self):
        """from_attributes=Trueが設定されていることをテスト"""
        assert TermsAgreementRead.model_config.get("from_attributes") is True


class TestAgreeToTermsRequest:
    """AgreeToTermsRequestスキーマのテスト"""

    def test_request_valid_all_agreed(self):
        """両方に同意する正常なリクエストが作成できることをテスト"""
        request_data = {
            "agree_to_terms": True,
            "agree_to_privacy": True,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
        request = AgreeToTermsRequest(**request_data)
        assert request.agree_to_terms is True
        assert request.agree_to_privacy is True
        assert request.terms_version == "1.0"
        assert request.privacy_version == "1.0"

    def test_request_default_versions(self):
        """バージョンのデフォルト値が設定されることをテスト"""
        request_data = {
            "agree_to_terms": True,
            "agree_to_privacy": True
        }
        request = AgreeToTermsRequest(**request_data)
        assert request.terms_version == "1.0"
        assert request.privacy_version == "1.0"

    def test_request_not_agreed(self):
        """同意しない場合でもモデルが作成できることをテスト"""
        request_data = {
            "agree_to_terms": False,
            "agree_to_privacy": False
        }
        request = AgreeToTermsRequest(**request_data)
        assert request.agree_to_terms is False
        assert request.agree_to_privacy is False

    def test_request_partial_agreement(self):
        """片方のみ同意する場合でもモデルが作成できることをテスト"""
        request_data = {
            "agree_to_terms": True,
            "agree_to_privacy": False
        }
        request = AgreeToTermsRequest(**request_data)
        assert request.agree_to_terms is True
        assert request.agree_to_privacy is False

    def test_request_missing_required_fields(self):
        """必須フィールドが欠落している場合にValidationErrorが発生することをテスト"""
        invalid_data = {
            "agree_to_terms": True
            # agree_to_privacyが欠落
        }
        with pytest.raises(ValidationError) as exc_info:
            AgreeToTermsRequest(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("agree_to_privacy",) for error in errors)

    def test_request_custom_versions(self):
        """カスタムバージョンが設定できることをテスト"""
        request_data = {
            "agree_to_terms": True,
            "agree_to_privacy": True,
            "terms_version": "2.5",
            "privacy_version": "3.0"
        }
        request = AgreeToTermsRequest(**request_data)
        assert request.terms_version == "2.5"
        assert request.privacy_version == "3.0"


class TestAgreeToTermsResponse:
    """AgreeToTermsResponseスキーマのテスト"""

    def test_response_valid(self):
        """正常なレスポンスモデルが作成できることをテスト"""
        now = datetime.now(timezone.utc)
        response_data = {
            "message": "利用規約とプライバシーポリシーへの同意が記録されました",
            "agreed_at": now,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
        response = AgreeToTermsResponse(**response_data)
        assert response.message == "利用規約とプライバシーポリシーへの同意が記録されました"
        assert response.agreed_at == now
        assert response.terms_version == "1.0"
        assert response.privacy_version == "1.0"

    def test_response_missing_message(self):
        """messageが欠落している場合にValidationErrorが発生することをテスト"""
        now = datetime.now(timezone.utc)
        invalid_data = {
            # messageが欠落
            "agreed_at": now,
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
        with pytest.raises(ValidationError) as exc_info:
            AgreeToTermsResponse(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("message",) for error in errors)

    def test_response_missing_agreed_at(self):
        """agreed_atが欠落している場合にValidationErrorが発生することをテスト"""
        invalid_data = {
            "message": "同意が記録されました",
            # agreed_atが欠落
            "terms_version": "1.0",
            "privacy_version": "1.0"
        }
        with pytest.raises(ValidationError) as exc_info:
            AgreeToTermsResponse(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("agreed_at",) for error in errors)

    def test_response_missing_versions(self):
        """バージョンフィールドが欠落している場合にValidationErrorが発生することをテスト"""
        now = datetime.now(timezone.utc)
        invalid_data = {
            "message": "同意が記録されました",
            "agreed_at": now
            # terms_versionとprivacy_versionが欠落
        }
        with pytest.raises(ValidationError) as exc_info:
            AgreeToTermsResponse(**invalid_data)
        errors = exc_info.value.errors()
        assert any(
            error["loc"] == ("terms_version",) or error["loc"] == ("privacy_version",)
            for error in errors
        )

    def test_response_custom_message(self):
        """カスタムメッセージが設定できることをテスト"""
        now = datetime.now(timezone.utc)
        response_data = {
            "message": "規約への同意を確認しました",
            "agreed_at": now,
            "terms_version": "2.0",
            "privacy_version": "2.0"
        }
        response = AgreeToTermsResponse(**response_data)
        assert response.message == "規約への同意を確認しました"
