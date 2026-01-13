"""
日本の祝日判定ユーティリティ
"""
import jpholiday
from datetime import date


def is_japanese_holiday(target_date: date) -> bool:
    """
    指定された日付が日本の祝日かどうかを判定

    Args:
        target_date: 判定対象の日付

    Returns:
        bool: 祝日の場合True、祝日でない場合False

    Examples:
        >>> is_japanese_holiday(date(2026, 1, 1))  # 元日
        True
        >>> is_japanese_holiday(date(2026, 1, 2))  # 平日
        False
    """
    return jpholiday.is_holiday(target_date)


def is_japanese_weekday_and_not_holiday(target_date: date) -> bool:
    """
    指定された日付が平日かつ祝日でないことを判定

    Args:
        target_date: 判定対象の日付

    Returns:
        bool: 平日かつ祝日でない場合True、それ以外False

    Examples:
        >>> is_japanese_weekday_and_not_holiday(date(2026, 1, 5))  # 月曜日
        True
        >>> is_japanese_weekday_and_not_holiday(date(2026, 1, 10))  # 土曜日
        False
        >>> is_japanese_weekday_and_not_holiday(date(2026, 1, 1))  # 元日（木曜日）
        False
    """
    # 土曜日=5, 日曜日=6
    is_weekend = target_date.weekday() >= 5
    is_holiday = is_japanese_holiday(target_date)

    return not is_weekend and not is_holiday


def get_holiday_name(target_date: date) -> str | None:
    """
    指定された日付の祝日名を取得

    Args:
        target_date: 判定対象の日付

    Returns:
        str | None: 祝日名（祝日でない場合はNone）

    Examples:
        >>> get_holiday_name(date(2026, 1, 1))
        '元日'
        >>> get_holiday_name(date(2026, 1, 2))
        None
    """
    return jpholiday.is_holiday_name(target_date)
