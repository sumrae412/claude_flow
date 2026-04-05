# Security Guidelines

## OWASP Top 10 Prevention

### 1. Injection (SQL, Command, etc.)

```python
# BAD - SQL injection vulnerable
query = f"SELECT * FROM users WHERE email = '{user_input}'"
await db.execute(text(query))

# GOOD - Parameterized query
await db.execute(
    select(User).where(User.email == user_input)
)

# GOOD - If raw SQL needed, use parameters
await db.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": user_input}
)
```

```python
# BAD - Command injection
os.system(f"convert {user_filename} output.png")

# GOOD - Use subprocess with list args (no shell)
subprocess.run(["convert", user_filename, "output.png"], check=True)

# GOOD - Validate/sanitize filename
import re
if not re.match(r'^[\w\-\.]+$', user_filename):
    raise ValueError("Invalid filename")
```

### 2. Broken Authentication

```python
# Password requirements
MIN_PASSWORD_LENGTH = 12
REQUIRE_SPECIAL_CHAR = True
REQUIRE_NUMBER = True
REQUIRE_UPPERCASE = True

# Always hash passwords
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# Secure session configuration
SESSION_CONFIG = {
    "secret_key": os.environ["SECRET_KEY"],  # Min 32 chars, from env
    "max_age": 3600,  # 1 hour
    "same_site": "lax",
    "https_only": True,  # In production
}
```

### 3. Sensitive Data Exposure

```python
# NEVER log sensitive data
logger.info(f"User login: {email}")  # OK
logger.info(f"Password: {password}")  # NEVER DO THIS
logger.info(f"Token: {token[:8]}...")  # Truncate if needed

# NEVER return sensitive fields in API responses
class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    # password_hash: str  # NEVER include
    # ssn: str  # NEVER include

# Use environment variables for secrets
DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["API_KEY"]
# NEVER hardcode: API_KEY = "sk-1234..."
```

### 4. XML External Entities (XXE)

```python
# If parsing XML, disable external entities
import defusedxml.ElementTree as ET  # Use defusedxml, not xml.etree

tree = ET.parse(xml_file)  # Safe by default
```

### 5. Broken Access Control

```python
# ALWAYS verify ownership/permissions
async def get_resource(
    resource_id: UUID,
    db: AsyncSession,
    current_user: User
) -> Resource:
    resource = await db.get(Resource, resource_id)

    if not resource:
        raise HTTPException(404, "Not found")

    # CRITICAL: Check ownership
    if resource.user_id != current_user.id:
        raise HTTPException(403, "Access denied")

    return resource

# Use dependency injection for auth
@router.get("/admin/users")
async def admin_endpoint(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin)  # Fails if not admin
):
    ...
```

### 6. Security Misconfiguration

```python
# Production settings
DEBUG = False  # NEVER True in production
ALLOWED_HOSTS = ["myapp.com", "www.myapp.com"]  # Specific hosts only

# CORS - be restrictive
CORS_ORIGINS = [
    "https://myapp.com",
    "https://www.myapp.com",
]
# NOT: CORS_ORIGINS = ["*"]

# Security headers (use middleware)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
}
```

### 7. Cross-Site Scripting (XSS)

```python
# In templates - always escape (Jinja2 does this by default)
{{ user_input }}  # Auto-escaped
{{ user_input | safe }}  # DANGEROUS - only if you trust the content

# In JavaScript - don't insert raw HTML
// BAD
element.innerHTML = userInput;

// GOOD
element.textContent = userInput;

// If HTML needed, sanitize first
import DOMPurify from 'dompurify';
element.innerHTML = DOMPurify.sanitize(userInput);
```

### 8. Insecure Deserialization

```python
# NEVER unpickle untrusted data
import pickle
data = pickle.loads(user_input)  # DANGEROUS

# Use JSON for untrusted data
import json
data = json.loads(user_input)  # Safe (but validate schema)

# Validate with Pydantic
class UserInput(BaseModel):
    name: str = Field(max_length=100)
    age: int = Field(ge=0, le=150)

validated = UserInput.model_validate_json(user_input)
```

### 9. Using Components with Known Vulnerabilities

```bash
# Regularly check for vulnerabilities
pip-audit  # Python
npm audit  # JavaScript

# Pin dependencies with hashes
pip install --require-hashes -r requirements.txt

# Keep dependencies updated
pip list --outdated
npm outdated
```

### 10. Insufficient Logging & Monitoring

```python
# Log security-relevant events
logger.warning(f"Failed login attempt for {email} from {ip_address}")
logger.warning(f"Access denied: user {user_id} tried to access resource {resource_id}")
logger.error(f"Suspicious activity: {details}")

# Include context for forensics
logger.info(
    "User action",
    extra={
        "user_id": str(user_id),
        "action": "delete_resource",
        "resource_id": str(resource_id),
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent"),
    }
)
```

---

## Input Validation

### Validate All User Input

```python
from pydantic import BaseModel, Field, field_validator
import re

class UserInput(BaseModel):
    email: str = Field(pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=0, le=150)
    url: str = Field(pattern=r'^https?://[\w\.-]+')

    @field_validator('name')
    @classmethod
    def no_html_in_name(cls, v):
        if '<' in v or '>' in v:
            raise ValueError('HTML not allowed')
        return v.strip()
```

### File Upload Security

```python
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def validate_upload(file: UploadFile):
    # Check extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not allowed")

    # Check file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large")

    # Check magic bytes (actual file type)
    import magic
    mime = magic.from_buffer(content, mime=True)
    if mime not in ['image/jpeg', 'image/png', 'application/pdf']:
        raise HTTPException(400, "Invalid file content")

    # Reset file position
    await file.seek(0)

    # Generate safe filename
    safe_filename = f"{uuid4()}{ext}"
    return safe_filename, content
```

---

## API Security

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/resource")
@limiter.limit("100/minute")
async def get_resource(request: Request):
    ...

# Stricter limits for auth endpoints
@app.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request):
    ...
```

### JWT Best Practices

```python
from jose import jwt
from datetime import datetime, timedelta

# Use strong secret
JWT_SECRET = os.environ["JWT_SECRET"]  # Min 32 chars
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(user_id: UUID) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(401, "Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.JWTError:
        raise HTTPException(401, "Invalid token")
```

---

## Secrets Management

### Environment Variables

```python
# GOOD - from environment
DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["API_KEY"]

# GOOD - with default for optional
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# BAD - hardcoded secrets
API_KEY = "sk-1234567890"  # NEVER DO THIS
```

### .env Files

```bash
# .env (NEVER commit to git)
DATABASE_URL=postgresql://user:pass@localhost/db
SECRET_KEY=your-very-long-secret-key-here
API_KEY=sk-1234567890

# .gitignore
.env
.env.*
*.pem
*.key
```

### Secrets in CI/CD

```yaml
# GitHub Actions - use secrets
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  API_KEY: ${{ secrets.API_KEY }}

# NEVER echo secrets
- run: echo $API_KEY  # DANGEROUS - appears in logs
```

---

## Security Checklist

### Before Deployment

- [ ] All secrets in environment variables (not in code)
- [ ] DEBUG = False in production
- [ ] HTTPS enforced (redirect HTTP)
- [ ] CORS configured restrictively
- [ ] Rate limiting on all endpoints
- [ ] Input validation on all user input
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (output encoding)
- [ ] CSRF protection enabled
- [ ] Security headers configured
- [ ] Dependencies scanned for vulnerabilities
- [ ] Sensitive data not logged
- [ ] Authentication on all protected routes
- [ ] Authorization checks for resource access
- [ ] File uploads validated and sanitized
