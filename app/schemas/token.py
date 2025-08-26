from pydantic import BaseModel
from typing import Optional

class TokenData(BaseModel):
    sub: Optional[str] = None