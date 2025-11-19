from pydantic import BaseModel


class MfaEnrollmentResponse(BaseModel):
    secret_key: str
    qr_code_uri: str


class AdminMfaEnableResponse(BaseModel):
    """管理者によるMFA有効化のレスポンススキーマ"""
    message: str
    staff_id: str
    staff_name: str
    qr_code_uri: str
    secret_key: str
    recovery_codes: list[str]
