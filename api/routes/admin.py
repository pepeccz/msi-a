"""
MSI Automotive - Admin API routes.

Provides authentication and basic CRUD endpoints for the admin panel.
Includes admin user management with role-based access control.
"""

import logging
import uuid
from datetime import datetime, timedelta, UTC
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.hash import bcrypt
from pydantic import BaseModel
from sqlalchemy import select, func

from api.models.admin_user import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserPasswordChange,
    AdminUserResponse,
    AdminUserListResponse,
    AdminAccessLogResponse,
    AdminAccessLogListResponse,
    LoginRequest,
    LoginResponse,
    CurrentUserResponse,
)
from database.connection import get_async_session
from database.models import (
    User,
    ConversationHistory,
    Policy,
    SystemSetting,
    AdminUser,
    AdminAccessLog,
    Escalation,
)
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin")

# JWT Configuration
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

# Security
security = HTTPBearer(auto_error=False)


# =============================================================================
# Authentication Helpers
# =============================================================================


def create_access_token(
    user_id: uuid.UUID,
    username: str,
    role: str,
) -> tuple[str, datetime]:
    """
    Create JWT access token.

    Args:
        user_id: Admin user UUID
        username: Username to encode in token
        role: User role (admin/user)

    Returns:
        Tuple of (token, expiration_datetime)
    """
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(hours=TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": username,
        "user_id": str(user_id),
        "role": role,
        "type": "admin",
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    token = jwt.encode(payload, settings.ADMIN_JWT_SECRET, algorithm=ALGORITHM)
    return token, expire


def verify_token(token: str) -> dict[str, Any]:
    """
    Verify JWT token and return payload.

    Used for SSE streaming where EventSource doesn't support custom headers,
    so token is passed as query parameter.

    Args:
        token: JWT token string

    Returns:
        Token payload dict

    Raises:
        HTTPException 401: Invalid or expired token
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.ADMIN_JWT_SECRET,
            algorithms=[ALGORITHM],
        )

        # Check token type
        if payload.get("type") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token type")

        return payload

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AdminUser:
    """
    Validate JWT token and return admin user from database.

    Args:
        credentials: Bearer token from Authorization header

    Returns:
        AdminUser object from database

    Raises:
        HTTPException 401: Invalid or missing token, or user not found/inactive
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.ADMIN_JWT_SECRET,
            algorithms=[ALGORITHM],
        )

        # Check token type
        if payload.get("type") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token type")

        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti:
            redis_client = get_redis_client()
            is_blacklisted = await redis_client.get(f"token_blacklist:{jti}")
            if is_blacklisted:
                raise HTTPException(status_code=401, detail="Token has been revoked")

        # Get user from database
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        async with get_async_session() as session:
            result = await session.execute(
                select(AdminUser).where(AdminUser.username == username)
            )
            admin_user = result.scalar_one_or_none()

            if not admin_user:
                raise HTTPException(status_code=401, detail="User not found")

            if not admin_user.is_active:
                raise HTTPException(status_code=401, detail="User account is disabled")

            return admin_user

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*roles: str) -> Callable:
    """
    Create a dependency that requires specific role(s).

    Args:
        roles: Allowed roles (e.g., "admin", "user")

    Returns:
        Dependency function that validates user role

    Example:
        @router.post("/users", dependencies=[Depends(require_role("admin"))])
        async def create_admin_user(...):
            ...
    """
    async def check_role(
        current_user: AdminUser = Depends(get_current_user),
    ) -> AdminUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required role: {', '.join(roles)}",
            )
        return current_user

    return check_role


