"""
MSI Automotive - Admin User Pydantic schemas.

Schemas for admin panel user management with role-based access.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
import re


# =============================================================================
# Type Definitions
# =============================================================================

AdminRole = Literal["admin", "user"]
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
        default="user",
        description="User role: admin (full access) or user (limited access)",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username contains only alphanumeric characters and underscores."""
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v.lower()


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
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


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
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


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
