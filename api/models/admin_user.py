"""
MSI Automotive - Admin User Pydantic schemas.

Schemas for admin panel user management with role-based access.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
import re


# =============================================================================
# Validators
# =============================================================================


def _validate_password_complexity(password: str) -> str:
    """Validate password meets Chatwoot complexity requirements."""
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if not re.search(r"[a-z]", password):
        raise ValueError(
            "La contraseña debe contener al menos una letra minúscula"
        )
    if not re.search(r"[A-Z]", password):
        raise ValueError(
            "La contraseña debe contener al menos una letra mayúscula"
        )
    if not re.search(r"\d", password):
        raise ValueError("La contraseña debe contener al menos un número")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\",./<>?\\|`~]", password):
        raise ValueError(
            "La contraseña debe contener al menos un carácter especial"
        )
    return password


# =============================================================================
# Type Definitions
# =============================================================================

AdminRole = Literal["admin", "agent"]
AccessAction = Literal["login", "logout", "login_failed"]


# =============================================================================
# Admin User Schemas
# =============================================================================


class AdminUserBase(BaseModel):
    """Base schema for admin user data."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Unique username (alphanumeric and underscores only)",
    )
    display_name: str | None = Field(
        None,
        max_length=100,
        description="Display name shown in UI",
    )
    role: AdminRole = Field(
        default="agent",
        description="User role: admin (full access) or agent (limited access)",
    )
    email: str | None = Field(
        None,
        max_length=255,
        description="Email address (required for agents, optional for admins)",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username contains only alphanumeric characters and underscores."""
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v.lower()

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid email format")
        return v

    @model_validator(mode="after")
    def validate_email_required_for_agent(self) -> "AdminUserBase":
        if self.role == "agent" and not self.email:
            raise ValueError("Email is required for agent role (needed for Chatwoot sync)")
        return self


class AdminUserCreate(AdminUserBase):
    """Schema for creating a new admin user."""

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (minimum 8 characters)",
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        return _validate_password_complexity(v)


class AdminUserUpdate(BaseModel):
    """Schema for updating an existing admin user."""

    display_name: str | None = Field(
        None,
        max_length=100,
        description="Display name shown in UI",
    )
    role: AdminRole | None = Field(
        None,
        description="User role",
    )
    is_active: bool | None = Field(
        None,
        description="Active status (soft delete)",
    )
    email: str | None = Field(
        None,
        max_length=255,
        description="Email address",
    )

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid email format")
        return v


class AdminUserPasswordChange(BaseModel):
    """Schema for changing admin user password."""

    current_password: str | None = Field(
        None,
        description="Current password (required for non-admin users changing own password)",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (minimum 8 characters)",
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        return _validate_password_complexity(v)


class AdminUserResponse(BaseModel):
    """Schema for admin user response."""

    id: UUID
    username: str
    display_name: str | None
    role: AdminRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    email: str | None = None
    chatwoot_agent_id: int | None = None
    chatwoot_user_id: int | None = None

    model_config = {"from_attributes": True}


class AdminUserWithStats(AdminUserResponse):
    """Schema for admin user with additional statistics."""

    last_login: datetime | None = None
    login_count: int = 0


# =============================================================================
# Access Log Schemas
# =============================================================================


class AdminAccessLogResponse(BaseModel):
    """Schema for access log entry response."""

    id: UUID
    user_id: UUID
    username: str | None = None  # Joined from admin_users
    action: AccessAction
    ip_address: str | None
    user_agent: str | None
    details: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAccessLogListResponse(BaseModel):
    """Schema for paginated access log list."""

    items: list[AdminAccessLogResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


# =============================================================================
# Auth Schemas
# =============================================================================


class LoginRequest(BaseModel):
    """Schema for login request."""

    username: str = Field(..., description="Admin username")
    password: str = Field(..., description="Admin password")


class LoginResponse(BaseModel):
    """Schema for login response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUserResponse(BaseModel):
    """Schema for current user response (from /auth/me)."""

    id: UUID
    username: str
    display_name: str | None
    role: AdminRole
    chatwoot_agent_id: int | None = None
    chatwoot_user_id: int | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# List Response
# =============================================================================


class AdminUserListResponse(BaseModel):
    """Schema for paginated admin user list."""

    items: list[AdminUserResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
