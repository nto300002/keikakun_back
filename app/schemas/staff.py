import uuid
from pydantic import BaseModel, EmailStr
from app.models.enums import StaffRole


class StaffBase(BaseModel):
    email: EmailStr
    name: str


class StaffCreate(StaffBase):
    password: str


class Staff(StaffBase):
    id: uuid.UUID
    role: StaffRole

    class Config:
        from_attributes = True