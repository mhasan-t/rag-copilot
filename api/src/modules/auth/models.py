import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class User(Base):
    # "user" is a reserved word in Postgres; unquoted `FROM user` returns the current role, not this table.
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(String(320), unique=True, comment="Stored lowercased; the login identifier")
    password_hash: Mapped[str] = mapped_column(String(255), comment="argon2id hash")
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), comment="Manages users and approves high-risk actions; set via CLI only"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), comment="Inactive users cannot log in; users are never deleted"
    )
    token_version: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        comment="Copied into access tokens; incrementing it (on password reset) revokes all existing tokens",
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id"), comment="Superuser who created this account; null for CLI-created superusers"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
