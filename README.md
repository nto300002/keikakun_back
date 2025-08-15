# keikakun_back

---

## **アプリケーションバックエンド要件定義書: ケイカくん API**

### 1. システム概要とアーキテクチャ

#### 1.1. 目的
本バックエンドは、福祉サービス事業所向けWebアプリケーション「ケイカくん」のサーバーサイド機能を提供する。主な責務は、データ永続化、ビジネスロジックの実行、フロントエンドへのAPI提供、外部サービスとの連携である。

#### 1.2. 技術スタック
*   **フレームワーク**: FastAPI
*   **言語**: Python 3.13
*   **データベース**: Neon (PostgreSQL)
*   **ORM**: SQLAlchemy 2.0 (非同期モード)
*   **DBマイグレーション**: Alembic
*   **データ検証**: Pydantic V2
*   **コンテナ化**: Docker
*   **デプロイ先**: Google Cloud Run

#### 1.3. アーキテクチャ
厳格な**階層型アーキテクチャ（Layered Architecture）**を採用し、関心の分離を徹底する。

*   **API層 (`endpoints`)**: HTTPリクエストの受付とレスポンス返却に専念。認証・認可を処理し、リクエストを検証後、サービス層に処理を委譲する。
*   **サービス層 (`services`)**: ビジネスロジックの中核。複数のCRUD操作を組み合わせて単一のユースケースを実装し、トランザクションを管理する。
*   **CRUD層 (`crud`)**: データアクセス層。単一のDBモデルに対する基本的なCRUD操作のみを提供する。
*   **スキーマ層 (`schemas`)**: Pydanticを使用し、APIの入出力や層間でのデータ転送オブジェクト（DTO）を厳密に定義する。

### 2. 認証・認可要件

#### 2.1. 認証方式
*   自前実装による**JWT (JSON Web Token) ベースのトークン認証**を採用する。
*   パスワードは`passlib`と`bcrypt`アルゴリズムを用いてハッシュ化し、データベースに保存する。平文での保存は禁止する。

#### 2.2. ユーザーロール（権限）
システムは以下の3つのロールを管理する。APIエンドポイントごとにアクセス制御を行う。
*   `service_administrator`: 全機能へのアクセス権を持つ最高責任者。
*   `manager`: 現場の責任者。利用者や計画の管理権限を持つ。
*   `employee`: 一般職員。情報の閲覧が主で、作成・更新・削除には承認が必要。

#### 2.3. 多要素認証 (MFA)
*   TOTP (Time-based One-Time Password) アルゴリズムによるMFAを自前で実装する。
*   `Staff`モデルはMFAの有効状態と暗号化されたMFAシークレットを保持する。
*   MFAの有効化（QRコード生成）、検証、無効化を行うAPIを提供する。

### 3. APIエンドポイント仕様

全エンドポイントは `/api/v1` をプレフィックスとする。

