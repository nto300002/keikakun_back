import pytest
from pydantic import ValidationError
from datetime import date, timedelta

from app.schemas.welfare_recipient import WelfareRecipientCreate, WelfareRecipientUpdate
from app.models.enums import GenderType


def test_welfare_recipient_create_valid():
    """正常なデータでWelfareRecipientCreateモデルが作成できることをテスト"""
    today = date.today()
    valid_data = {
        "first_name": "太郎",
        "last_name": "山田",
        "first_name_furigana": "たろう",
        "last_name_furigana": "やまだ",
        "birth_day": today,
        "gender": GenderType.male,
    }
    recipient = WelfareRecipientCreate(**valid_data)
    assert recipient.first_name == valid_data["first_name"]
    assert recipient.birth_day == valid_data["birth_day"]


def test_welfare_recipient_create_future_birth_day_raises_error():
    """未来の誕生日でWelfareRecipientCreateモデルを作成するとValidationErrorが発生することをテスト"""
    tomorrow = date.today() + timedelta(days=1)
    invalid_data = {
        "first_name": "未来",
        "last_name": "太郎",
        "first_name_furigana": "みらい",
        "last_name_furigana": "たろう",
        "birth_day": tomorrow,
        "gender": GenderType.male,
    }
    with pytest.raises(ValidationError) as exc_info:
        WelfareRecipientCreate(**invalid_data)
    assert "Birth date cannot be in the future" in str(exc_info.value)


def test_welfare_recipient_update_valid():
    """正常なデータでWelfareRecipientUpdateモデルが作成できることをテスト"""
    update_data = {
        "first_name": "更新太郎",
        "birth_day": date(2000, 1, 1),
    }
    recipient_update = WelfareRecipientUpdate(**update_data)
    assert recipient_update.first_name == "更新太郎"
    assert recipient_update.birth_day == date(2000, 1, 1)


def test_welfare_recipient_update_future_birth_day_raises_error():
    """未来の誕生日でWelfareRecipientUpdateモデルを更新するとValidationErrorが発生することをテスト"""
    tomorrow = date.today() + timedelta(days=1)
    invalid_update_data = {
        "birth_day": tomorrow,
    }
    with pytest.raises(ValidationError) as exc_info:
        WelfareRecipientUpdate(**invalid_update_data)
    assert "Birth date cannot be in the future" in str(exc_info.value)


def test_welfare_recipient_update_birth_day_none():
    """誕生日をNoneで更新できることをテスト"""
    update_data = {"birth_day": None}
    recipient_update = WelfareRecipientUpdate(**update_data)
    assert recipient_update.birth_day is None
