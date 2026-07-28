"""SQLAlchemy 声明基类。P1 起所有 ORM 模型继承 Base。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
