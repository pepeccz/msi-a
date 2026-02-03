# Estándares de Seguridad MSI-a

---

## 1. JWT Authentication

```python
from api.routes.admin import create_access_token, get_current_user

# Create token
token = create_access_token({"sub": user.username, "jti": str(uuid.uuid4())})

# Protect endpoint
@router.get("/protected")
async def protected(current_user: AdminUser = Depends(get_current_user)):
    return {"user": current_user.username}

# RBAC
from api.routes.admin import require_role

@router.delete("/admin-only", dependencies=[Depends(require_role("admin"))])
async def admin_only(current_user: AdminUser = Depends(get_current_user)):
    return {"message": "Admin access granted"}
```

---

## 2. SSRF Prevention

```python
from shared.image_security import validate_url

# Validate before download
try:
    validate_url(image_url, allowed_domains=["storage.chatwoot.com"])
except ValueError as e:
    raise HTTPException(400, f"Invalid URL: {e}")

# Download with manual redirect following
response = await client.get(url, follow_redirects=False)
if response.status_code in (301, 302):
    redirect_url = response.headers["location"]
    validate_url(redirect_url, allowed_domains)  # Validate redirect!
```

---

## 3. Image Security (Multi-Layer)

```python
from shared.image_security import validate_image_full

try:
    mime_type, width, height = validate_image_full(
        image_bytes,
        max_size_mb=10,
    )
except ImageSecurityError as e:
    raise HTTPException(400, f"Invalid image: {e}")

# validate_image_full checks:
# 1. Magic numbers (file signature)
# 2. PIL parsing (detect polyglot files)
# 3. Decompression bomb detection
# 4. Image dimensions
```

---

## 4. Path Traversal Prevention

```python
from shared.image_security import sanitize_filename

# Sanitize user input
safe_name = sanitize_filename(user_provided_filename)

# Validate path
file_path = (UPLOAD_DIR / safe_name).resolve()
if not file_path.is_relative_to(UPLOAD_DIR):
    raise ValueError("Path traversal detected")
```

---

## 5. Rate Limiting

```python
from api.middleware.rate_limit import RateLimiter

limiter = RateLimiter()

@router.post("/upload")
async def upload(file: UploadFile, username: str):
    try:
        limiter.check_rate_limit(
            key=f"upload:{username}",
            max_requests=10,
            window_seconds=60,
        )
    except ValueError as e:
        raise HTTPException(429, str(e))
    
    # Process upload...
```

---

## 6. Input Validation

```python
# ✅ SIEMPRE usar Pydantic
from pydantic import BaseModel, Field, field_validator

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    
    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v
```

---

## 7. SQL Injection Prevention

```python
# ✅ CORRECTO - SQLAlchemy ORM
result = await session.execute(
    select(User).where(User.username == username)
)

# ❌ INCORRECTO - Raw SQL (vulnerable)
query = f"SELECT * FROM users WHERE username = '{username}'"  # NEVER!
```

---

## 8. Password Hashing

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash
hashed = pwd_context.hash(plain_password)

# Verify
if not pwd_context.verify(plain_password, hashed):
    raise HTTPException(401, "Invalid credentials")
```

---

## 9. Sensitive Data Logging

```python
from shared.logging_config import sanitize_phone

# ✅ CORRECTO
logger.info("user_login", phone=sanitize_phone(user.phone))

# ❌ INCORRECTO
logger.info("user_login", phone=user.phone)  # Exposes full number!
```

---

## 10. CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),  # From env
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

---

**Última actualización:** Febrero 2026
