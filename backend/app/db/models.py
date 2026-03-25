from typing import Optional

from fastapi_users.db import SQLAlchemyBaseOAuthAccountTableUUID, SQLAlchemyBaseUserTableUUID
from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """Stores OAuth provider tokens linked to a User (used by fastapi-users)."""


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model with role field mapping to the RBAC roles (viewer/designer/admin)."""

    role: Mapped[str] = mapped_column(
        SAEnum("viewer", "designer", "admin", name="user_role"),
        nullable=False,
        default="viewer",
    )

    github_access_token_encrypted: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, default=None
    )

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount", lazy="joined"
    )