| リソース | エンドポイント | HTTPメソッド | 機能概要 | アクセス権限 |
|:---|:---|:---|:---|:---|
| **認証** | `/auth/register-admin` | `POST` | サービス責任者として新規登録する | 公開 |
| | `/auth/register` | `POST` | 一般スタッフとして新規登録する | 公開 |
| | `/auth/token` | `POST` | メールアドレスとパスワードで認証し、JWTを取得する | 公開 |
| **MFA** | `/mfa/enroll` | `POST` | MFAの有効化プロセスを開始する | 認証済みユーザー |
| | `/mfa/verify` | `POST` | MFAのワンタイムコードを検証し、有効化する | 認証済みユーザー |
| | `/mfa/disable` | `POST` | MFAを無効化する | 認証済みユーザー |
| **スタッフ** | `/staff/me` | `GET`, `PATCH` | 自身のプロフィール情報を取得・更新する | 認証済みユーザー |
| | `/staff/invite` | `POST` | 新しいスタッフを事業所に招待する | `service_administrator` |
| | `/staff/{staff_id}` | `DELETE` | スタッフを事業所から削除する | `service_administrator` |
| **事業所** | `/offices` | `GET`, `POST` | 事業所一覧を取得、または新規作成する | 認証済みユーザー, `service_administrator` |
| | `/offices/{office_id}` | `PATCH` | 事業所名を変更する | `service_administrator` |
| | `/offices/{office_id}/deactivate` | `POST` | 事業所を停止（非アクティブ化）する | `service_administrator` |
| | `/office-staff/associate` | `POST` | スタッフを事業所に関連付ける | 認証済みユーザー |
| **利用者** | `/recipients` | `POST` | 新規利用者を登録し、最初の計画サイクルを自動生成する | `manager`以上 |
| | `/recipients/{recipient_id}` | `GET`, `PATCH` | 特定の利用者情報を取得・更新する | `employee`以上 |
| **計画** | `/recipients/{recipient_id}/plans` | `GET` | 特定利用者の全計画サイクル情報を取得する | `employee`以上 |
| | `/recipients/{recipient_id}/documents`| `GET` | 特定利用者の全成果物の署名付きURLを一覧で取得する | `employee`以上 |
| **成果物** | `/plan-deliverables` | `POST` | 成果物(PDF)をアップロードし、ステップを更新する | `manager`以上 |
| | `/plan-deliverables/{id}` | `DELETE` | 成果物(PDF)を削除する | `manager`以上 |
| | `/assessment-sheets` | `POST` | アセスメントシートをアップロードする | `manager`以上 |
| | `/assessment-sheets/{id}` | `PUT`, `DELETE` | アセスメントシートを置換・削除する | `manager`以上 |
| **申請・通知**| `/approval-requests` | `POST` | 操作の承認を申請する | `employee` |
| | `/notices` | `GET` | 自分宛の通知（承認依頼）を一覧で取得する | 認証済みユーザー |
| | `/notices/{notice_id}/approve` | `PATCH` | 通知を承認する | 承認者 |
| | `/notices/{notice_id}/reject` | `PATCH` | 通知を否認する | 承認者 |
| **課金** | `/stripe/create-checkout-session`| `POST` | Stripe Checkoutセッションを作成する | `service_administrator` |
| | `/stripe/create-customer-portal-session`| `POST` | Stripeカスタマーポータルセッションを作成する | `service_administrator` |
| | `/stripe/webhook` | `POST` | StripeからのWebhookイベントを受信する | 公開（署名検証必須） |
| **ダッシュボード**| `/dashboard` | `GET` | ダッシュボードに必要な情報を一括で取得する | `employee`以上 |

### 4. 外部サービス連携要件

#### 4.1. Stripe (決済)
*   利用者数が11人目に達する際のサブスクリプション登録フローをStripe Checkoutで実現する。
*   決済完了、サブスクリプション更新・キャンセルなどのイベントは、Stripe Webhookを通じて非同期でDBに反映させる。Webhookリクエストは署名検証を必須とする。
*   契約者が支払い情報を管理できるよう、Stripeカスタマーポータルへのリダイレクト機能を提供する。

#### 4.2. ファイルストレージ (S3互換)
*   ユーザーがアップロードしたPDFファイル（計画書、アセスメントシート等）は、S3互換のオブジェクトストレージに保存する。
*   ファイルへの直接アクセスは許可せず、全てのファイルアクセスはバックエンドが生成する**署名付きURL**を経由させる。

### 5. 開発・運用要件

#### 5.1. コンテナ化とデプロイ
*   アプリケーションはDockerを用いてコンテナ化する。`Dockerfile`は開発用と本番用でステージを分けるマルチステージビルドを採用する。
*   本番環境へのデプロイはGoogle Cloud Runをターゲットとする。

#### 5.2. CI/CD
*   GitHub Actionsを用いてCI/CDパイプラインを構築する。
*   `main`ブランチへのプッシュをトリガーに、以下の処理を自動で実行する。
    1.  `pytest`による自動テストの実行。
    2.  本番用のDockerイメージをビルドし、Google Artifact Registryにプッシュ。
    3.  新しいイメージをCloud Runにデプロイ。

