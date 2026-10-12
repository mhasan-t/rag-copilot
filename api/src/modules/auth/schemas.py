import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

# EmailStr only lowercases the domain; lowercasing the whole address makes logins case-insensitive.
type Email = Annotated[EmailStr, AfterValidator(str.lower)]
# The upper bound stops oversized inputs from making argon2 hashing a cheap DoS.
type NewPassword = Annotated[str, Field(min_length=12, max_length=128)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_superuser: bool
    is_active: bool
    created_by_id: uuid.UUID | None
    created_at: datetime


class UserCreate(BaseModel):
    email: Email
    password: NewPassword


class UserUpdate(BaseModel):
    """Partial update; omitted fields are left unchanged."""

    is_active: bool | None = None
    password: NewPassword | None = None


class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, Field(max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Lifetime in seconds")