async def log_access(
    user_id: uuid.UUID,
    action: str,
    request: Request,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an access event (login, logout, login_failed).

    Args:
        user_id: Admin user UUID
        action: Action type (login, logout, login_failed)
        request: FastAPI request object
        details: Additional details to log
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    async with get_async_session() as session:
        log_entry = AdminAccessLog(
            user_id=user_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )
        session.add(log_entry)
        await session.commit()


# =============================================================================
# Auth Routes
# =============================================================================


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    response: Response,
) -> LoginResponse:
    """
    Authenticate admin user and return JWT token.

    Args:
        request: FastAPI request object (for logging)
        login_data: Login credentials
        response: FastAPI response object for setting cookies

    Returns:
        JWT access token

    Raises:
        HTTPException 401: Invalid credentials
    """
    settings = get_settings()

    async with get_async_session() as session:
        # Find user by username
        result = await session.execute(
            select(AdminUser).where(AdminUser.username == login_data.username.lower())
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            logger.warning(f"Login attempt with invalid username: {login_data.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Check if user is active
        if not admin_user.is_active:
            logger.warning(f"Login attempt for disabled user: {login_data.username}")
            await log_access(
                admin_user.id,
                "login_failed",
                request,
                {"reason": "account_disabled"},
            )
            raise HTTPException(status_code=401, detail="Account is disabled")

        # Validate password
        if not bcrypt.verify(login_data.password, admin_user.password_hash):
            logger.warning(f"Login attempt with invalid password for: {login_data.username}")
            await log_access(
                admin_user.id,
                "login_failed",
                request,
                {"reason": "invalid_password"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create token
        token, expire = create_access_token(
            user_id=admin_user.id,
            username=admin_user.username,
            role=admin_user.role,
        )

        # Set HttpOnly cookie
        response.set_cookie(
            key="admin_token",
            value=token,
            httponly=True,
            secure=settings.ENVIRONMENT == "production",
            samesite="lax",
            expires=expire,
        )

        # Log successful login
        await log_access(admin_user.id, "login", request)

        logger.info(f"Admin login successful: {login_data.username}")

        return LoginResponse(
            access_token=token,
            expires_in=TOKEN_EXPIRE_HOURS * 3600,
        )


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Logout admin user by blacklisting their token.

    Args:
        request: FastAPI request object
        response: FastAPI response object
        credentials: Bearer token
        current_user: Current admin user from database

    Returns:
        Success message
    """
    settings = get_settings()

    # Get jti from token
    if credentials:
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.ADMIN_JWT_SECRET,
                algorithms=[ALGORITHM],
            )
            jti = payload.get("jti")
            if jti:
                redis_client = get_redis_client()
                exp = payload.get("exp", 0)
                ttl = max(0, exp - int(datetime.now(UTC).timestamp()))
                await redis_client.setex(f"token_blacklist:{jti}", ttl, "1")
        except JWTError:
            pass

    # Log logout
    await log_access(current_user.id, "logout", request)

    # Clear cookie
    response.delete_cookie("admin_token")

    logger.info(f"Admin logout: {current_user.username}")

    return JSONResponse(content={"message": "Logged out successfully"})


@router.get("/auth/me", response_model=CurrentUserResponse)
async def get_me(
    current_user: AdminUser = Depends(get_current_user),
) -> CurrentUserResponse:
    """
    Get current authenticated user info.

    Args:
        current_user: Current admin user from database

    Returns:
        User info including role
    """
    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role,
    )


# =============================================================================
# Dashboard Routes
# =============================================================================


@router.get("/dashboard/kpis")
async def get_dashboard_kpis(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get dashboard KPI metrics.

    Returns:
        KPI metrics for the dashboard
    """
    async with get_async_session() as session:
        # Total users
        total_users = await session.scalar(select(func.count(User.id)))

        # Total conversations
        total_conversations = await session.scalar(
            select(func.count(ConversationHistory.id))
        )

        # Active policies
        active_policies = await session.scalar(
            select(func.count(Policy.id)).where(Policy.is_active == True)
        )

        return JSONResponse(
            content={
                "total_users": total_users or 0,
                "total_conversations": total_conversations or 0,
                "active_policies": active_policies or 0,
            }
        )


# =============================================================================
# User Routes
# =============================================================================


class UserCreateRequest(BaseModel):
    """User creation request payload."""

    phone: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    nif_cif: str | None = None
    company_name: str | None = None
    client_type: str = "particular"
    metadata: dict | None = None


class UserUpdateRequest(BaseModel):
    """User update request payload."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    nif_cif: str | None = None
    company_name: str | None = None
    client_type: str | None = None
    metadata: dict | None = None


@router.get("/users")
async def list_users(
    current_user: dict = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
    client_type: str | None = None,
) -> JSONResponse:
    """
    List users with pagination.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip
        client_type: Filter by client type (particular/professional)

    Returns:
        Paginated list of users
    """
    async with get_async_session() as session:
        # Build count query
        count_query = select(func.count(User.id))
        if client_type:
            count_query = count_query.where(User.client_type == client_type)
        total = await session.scalar(count_query) or 0

        # Build users query
        query = select(User).order_by(User.created_at.desc())
        if client_type:
            query = query.where(User.client_type == client_type)
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        users = result.scalars().all()

        return JSONResponse(
            content={
                "items": [
                    {
                        "id": str(u.id),
                        "phone": u.phone,
                        "first_name": u.first_name,
                        "last_name": u.last_name,
                        "email": u.email,
                        "nif_cif": u.nif_cif,
                        "company_name": u.company_name,
                        "client_type": u.client_type,
                        "metadata": u.metadata_,
                        "created_at": u.created_at.isoformat(),
                        "updated_at": u.updated_at.isoformat(),
                    }
                    for u in users
                ],
                "total": total,
                "has_more": offset + len(users) < total,
            }
        )


@router.post("/users")
async def create_user(
    data: UserCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Create a new user manually.

    Args:
        data: User data

    Returns:
        Created user details
    """
    # Validate client_type
    if data.client_type not in ("particular", "professional"):
        raise HTTPException(
            status_code=400,
            detail="client_type must be 'particular' or 'professional'"
        )

    async with get_async_session() as session:
        # Check if user with this phone already exists
        existing = await session.execute(
            select(User).where(User.phone == data.phone)
        )
        if existing.scalar():
            raise HTTPException(
                status_code=409,
                detail="User with this phone already exists"
            )

        # Create new user
        new_user = User(
            phone=data.phone,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            nif_cif=data.nif_cif,
            company_name=data.company_name,
            client_type=data.client_type,
            metadata_=data.metadata or {},
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        logger.info(f"Created user {new_user.id} with phone {data.phone}")

        # Sync to Chatwoot if contact exists
        try:
            chatwoot_client = ChatwootClient()
            contact = await chatwoot_client.find_contact_by_phone(new_user.phone)
            if contact:
                tipo = "Profesional" if new_user.client_type == "professional" else "Particular"
                name = f"{new_user.first_name or ''} {new_user.last_name or ''}".strip() or None
                await chatwoot_client.update_contact(
                    contact_id=contact["id"],
                    name=name,
                    custom_attributes={"tipo": tipo},
                )
                logger.info(
                    f"Synced new user {new_user.id} to Chatwoot contact {contact['id']}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to sync new user {new_user.id} to Chatwoot: {e}",
                exc_info=True,
            )
            # Don't fail the request, Chatwoot sync is best-effort

        return JSONResponse(
            status_code=201,
            content={
                "id": str(new_user.id),
                "phone": new_user.phone,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "email": new_user.email,
                "nif_cif": new_user.nif_cif,
                "company_name": new_user.company_name,
                "client_type": new_user.client_type,
                "metadata": new_user.metadata_,
                "created_at": new_user.created_at.isoformat(),
                "updated_at": new_user.updated_at.isoformat(),
            }
        )


@router.get("/users/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Get a user by ID.

    Args:
        user_id: User UUID

    Returns:
        User details
    """
    async with get_async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return JSONResponse(
            content={
                "id": str(user.id),
                "phone": user.phone,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "nif_cif": user.nif_cif,
                "company_name": user.company_name,
                "client_type": user.client_type,
                "metadata": user.metadata_,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat(),
            }
        )


@router.put("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Update a user.

    Args:
        user_id: User UUID
        data: Fields to update

    Returns:
        Updated user details
    """
    async with get_async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate client_type if provided
        if data.client_type is not None:
            if data.client_type not in ("particular", "professional"):
                raise HTTPException(
                    status_code=400,
                    detail="client_type must be 'particular' or 'professional'"
                )

        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == "metadata":
                setattr(user, "metadata_", value)
            else:
                setattr(user, field, value)

        await session.commit()
        await session.refresh(user)

        logger.info(f"Updated user {user_id}: {list(update_data.keys())}")

        # Sync to Chatwoot
        try:
            chatwoot_client = ChatwootClient()
            contact = await chatwoot_client.find_contact_by_phone(user.phone)
            if contact:
                tipo = "Profesional" if user.client_type == "professional" else "Particular"
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None
                await chatwoot_client.update_contact(
                    contact_id=contact["id"],
                    name=name,
                    custom_attributes={"tipo": tipo},
                )
                logger.info(
                    f"Synced updated user {user_id} to Chatwoot contact {contact['id']}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to sync updated user {user_id} to Chatwoot: {e}",
                exc_info=True,
            )
            # Don't fail the request, Chatwoot sync is best-effort

        return JSONResponse(
            content={
                "id": str(user.id),
                "phone": user.phone,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "nif_cif": user.nif_cif,
                "company_name": user.company_name,
                "client_type": user.client_type,
                "metadata": user.metadata_,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat(),
            }
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Delete a user by ID.

    Args:
        user_id: User UUID

    Returns:
        Success message
    """
    async with get_async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        await session.delete(user)
        await session.commit()

        logger.info(f"Deleted user {user_id}")

        return JSONResponse(
            status_code=200,
            content={"message": "User deleted successfully"}
        )


# =============================================================================
# Conversation Routes
# =============================================================================


@router.get("/conversations")
async def list_conversations(
    current_user: AdminUser = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """
    List conversation history with pagination.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip

    Returns:
        Paginated list of conversations
    """
    async with get_async_session() as session:
        # Get total count
        total = await session.scalar(select(func.count(ConversationHistory.id))) or 0

        # Get conversations
        result = await session.execute(
            select(ConversationHistory)
            .order_by(ConversationHistory.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        conversations = result.scalars().all()

        return JSONResponse(
            content={
                "items": [
                    {
                        "id": str(c.id),
                        "conversation_id": c.conversation_id,
                        "user_id": str(c.user_id) if c.user_id else None,
                        "started_at": c.started_at.isoformat(),
                        "ended_at": c.ended_at.isoformat() if c.ended_at else None,
                        "message_count": c.message_count,
                        "summary": c.summary,
                    }
                    for c in conversations
                ],
                "total": total,
                "has_more": offset + len(conversations) < total,
            }
        )


# =============================================================================
# Settings Routes
# =============================================================================


@router.get("/settings")
async def list_settings(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    List all system settings.

    Returns:
        List of system settings
    """
    async with get_async_session() as session:
        result = await session.execute(select(SystemSetting).order_by(SystemSetting.key))
        settings = result.scalars().all()

        return JSONResponse(
            content={
                "items": [
                    {
                        "id": str(s.id),
                        "key": s.key,
                        "value": s.value,
                        "value_type": s.value_type,
                        "description": s.description,
                        "is_mutable": s.is_mutable,
                    }
                    for s in settings
                ],
                "total": len(settings),
                "has_more": False,
            }
        )


# =============================================================================
# Admin User Management Routes
# =============================================================================


@router.get("/admin-users", response_model=AdminUserListResponse)
async def list_admin_users(
    current_user: AdminUser = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
    role: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    """
    List admin users with pagination.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip
        role: Filter by role (admin/user)
        is_active: Filter by active status

    Returns:
        Paginated list of admin users
    """
    async with get_async_session() as session:
        # Build count query
        count_query = select(func.count(AdminUser.id))
        if role:
            count_query = count_query.where(AdminUser.role == role)
        if is_active is not None:
            count_query = count_query.where(AdminUser.is_active == is_active)
        total = await session.scalar(count_query) or 0

        # Build users query
        query = select(AdminUser).order_by(AdminUser.created_at.desc())
        if role:
            query = query.where(AdminUser.role == role)
        if is_active is not None:
            query = query.where(AdminUser.is_active == is_active)
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        users = result.scalars().all()

        return AdminUserListResponse(
            items=[AdminUserResponse.model_validate(u) for u in users],
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(users) < total,
        )


@router.post("/admin-users", response_model=AdminUserResponse, status_code=201)
async def create_admin_user(
    data: AdminUserCreate,
    current_user: AdminUser = Depends(require_role("admin")),
) -> AdminUserResponse:
    """
    Create a new admin user.

    Requires 'admin' role.

    Args:
        data: Admin user data

    Returns:
        Created admin user
    """
    async with get_async_session() as session:
        # Check if username already exists
        existing = await session.execute(
            select(AdminUser).where(AdminUser.username == data.username.lower())
        )
        if existing.scalar():
            raise HTTPException(
                status_code=409,
                detail="Username already exists",
            )

        # Create password hash
        password_hash = bcrypt.hash(data.password)

        # Create new admin user
        new_user = AdminUser(
            username=data.username.lower(),
            password_hash=password_hash,
            role=data.role,
            display_name=data.display_name,
            created_by=current_user.id,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        logger.info(
            f"Admin user created: {new_user.username} (role={new_user.role}) by {current_user.username}"
        )

        return AdminUserResponse.model_validate(new_user)


@router.get("/admin-users/{user_id}", response_model=AdminUserResponse)
async def get_admin_user(
    user_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> AdminUserResponse:
    """
    Get an admin user by ID.

    Args:
        user_id: Admin user UUID

    Returns:
        Admin user details
    """
    async with get_async_session() as session:
        admin_user = await session.get(AdminUser, user_id)
        if not admin_user:
            raise HTTPException(status_code=404, detail="Admin user not found")

        return AdminUserResponse.model_validate(admin_user)


@router.put("/admin-users/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    current_user: AdminUser = Depends(require_role("admin")),
) -> AdminUserResponse:
    """
    Update an admin user.

    Requires 'admin' role.
    Admin cannot change their own role or deactivate themselves.

    Args:
        user_id: Admin user UUID
        data: Fields to update

    Returns:
        Updated admin user
    """
    async with get_async_session() as session:
        admin_user = await session.get(AdminUser, user_id)
        if not admin_user:
            raise HTTPException(status_code=404, detail="Admin user not found")

        # Prevent self-demotion or self-deactivation
        if user_id == current_user.id:
            if data.role is not None and data.role != current_user.role:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change your own role",
                )
            if data.is_active is not None and not data.is_active:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot deactivate your own account",
                )

        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(admin_user, field, value)

        await session.commit()
        await session.refresh(admin_user)

        logger.info(
            f"Admin user updated: {admin_user.username} by {current_user.username}: {list(update_data.keys())}"
        )

        return AdminUserResponse.model_validate(admin_user)


@router.delete("/admin-users/{user_id}")
async def delete_admin_user(
    user_id: uuid.UUID,
    current_user: AdminUser = Depends(require_role("admin")),
) -> JSONResponse:
    """
    Deactivate an admin user (soft delete).

    Requires 'admin' role.
    Admin cannot deactivate themselves.

    Args:
        user_id: Admin user UUID

    Returns:
        Success message
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate your own account",
        )

    async with get_async_session() as session:
        admin_user = await session.get(AdminUser, user_id)
        if not admin_user:
            raise HTTPException(status_code=404, detail="Admin user not found")

        # Soft delete
        admin_user.is_active = False
        await session.commit()

        logger.info(
            f"Admin user deactivated: {admin_user.username} by {current_user.username}"
        )

        return JSONResponse(
            content={"message": "Admin user deactivated successfully"}
        )


@router.put("/admin-users/{user_id}/password")
async def change_admin_user_password(
    user_id: uuid.UUID,
    data: AdminUserPasswordChange,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Change an admin user's password.

    - Admin users can change any user's password without current password
    - Non-admin users can only change their own password and must provide current password

    Args:
        user_id: Admin user UUID
        data: Password change data

    Returns:
        Success message
    """
    async with get_async_session() as session:
        admin_user = await session.get(AdminUser, user_id)
        if not admin_user:
            raise HTTPException(status_code=404, detail="Admin user not found")

        # Check permissions
        is_self = user_id == current_user.id
        is_admin = current_user.role == "admin"

        if not is_self and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Can only change your own password",
            )

        # Non-admin changing own password must provide current password
        if is_self and not is_admin:
            if not data.current_password:
                raise HTTPException(
                    status_code=400,
                    detail="Current password is required",
                )
            if not bcrypt.verify(data.current_password, admin_user.password_hash):
                raise HTTPException(
                    status_code=400,
                    detail="Current password is incorrect",
                )

        # Update password
        admin_user.password_hash = bcrypt.hash(data.new_password)
        await session.commit()

        logger.info(
            f"Password changed for admin user: {admin_user.username} by {current_user.username}"
        )

        return JSONResponse(content={"message": "Password changed successfully"})


# =============================================================================
# Access Log Routes
# =============================================================================


@router.get("/access-log", response_model=AdminAccessLogListResponse)
async def list_access_log(
    current_user: AdminUser = Depends(require_role("admin")),
    limit: int = 50,
    offset: int = 0,
    user_id: uuid.UUID | None = None,
    action: str | None = None,
) -> AdminAccessLogListResponse:
    """
    List access log entries with pagination.

    Requires 'admin' role.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip
        user_id: Filter by admin user ID
        action: Filter by action (login, logout, login_failed)

    Returns:
        Paginated list of access log entries
    """
    async with get_async_session() as session:
        # Build count query
        count_query = select(func.count(AdminAccessLog.id))
        if user_id:
            count_query = count_query.where(AdminAccessLog.user_id == user_id)
        if action:
            count_query = count_query.where(AdminAccessLog.action == action)
        total = await session.scalar(count_query) or 0

        # Build logs query with user join for username
        query = (
            select(AdminAccessLog, AdminUser.username)
            .join(AdminUser, AdminAccessLog.user_id == AdminUser.id)
            .order_by(AdminAccessLog.created_at.desc())
        )
        if user_id:
            query = query.where(AdminAccessLog.user_id == user_id)
        if action:
            query = query.where(AdminAccessLog.action == action)
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        rows = result.all()

        items = [
            AdminAccessLogResponse(
                id=log.id,
                user_id=log.user_id,
                username=username,
                action=log.action,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                details=log.details,
                created_at=log.created_at,
            )
            for log, username in rows
        ]

        return AdminAccessLogListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(items) < total,
        )


# =============================================================================
# Escalation Routes
# =============================================================================


@router.get("/escalations")
async def list_escalations(
    current_user: AdminUser = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> JSONResponse:
    """
    List escalations with pagination.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip
        status: Filter by status (pending, in_progress, resolved)

    Returns:
        Paginated list of escalations
    """
    async with get_async_session() as session:
        # Build count query
        count_query = select(func.count(Escalation.id))
        if status:
            count_query = count_query.where(Escalation.status == status)
        total = await session.scalar(count_query) or 0

        # Build escalations query
        query = select(Escalation).order_by(Escalation.triggered_at.desc())
        if status:
            query = query.where(Escalation.status == status)
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        escalations = result.scalars().all()

        return JSONResponse(
            content={
                "items": [
                    {
                        "id": str(e.id),
                        "conversation_id": e.conversation_id,
                        "user_id": str(e.user_id) if e.user_id else None,
                        "reason": e.reason,
                        "source": e.source,
                        "status": e.status,
                        "triggered_at": e.triggered_at.isoformat(),
                        "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
                        "resolved_by": e.resolved_by,
                        "metadata": e.metadata_,
                    }
                    for e in escalations
                ],
                "total": total,
                "has_more": offset + len(escalations) < total,
            }
        )


@router.get("/escalations/stats")
async def get_escalation_stats(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get escalation statistics for dashboard.

    Returns:
        Statistics: pending count, resolved today, total today
    """
    async with get_async_session() as session:
        # Pending escalations
        pending_count = await session.scalar(
            select(func.count(Escalation.id)).where(Escalation.status == "pending")
        ) or 0

        # In progress escalations
        in_progress_count = await session.scalar(
            select(func.count(Escalation.id)).where(Escalation.status == "in_progress")
        ) or 0

        # Get today's date boundaries in UTC
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Resolved today
        resolved_today = await session.scalar(
            select(func.count(Escalation.id)).where(
                Escalation.status == "resolved",
                Escalation.resolved_at >= today_start,
            )
        ) or 0

        # Total escalations today
        total_today = await session.scalar(
            select(func.count(Escalation.id)).where(
                Escalation.triggered_at >= today_start,
            )
        ) or 0

        return JSONResponse(
            content={
                "pending": pending_count,
                "in_progress": in_progress_count,
                "resolved_today": resolved_today,
                "total_today": total_today,
            }
        )


@router.get("/escalations/{escalation_id}")
async def get_escalation(
    escalation_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get a single escalation by ID.

    Args:
        escalation_id: Escalation UUID

    Returns:
        Escalation details
    """
    async with get_async_session() as session:
        escalation = await session.get(Escalation, escalation_id)
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")

        # Get user phone if available
        user_phone = None
        if escalation.user:
            user_phone = escalation.user.phone

        return JSONResponse(
            content={
                "id": str(escalation.id),
                "conversation_id": escalation.conversation_id,
                "user_id": str(escalation.user_id) if escalation.user_id else None,
                "user_phone": user_phone,
                "reason": escalation.reason,
                "source": escalation.source,
                "status": escalation.status,
                "triggered_at": escalation.triggered_at.isoformat(),
                "resolved_at": escalation.resolved_at.isoformat() if escalation.resolved_at else None,
                "resolved_by": escalation.resolved_by,
                "metadata": escalation.metadata_,
            }
        )


@router.post("/escalations/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Mark an escalation as resolved.

    Args:
        escalation_id: Escalation UUID

    Returns:
        Updated escalation
    """
    async with get_async_session() as session:
        escalation = await session.get(Escalation, escalation_id)
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")

        if escalation.status == "resolved":
            raise HTTPException(status_code=400, detail="Escalation is already resolved")

        # Update escalation
        escalation.status = "resolved"
        escalation.resolved_at = datetime.now(UTC)
        escalation.resolved_by = current_user.display_name or current_user.username

        await session.commit()
        await session.refresh(escalation)

        logger.info(
            f"Escalation {escalation_id} resolved by {current_user.username}",
            extra={
                "escalation_id": str(escalation_id),
                "resolved_by": current_user.username,
            },
        )

        return JSONResponse(
            content={
                "id": str(escalation.id),
                "status": escalation.status,
                "resolved_at": escalation.resolved_at.isoformat(),
                "resolved_by": escalation.resolved_by,
                "message": "Escalation resolved successfully",
            }
        )
