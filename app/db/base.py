from sqlalchemy.orm import (
    DeclarativeBase
)

# 1. 全てのモデルが継承するためのBaseクラスを定義
class Base(DeclarativeBase):
    pass

