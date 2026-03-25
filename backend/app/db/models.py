from typing import Optional
import uuid as _uuid_mod
import datetime

from fastapi_users.db import SQLAlchemyBaseOAuthAccountTableUUID, SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint
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


class ProjectMembership(Base):
    """Per-project role assignment.  project_id matches the key in .project_registry.json."""

    __tablename__ = "project_membership"
    __table_args__ = (UniqueConstraint("project_id", "user_email", name="uq_project_member"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(_uuid_mod.uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    # project-level role: viewer / manager / admin
    project_role: Mapped[str] = mapped_column(
        SAEnum("viewer", "manager", "admin", name="project_role"),
        nullable=False,
        default="viewer",
    )
    added_by: Mapped[str] = mapped_column(String(254), nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )


class ProjectAccessRequest(Base):
    """A pending request from a user to join a project."""

    __tablename__ = "project_access_request"
    __table_args__ = (
        UniqueConstraint("project_id", "user_email", name="uq_project_access_request"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(_uuid_mod.uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    requested_role: Mapped[str] = mapped_column(
        SAEnum("viewer", "manager", name="requested_project_role"),
        nullable=False,
        default="viewer",
    )
    # pending / approved / denied
    status: Mapped[str] = mapped_column(
        SAEnum("pending", "approved", "denied", name="access_request_status"),
        nullable=False,
        default="pending",
    )
    requested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
