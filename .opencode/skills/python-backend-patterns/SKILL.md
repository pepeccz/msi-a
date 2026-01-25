---
name: python-backend-patterns
description: >
  FastAPI and SQLAlchemy async patterns for MSI-a.
  Trigger: Working on api/ or agent/ Python code.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [api, agent]
  auto_invoke: "Working on api/ or agent/ Python code"
---

## Overview

Backend patterns for MSI-a using FastAPI, SQLAlchemy async, and Pydantic.

## FastAPI Patterns

### Router Structure

```python
# api/routes/tariffs.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from api.models.tariffs import TariffCreate, TariffResponse
from api.services.tariff_service import TariffService

router = APIRouter(prefix="/tariffs", tags=["tariffs"])

@router.post("/", response_model=TariffResponse, status_code=201)
async def create_tariff(
    data: TariffCreate,
    db: AsyncSession = Depends(get_db)
) -> TariffResponse:
    """Crear una nueva tarifa."""
    service = TariffService(db)
    return await service.create(data)
```

### Dependency Injection

```python
# Reusable dependencies
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    user = await verify_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    return user

# Usage in route
@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return user
```

### Error Handling

```python
from fastapi import HTTPException

# Use HTTPException for client errors
raise HTTPException(status_code=404, detail="Tarifa no encontrada")
raise HTTPException(status_code=400, detail="Datos inválidos")
raise HTTPException(status_code=403, detail="Acceso denegado")

# Log server errors before raising
try:
    result = await risky_operation()
except Exception as e:
    logger.error("operation_failed", error=str(e))
    raise HTTPException(status_code=500, detail="Error interno")
```

## SQLAlchemy Async Patterns

### Model Definition

```python
# database/models.py
from sqlalchemy import String, Integer, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    # Relationships
    category: Mapped["Category"] = relationship(back_populates="tariffs")
    elements: Mapped[list["Element"]] = relationship(back_populates="tariff")
```

### Async Queries

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Simple query
async def get_tariff(db: AsyncSession, tariff_id: int) -> Tariff | None:
    result = await db.execute(select(Tariff).where(Tariff.id == tariff_id))
    return result.scalar_one_or_none()

# With relationships (avoid N+1)
async def get_tariff_with_elements(db: AsyncSession, tariff_id: int) -> Tariff | None:
    result = await db.execute(
        select(Tariff)
        .options(selectinload(Tariff.elements))
        .where(Tariff.id == tariff_id)
    )
    return result.scalar_one_or_none()

# List with pagination
async def list_tariffs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20
) -> list[Tariff]:
    result = await db.execute(
        select(Tariff)
        .order_by(Tariff.name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())
```

### Transactions

```python
# Automatic transaction (commit on success, rollback on error)
async def create_tariff(db: AsyncSession, data: TariffCreate) -> Tariff:
    tariff = Tariff(**data.model_dump())
    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)
    return tariff

# Manual transaction control
async def transfer_funds(db: AsyncSession, from_id: int, to_id: int, amount: Decimal):
    async with db.begin():
        # Both operations in same transaction
        await debit_account(db, from_id, amount)
        await credit_account(db, to_id, amount)
```

## Pydantic Patterns

### Request/Response Models

```python
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import datetime

class TariffBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0)

class TariffCreate(TariffBase):
    category_id: int

class TariffResponse(TariffBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

### Validation

```python
from pydantic import field_validator, model_validator

class VehicleData(BaseModel):
    plate: str
    year: int

    @field_validator('plate')
    @classmethod
    def validate_plate(cls, v: str) -> str:
        pattern = r'^[0-9]{4}[A-Z]{3}$'
        if not re.match(pattern, v):
            raise ValueError('Formato de matrícula inválido')
        return v.upper()

    @model_validator(mode='after')
    def validate_year(self) -> 'VehicleData':
        current_year = datetime.now().year
        if self.year > current_year + 1:
            raise ValueError('Año no puede ser futuro')
        return self
```

## Service Layer Pattern

```python
# api/services/tariff_service.py
class TariffService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: TariffCreate) -> Tariff:
        # Business logic here
        tariff = Tariff(**data.model_dump())
        self.db.add(tariff)
        await self.db.commit()
        await self.db.refresh(tariff)
        return tariff

    async def calculate_price(self, tariff_id: int, options: dict) -> Decimal:
        tariff = await self.get_by_id(tariff_id)
        if not tariff:
            raise ValueError("Tarifa no encontrada")
        # Calculation logic
        return tariff.price * multiplier
```

## Related Skills

- `coding-standards` - General coding rules
- `msia-api` - MSI-a specific API patterns
- `msia-database` - Database models and migrations
