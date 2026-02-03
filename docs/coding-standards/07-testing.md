# Estándares de Testing MSI-a

---

## 1. Backend Testing (pytest)

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User

@pytest.mark.asyncio
async def test_create_user(session: AsyncSession):
    """Test user creation."""
    user = User(
        phone="+34600000001",
        client_type="particular",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    assert user.id is not None
    assert user.phone == "+34600000001"

# Fixtures en conftest.py
@pytest.fixture
async def session():
    """SQLite in-memory session for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSessionLocal() as session:
        yield session
    
    await engine.dispose()
```

---

## 2. Frontend Testing (Jest + RTL)

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { api } from '@/lib/api';
import MyComponent from './MyComponent';

jest.mock('@/lib/api');

describe('MyComponent', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });
  
  it('loads and displays items', async () => {
    const mockItems = [{ id: '1', name: 'Item 1' }];
    (api.getItems as jest.Mock).mockResolvedValue({ items: mockItems });
    
    render(<MyComponent />);
    
    await waitFor(() => {
      expect(screen.getByText('Item 1')).toBeInTheDocument();
    });
  });
  
  it('handles create action', async () => {
    const user = userEvent.setup();
    (api.create as jest.Mock).mockResolvedValue({ id: '1' });
    
    render(<MyComponent />);
    
    await user.click(screen.getByText('Crear Nuevo'));
    await user.type(screen.getByLabelText('Nombre'), 'Test');
    await user.click(screen.getByText('Guardar'));
    
    await waitFor(() => {
      expect(api.create).toHaveBeenCalledWith({ name: 'Test' });
    });
  });
});
```

---

## 3. Reglas Críticas

1. ✅ **SIEMPRE** SQLite in-memory para tests unitarios backend
2. ✅ **SIEMPRE** fixtures en conftest.py
3. ✅ **SIEMPRE** rollback después de cada test
4. ✅ **SIEMPRE** @pytest.mark.asyncio para tests async
5. ✅ **SIEMPRE** mock servicios externos
6. ✅ **SIEMPRE** userEvent (NO fireEvent) en frontend
7. ✅ **SIEMPRE** jest.clearAllMocks() en beforeEach
8. ✅ **SIEMPRE** waitFor() para async operations
9. ❌ **NUNCA** depender de DB real
10. ❌ **NUNCA** testear detalles de implementación

---

**Referencias:**
- `tests/conftest.py`
- `skills/pytest-async/SKILL.md`
- `skills/msia-test/SKILL.md`

**Última actualización:** Febrero 2026