#### 5.3. テスト
*   `pytest`と`pytest-asyncio`を用いたテスト駆動開発（TDD）を実践する。
*   テスト実行時には、本番・開発とは完全に独立したテスト用データベースを動的に作成・破棄する。
*   各テストはトランザクションで完全に分離され、他のテストに影響を与えないこと。
*   FastAPIの依存性注入（DI）をオーバーライドし、DBセッションや認証ユーザーをモック化する。
*   外部API（Stripeなど）との連携部分は`mocker`を用いてモック化し、内部ロジックのみをテストする。

### 6. コーディング規約

*   **依存関係の方向**: 依存関係は必ず **`api` → `services` → `crud`** という一方向とする。逆方向のインポートは禁止する。
*   **インポート規約**: `services`層から`crud`層を呼び出す際は、必ず`from app import crud`としてトップレベルのパッケージをインポートし、`crud.crud_staff.get(...)`のようにアクセスする。

## model
python

```py
import datetime
import enum
import uuid
from typing import List, Optional

from sqlalchemy import (
    create_engine,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    Enum as SQLAlchemyEnum,
    Boolean,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# --- Enum定義 ---
# Pythonのenumを定義し、SQLのENUM型と連携させるのがベストプラクティスです
class StaffRole(enum.Enum):
    employee = 'employee'
    manager = 'manager'
    owner = 'owner'

class OfficeType(enum.Enum):
    transition_to_employment = 'transition_to_employment'
    type_B_office = 'type_B_office'
    type_A_office = 'type_A_office'

class GenderType(enum.Enum):
    male = 'male'
    female = 'female'
    other = 'other'

class SupportPlanStep(enum.Enum):
    assessment = 'assessment'
    draft_plan = 'draft_plan'
    staff_meeting = 'staff_meeting'
    final_plan_signed = 'final_plan_signed'
    monitoring = 'monitoring'

class DeliverableType(enum.Enum):
    assessment_sheet = 'assessment_sheet'
    draft_plan_pdf = 'draft_plan_pdf'
    staff_meeting_minutes = 'staff_meeting_minutes'
    final_plan_signed_pdf = 'final_plan_signed_pdf'
    monitoring_report_pdf = 'monitoring_report_pdf'

class AssessmentSheetType(enum.Enum):
    """アセスメントシートの種類"""
    basic_info = '1-1.基本情報'
    employment_info = '1-2.就労関係'
    issue_analysis = '2.課題分析'

class BillingStatus(enum.Enum):
    free = 'free'          # 無料プラン
    active = 'active'        # 課金中
    past_due = 'past_due'    # 支払い延滞
    canceled = 'canceled'    # キャンセル済み

# --- Baseクラスの定義 ---
class Base(DeclarativeBase):
    pass

# --- モデル定義 ---

class Staff(Base):
    """スタッフ"""
    __tablename__ = 'staffs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[StaffRole] = mapped_column(SQLAlchemyEnum(StaffRole), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Staff -> OfficeStaff (one-to-many)
    office_associations: Mapped[List["OfficeStaff"]] = relationship(back_populates="staff")

class Office(Base):
    """事業所"""
    __tablename__ = 'offices'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(255))
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    type: Mapped[OfficeType] = mapped_column(SQLAlchemyEnum(OfficeType))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    last_modified_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    billing_status: Mapped[BillingStatus] = mapped_column(
        SQLAlchemyEnum(BillingStatus), default=BillingStatus.free, nullable=False
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    deactivated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Office -> OfficeStaff (one-to-many)
    staff_associations: Mapped[List["OfficeStaff"]] = relationship(back_populates="office")
    
    # Office -> office_welfare_recipients (one-to-many)
    recipient_associations: Mapped[List["OfficeWelfareRecipient"]] = relationship(back_populates="office")

class OfficeStaff(Base):
    """スタッフと事業所の中間テーブル"""
    __tablename__ = 'office_staffs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('offices.id'))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False) # メインの所属か
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # OfficeStaff -> Staff (many-to-one)
    staff: Mapped["Staff"] = relationship(back_populates="office_associations")
    # OfficeStaff -> Office (many-to-one)
    office: Mapped["Office"] = relationship(back_populates="staff_associations")

class WelfareRecipient(Base):
    """受給者"""
    __tablename__ = 'welfare_recipients'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    furigana: Mapped[str] = mapped_column(String(255))
    birth_day: Mapped[datetime.date]
    gender: Mapped[GenderType] = mapped_column(SQLAlchemyEnum(GenderType))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # WelfareRecipient -> OfficeWelfareRecipient (one-to-many)
    office_associations: Mapped[List["OfficeWelfareRecipient"]] = relationship(back_populates="welfare_recipient")
    # WelfareRecipient -> SupportPlanCycle (one-to-many)
    support_plan_cycles: Mapped[List["SupportPlanCycle"]] = relationship(back_populates="welfare_recipient")
    assessment_sheets: Mapped[List["AssessmentSheetDeliverable"]] = relationship(back_populates="welfare_recipient")


class OfficeWelfareRecipient(Base):
    """事業所と受給者の中間テーブル"""
    __tablename__ = 'office_welfare_recipients'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'))
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('offices.id'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # OfficeWelfareRecipient -> WelfareRecipient (many-to-one)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="office_associations")
    # OfficeWelfareRecipient -> Office (many-to-one)
    office: Mapped["Office"] = relationship(back_populates="recipient_associations")

class SupportPlanCycle(Base):
    """個別支援計画の1サイクル（約6ヶ月）"""
    __tablename__ = 'support_plan_cycles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'))
    plan_cycle_start_date: Mapped[datetime.date]
    final_plan_signed_date: Mapped[Optional[datetime.date]]
    next_renewal_deadline: Mapped[Optional[datetime.date]]
    is_latest_cycle: Mapped[bool] = mapped_column(Boolean, default=True)
    google_calendar_id: Mapped[Optional[str]] = mapped_column(Text)
    google_event_id: Mapped[Optional[str]] = mapped_column(Text)
    google_event_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # SupportPlanCycle -> WelfareRecipient (many-to-one)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="support_plan_cycles")
    # SupportPlanCycle -> SupportPlanStatus (one-to-many)
    statuses: Mapped[List["SupportPlanStatus"]] = relationship(back_populates="plan_cycle")
    # SupportPlanCycle -> PlanDeliverable (one-to-many)
    deliverables: Mapped[List["PlanDeliverable"]] = relationship(back_populates="plan_cycle")

class SupportPlanStatus(Base):
    """計画サイクル内の各ステップの進捗"""
    __tablename__ = 'support_plan_statuses'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_cycle_id: Mapped[int] = mapped_column(ForeignKey('support_plan_cycles.id'))
    step_type: Mapped[SupportPlanStep] = mapped_column(SQLAlchemyEnum(SupportPlanStep))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('staffs.id'))
    monitoring_deadline: Mapped[Optional[int]] # default = 7
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # SupportPlanStatus -> SupportPlanCycle (many-to-one)
    plan_cycle: Mapped["SupportPlanCycle"] = relationship(back_populates="statuses")

class PlanDeliverable(Base):
    """計画サイクルに関連する成果物"""
    __tablename__ = 'plan_deliverables'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_cycle_id: Mapped[int] = mapped_column(ForeignKey('support_plan_cycles.id'))
    deliverable_type: Mapped[DeliverableType] = mapped_column(SQLAlchemyEnum(DeliverableType))
    file_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # PlanDeliverable -> SupportPlanCycle (many-to-one)
    plan_cycle: Mapped["SupportPlanCycle"] = relationship(back_populates="deliverables")

class AssessmentSheetDeliverable(Base):
    """アセスメントシートの成果物（アップロードされたファイル）"""
    __tablename__ = 'assessment_sheet_deliverables'

    id: Mapped[int] = mapped_column(primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'))
    assessment_type: Mapped[AssessmentSheetType] = mapped_column(SQLAlchemyEnum(AssessmentSheetType), nullable=False)
    
    file_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 関係性: AssessmentSheetDeliverable -> WelfareRecipient (多対一)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="assessment_sheets")

# Noticeは他の多くのテーブルと関連するため最後に定義
class Notice(Base):
    """お知らせ"""
    __tablename__ = 'notices'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    recipient_staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id')) # 通知の受信者
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('offices.id'))
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[Optional[str]] = mapped_column(Text)
    link_url: Mapped[Optional[str]] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



class RequestStatus(enum.Enum):
    pending = 'pending'
    approved = 'approved'
    rejected = 'rejected'

class RoleChangeRequest(Base):
    """権限変更の申請"""
    __tablename__ = 'role_change_requests'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    requester_staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('offices.id'))
    requested_role: Mapped[StaffRole] = mapped_column(SQLAlchemyEnum(StaffRole), nullable=False)
    status: Mapped[RequestStatus] = mapped_column(SQLAlchemyEnum(RequestStatus), default=RequestStatus.pending)
    request_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by_staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('staffs.id'))
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性を定義
    requester: Mapped["Staff"] = relationship(foreign_keys=[requester_staff_id])
    reviewer: Mapped[Optional["Staff"]] = relationship(foreign_keys=[reviewed_by_staff_id])
```


