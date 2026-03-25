from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model with role field mapping to the RBAC roles (viewer/designer/admin)."""

    role: Mapped[str] = mapped_column(
        SAEnum("viewer", "designer", "admin", name="user_role"),
        nullable=False,
        default="viewer",
    )
