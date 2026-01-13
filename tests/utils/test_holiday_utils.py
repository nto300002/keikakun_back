"""
祝日判定ユーティリティのテスト
"""
import pytest
from datetime import date

from app.utils.holiday_utils import (
    is_japanese_holiday,
    is_japanese_weekday_and_not_holiday,
    get_holiday_name
)


class TestHolidayUtils:
    """祝日判定ユーティリティのテスト"""

    def test_is_japanese_holiday_new_year(self):
        """元日は祝日として判定される"""
        assert is_japanese_holiday(date(2026, 1, 1)) is True

    def test_is_japanese_holiday_regular_day(self):
        """平日は祝日でないと判定される"""
        assert is_japanese_holiday(date(2026, 1, 2)) is False

    def test_is_japanese_holiday_coming_of_age_day(self):
        """成人の日は祝日として判定される"""
        # 2026年の成人の日は1月12日（第2月曜日）
        assert is_japanese_holiday(date(2026, 1, 12)) is True

    def test_is_japanese_weekday_and_not_holiday_monday(self):
        """通常の月曜日は平日かつ祝日でないと判定される"""
        # 2026年1月5日（月曜日）
        assert is_japanese_weekday_and_not_holiday(date(2026, 1, 5)) is True

    def test_is_japanese_weekday_and_not_holiday_saturday(self):
        """土曜日は平日でないと判定される"""
        # 2026年1月10日（土曜日）
        assert is_japanese_weekday_and_not_holiday(date(2026, 1, 10)) is False

    def test_is_japanese_weekday_and_not_holiday_sunday(self):
        """日曜日は平日でないと判定される"""
        # 2026年1月11日（日曜日）
        assert is_japanese_weekday_and_not_holiday(date(2026, 1, 11)) is False

    def test_is_japanese_weekday_and_not_holiday_holiday(self):
        """祝日（平日）は平日かつ祝日でないの判定でFalse"""
        # 2026年1月1日（元日、木曜日）
        assert is_japanese_weekday_and_not_holiday(date(2026, 1, 1)) is False

    def test_get_holiday_name_new_year(self):
        """元日の祝日名を取得できる"""
        assert get_holiday_name(date(2026, 1, 1)) == "元日"

    def test_get_holiday_name_regular_day(self):
        """平日は祝日名がNone"""
        assert get_holiday_name(date(2026, 1, 2)) is None