---
## 以下 not MVP

```py
## 1-1 アセスメントシート 基本情報

import datetime
import enum
import uuid
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# 既存のBaseクラスを想定
class Base(DeclarativeBase):
    pass

# --- Enum定義 ---

class FormOfResidence(enum.Enum):
    at_home_with_family = 'at_home_with_family'
    alone_at_home = 'alone_at_home'
    hospital = 'hospital'
    support_facilities_for_the_disabled = 'support_facilities_for_the_disabled'
    no_nursing_care_in_a_group_home = 'no_nursing_care_in_a_group_home'
    group_home_with_nursing_care = 'group_home_with_nursing_care'
    other_option = 'other_option'

class MeansOfTransportation(enum.Enum):
    train = 'train'
    bus = 'bus'
    bicycle = 'bicycle'
    other_option = 'other_option'

class Household(enum.Enum):
    same = 'same'
    living_apart = 'living_apart'

class LivelihoodProtection(enum.Enum):
    yes_with_stranger_care_fee = 'yes_with_stranger_care_fee'
    yes_no_stranger_care_fee = 'yes_no_stranger_care_fee'
    no = 'no'

class DisabilityCategory(enum.Enum):
    physical_handicap_certificate = 'physical_handicap_certificate'
    rehabilitation_certificate = 'rehabilitation_certificate'
    mental_disability_welfare_certificate = 'mental_disability_welfare_certificate'
    basic_disability_pension = 'basic_disability_pension'
    other_disability_pension = 'other_disability_pension'
    other_handicap_or_disease = 'other_handicap_or_disease'

class PhysicalDisabilityType(enum.Enum):
    visual_impairment = 'visual_impairment'
    hearing_impairment = 'hearing_impairment'
    physical_disability = 'physical_disability'
    internal_disorder = 'internal_disorder'
    other_option = 'other_option'

class ApplicationStatus(enum.Enum):
    not_applicable = 'not_applicable'
    pending = 'pending'
    in_progress = 'in_progress'
    scheduled = 'scheduled'
    completed = 'completed'

class MedicalCareInsurance(enum.Enum):
    national_health_insurance = 'national_health_insurance'
    mutual_aid = 'mutual_aid'
    social_security = 'social_security'
    other_option = 'other_option'

class AidingType(enum.Enum):
    independence_support = 'independence_support'
    subsidy_for_the_severely_physically_and_mentally_handicapped = 'subsidy_for_the_severely_physically_and_mentally_handicapped'
    specific_diseases = 'specific_diseases'
    geriatrics = 'geriatrics'

class WorkConditions(enum.Enum):
    regular_work = 'regular_work'
    part_time_job = 'part_time_job'
    labor_transition_support = 'labor_transition_support'
    support_for_continuous_employment_A_B = 'support_for_continuous_employment_A_B'
    not_yet_employed = 'not_yet_employed'
    other_option = 'other_option'

class WorkOutsideFacility(enum.Enum):
    i_wish_to = 'i_wish_to'
    i_dont_want_to = 'i_dont_want_to'

# --- モデル定義 ---

class ServiceRecipientDetail(Base):
    """受給者の詳細情報 (基本情報)"""
    __tablename__ = 'service_recipient_details'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'), unique=True)
    address: Mapped[str] = mapped_column(Text)
    form_of_residence: Mapped[FormOfResidence] = mapped_column(SQLAlchemyEnum(FormOfResidence))
    form_of_residence_other_text: Mapped[Optional[str]] = mapped_column(Text)
    means_of_transportation: Mapped[MeansOfTransportation] = mapped_column(SQLAlchemyEnum(MeansOfTransportation))
    means_of_transportation_other_text: Mapped[Optional[str]] = mapped_column(Text)
    tel: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: ServiceRecipientDetail -> WelfareRecipient (one-to-oneの逆側)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="detail")
    # 関係性: ServiceRecipientDetail -> EmergencyContact (one-to-many)
    emergency_contacts: Mapped[List["EmergencyContact"]] = relationship(back_populates="service_recipient_detail")

class EmergencyContact(Base):
    """緊急連絡先"""
    __tablename__ = 'emergency_contacts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_recipient_detail_id: Mapped[int] = mapped_column(ForeignKey('service_recipient_details.id'))
    address: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    relation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 関係性: EmergencyContact -> ServiceRecipientDetail (many-to-one)
    service_recipient_detail: Mapped["ServiceRecipientDetail"] = relationship(back_populates="emergency_contacts")

class FamilyOfServiceRecipients(Base):
    """家族構成"""
    __tablename__ = 'family_of_service_recipients'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'))
    name: Mapped[str] = mapped_column(Text)
    relationship: Mapped[str] = mapped_column(Text)
    household: Mapped[Household] = mapped_column(SQLAlchemyEnum(Household))
    ones_health: Mapped[str] = mapped_column(Text)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    family_structure_chart: Mapped[Optional[str]] = mapped_column(Text) # URL or path
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: FamilyOfServiceRecipients -> WelfareRecipient (many-to-one)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="family_members")

class DisabilityStatus(Base):
    """障害についての基本情報"""
    __tablename__ = 'disability_statuses'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'), unique=True)
    disability_or_disease_name: Mapped[str] = mapped_column(Text)
    livelihood_protection: Mapped[LivelihoodProtection] = mapped_column(SQLAlchemyEnum(LivelihoodProtection))
    special_remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 関係性: DisabilityStatus -> WelfareRecipient (one-to-oneの逆側)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="disability_status")
    # 関係性: DisabilityStatus -> DisabilityDetail (one-to-many)
    details: Mapped[List["DisabilityDetail"]] = relationship(back_populates="disability_status")

class DisabilityDetail(Base):
    """個別の障害・手帳・年金の詳細"""
    __tablename__ = 'disability_details'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disability_status_id: Mapped[int] = mapped_column(ForeignKey('disability_statuses.id'))
    category: Mapped[DisabilityCategory] = mapped_column(SQLAlchemyEnum(DisabilityCategory))
    grade_or_level: Mapped[Optional[str]] = mapped_column(Text)
    physical_disability_type: Mapped[Optional[PhysicalDisabilityType]] = mapped_column(SQLAlchemyEnum(PhysicalDisabilityType))
    physical_disability_type_other_text: Mapped[Optional[str]] = mapped_column(Text)
    application_status: Mapped[ApplicationStatus] = mapped_column(SQLAlchemyEnum(ApplicationStatus))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: DisabilityDetail -> DisabilityStatus (many-to-one)
    disability_status: Mapped["DisabilityStatus"] = relationship(back_populates="details")

class WelfareServicesUsed(Base):
    """過去のサービス利用歴"""
    __tablename__ = 'welfare_services_used'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'))
    office_name: Mapped[str] = mapped_column(Text)
    starting_day: Mapped[datetime.date]
    amount_used: Mapped[str] = mapped_column(Text)
    service_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 関係性: WelfareServicesUsed -> WelfareRecipient (many-to-one)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="service_history")

class MedicalMatters(Base):
    """医療に関する基本情報"""
    __tablename__ = 'medical_matters'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'), unique=True)
    medical_care_insurance: Mapped[MedicalCareInsurance] = mapped_column(SQLAlchemyEnum(MedicalCareInsurance))
    medical_care_insurance_other_text: Mapped[Optional[str]] = mapped_column(Text)
    aiding: Mapped[AidingType] = mapped_column(SQLAlchemyEnum(AidingType))
    history_of_hospitalization_in_the_past_2_years: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: MedicalMatters -> WelfareRecipient (one-to-oneの逆側)
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="medical_matters")
    # 関係性: MedicalMatters -> HistoryOfHospitalVisits (one-to-many)
    hospital_visits: Mapped[List["HistoryOfHospitalVisits"]] = relationship(back_populates="medical_matters")

class HistoryOfHospitalVisits(Base):
    """通院歴"""
    __tablename__ = 'history_of_hospital_visits'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medical_matters_id: Mapped[int] = mapped_column(ForeignKey('medical_matters.id'))
    disease: Mapped[str] = mapped_column(Text)
    frequency_of_hospital_visits: Mapped[str] = mapped_column(Text)
    symptoms: Mapped[str] = mapped_column(Text)
    medical_institution: Mapped[str] = mapped_column(Text)
    doctor: Mapped[str] = mapped_column(Text)
    tel: Mapped[str] = mapped_column(Text)
    taking_medicine: Mapped[bool] = mapped_column(Boolean)
    date_started: Mapped[Optional[datetime.date]]
    date_ended: Mapped[Optional[datetime.date]]
    special_remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: HistoryOfHospitalVisits -> MedicalMatters (many-to-one)
    medical_matters: Mapped["MedicalMatters"] = relationship(back_populates="hospital_visits")

class EmploymentRelated(Base):
    """就労関係"""
    __tablename__ = 'employment_related'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'), unique=True)
    created_by_staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    work_conditions: Mapped[WorkConditions] = mapped_column(SQLAlchemyEnum(WorkConditions))
    regular_or_part_time_job: Mapped[bool]
    employment_support: Mapped[bool]
    work_experience_in_the_past_year: Mapped[bool]
    suspension_of_work: Mapped[bool]
    qualifications: Mapped[Optional[str]] = mapped_column(Text)
    main_places_of_employment: Mapped[Optional[str]] = mapped_column(Text)
    general_employment_request: Mapped[bool]
    desired_job: Mapped[Optional[str]] = mapped_column(Text)
    special_remarks: Mapped[Optional[str]] = mapped_column(Text)
    work_outside_the_facility: Mapped[WorkOutsideFacility] = mapped_column(SQLAlchemyEnum(WorkOutsideFacility))
    special_note_about_working_outside_the_facility: Mapped[Optional[str]] = mapped_column(Text)

    # 関係性
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="employment_related")

class IssueAnalysis(Base):
    """課題分析"""
    __tablename__ = 'issue_analyses'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'), unique=True)
    created_by_staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    what_i_like_to_do: Mapped[Optional[str]] = mapped_column(Text)
    im_not_good_at: Mapped[Optional[str]] = mapped_column(Text)
    the_life_i_want: Mapped[Optional[str]] = mapped_column(Text)
    the_support_i_want: Mapped[Optional[str]] = mapped_column(Text)
    points_to_keep_in_mind_when_providing_support: Mapped[Optional[str]] = mapped_column(Text)
    future_dreams: Mapped[Optional[str]] = mapped_column(Text)
    other: Mapped[Optional[str]] = mapped_column(Text)

    # 関係性
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="issue_analysis")

# --- 既存モデルへのリレーションシップ追加 ---
# 上記のモデルと連携するために、既存の`WelfareRecipient`モデルに
# `relationship`を追加する必要があります。

class WelfareRecipient(Base):
    """
    受給者 (アセスメントシート関連のrelationshipを追加)
    ※既存の定義に以下を追加・統合してください
    """
    __tablename__ = 'welfare_recipients'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # ... 既存のカラム定義 ...

    # --- アセスメントシート関連の新しいリレーションシップ ---
    detail: Mapped[Optional["ServiceRecipientDetail"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    family_members: Mapped[List["FamilyOfServiceRecipients"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    disability_status: Mapped[Optional["DisabilityStatus"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    service_history: Mapped[List["WelfareServicesUsed"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    medical_matters: Mapped[Optional["MedicalMatters"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    employment_related: Mapped[Optional["EmploymentRelated"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    issue_analysis: Mapped[Optional["IssueAnalysis"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")

    # ... 既存のリレーションシップ定義 ...
```