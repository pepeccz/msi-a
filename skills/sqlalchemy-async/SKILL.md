---
name: sqlalchemy-async
description: >
  SQLAlchemy async patterns for database operations.
  Trigger: When working with database models, async queries, relationships, or migrations.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, database, api]
  auto_invoke: "Writing Alembic migrations"
---

## Async Engine Setup

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/db"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

# Dependency for FastAPI
async def get_session() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## Model Definition

```python
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    
    # Relationships
    posts: Mapped[list["Post"]] = relationship(back_populates="author", lazy="selectin")

class Post(Base):
    __tablename__ = "posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    
    # Relationships
    author: Mapped["User"] = relationship(back_populates="posts")
```

## Async Queries

```python
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload, joinedload

# Select all
async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return result.scalars().all()

# Select with filter
async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()

# Select with eager loading
async def get_user_with_posts(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(
        select(User)
        .options(selectinload(User.posts))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()

# Pagination
async def get_users_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[User]:
    result = await session.execute(
        select(User)
        .offset(skip)
        .limit(limit)
        .order_by(User.created_at.desc())
    )
    return result.scalars().all()
```

## Insert/Update/Delete

```python
# Create
async def create_user(session: AsyncSession, email: str, name: str) -> User:
    user = User(email=email, name=name)
    session.add(user)
    await session.flush()  # Get ID without committing
    return user

# Update single
async def update_user(session: AsyncSession, user_id: int, **kwargs) -> User | None:
    user = await session.get(User, user_id)
    if not user:
        return None
    for key, value in kwargs.items():
        setattr(user, key, value)
    await session.flush()
    return user

# Bulk update
async def deactivate_users(session: AsyncSession, user_ids: list[int]) -> int:
    result = await session.execute(
        update(User)
        .where(User.id.in_(user_ids))
        .values(is_active=False)
    )
    return result.rowcount

# Delete
async def delete_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        delete(User).where(User.id == user_id)
    )
    return result.rowcount > 0
```

## Alembic Migration

```python
"""Add users table

Revision ID: 001_users
"""
from alembic import op
import sqlalchemy as sa

revision = "001_users"
down_revision = None

def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

def downgrade() -> None:
    op.drop_index("ix_users_email")
    op.drop_table("users")
```

## Async Alembic env.py

```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

def run_migrations_offline():
    context.configure(url=DATABASE_URL, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

## Critical Rules

- ALWAYS use `async with` for sessions
- ALWAYS call `await session.flush()` to get IDs before commit
- ALWAYS use `selectinload` or `joinedload` for eager loading
- NEVER use synchronous operations in async context
- ALWAYS use `scalar_one_or_none()` for optional single results
- ALWAYS create indexes for frequently queried columns
- ALWAYS use `expire_on_commit=False` for async sessions
