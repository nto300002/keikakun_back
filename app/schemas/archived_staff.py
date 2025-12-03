"""
アーカイブスタッフのスキーマ定義
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ArchivedStaffBase(BaseModel):
    """アーカイブスタッフの基本スキーマ"""
    original_staff_id: UUID = Field(..., description="元のスタッフID")
    anonymized_full_name: str = Field(..., description="匿名化された氏名")
    anonymized_email: str = Field(..., description="匿名化されたメールアドレス")
    role: str = Field(..., description="役職（owner/manager/employee）")
    office_id: Optional[UUID] = Field(None, description="所属していた事務所ID")
    office_name: Optional[str] = Field(None, description="事務所名")
    hired_at: datetime = Field(..., description="雇入れ日")
    terminated_at: datetime = Field(..., description="退職日")
    archive_reason: str = Field(..., description="アーカイブ理由")
    legal_retention_until: datetime = Field(..., description="法定保存期限")


class ArchivedStaffRead(ArchivedStaffBase):
    """アーカイブスタッフ読み取り用スキーマ（詳細）"""
    id: UUID = Field(..., description="アーカイブID")
    archived_at: datetime = Field(..., description="アーカイブ作成日時")
    metadata_: Optional[dict] = Field(None, description="メタデータ", alias="metadata_")
    is_test_data: bool = Field(..., description="テストデータフラグ")
    created_at: datetime = Field(..., description="レコード作成日時")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ArchivedStaffListItem(BaseModel):
    """アーカイブスタッフリスト項目スキーマ（一覧表示用）"""
    id: UUID = Field(..., description="アーカイブID")
    anonymized_full_name: str = Field(..., description="匿名化された氏名")
    anonymized_email: str = Field(..., description="匿名化されたメールアドレス")
    role: str = Field(..., description="役職")
    office_id: Optional[UUID] = Field(None, description="所属していた事務所ID")
    office_name: Optional[str] = Field(None, description="事務所名")
    terminated_at: datetime = Field(..., description="退職日")
    archive_reason: str = Field(..., description="アーカイブ理由")
    legal_retention_until: datetime = Field(..., description="法定保存期限")
    archived_at: datetime = Field(..., description="アーカイブ作成日時")

    model_config = ConfigDict(from_attributes=True)


class ArchivedStaffListResponse(BaseModel):
    """アーカイブスタッフリストレスポンス"""
    items: List[ArchivedStaffListItem] = Field(..., description="アーカイブリスト")
    total: int = Field(..., description="総件数")
    skip: int = Field(..., description="スキップ件数")
    limit: int = Field(..., description="取得件数")
