from pydantic import BaseModel


class MfaEnrollmentResponse(BaseModel):
    secret_key: str
    qr_code_uri: str
