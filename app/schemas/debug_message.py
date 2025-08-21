from pydantic import BaseModel, ConfigDict # ★ ConfigDictをインポート
import datetime

class DebugMessageBase(BaseModel):
    message: str

class DebugMessageCreate(DebugMessageBase):
    pass

class DebugMessage(DebugMessageBase):
    id: int
    created_at: datetime.datetime

    # --- Pydantic V2 の記法 (新) ---
    # class Config: ... の代わりに model_config を使用します
    model_config = ConfigDict(from_attributes=True)

    # --- Pydantic V1 の記法 (旧) ---
    # class Config:
    #     orm_mode = True