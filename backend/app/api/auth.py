"""
Authentication API routes.
"""
import secrets
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from loguru import logger

from app.database import get_db
from app.models import User, APIToken
from app.utils.auth import verify_password, create_access_token, decode_access_token, get_password_hash
from app.utils.rate_limit import login_rate_limiter

router = APIRouter(prefix="/api/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxy headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return ""


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.get("/first-run")
async def check_first_run(db: AsyncSession = Depends(get_db)):
    """Check if this is a first-time setup (no users exist)."""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return {
        "first_run": len(users) == 0,
        "user_count": len(users)
    }


@router.post("/register")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register the first admin user. Only works when no users exist."""
    # Check if any users exist
    result = await db.execute(select(User))
    users = result.scalars().all()

    if len(users) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration is disabled. Users already exist."
        )

    # Validate input
    if not request.username or len(request.username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters"
        )

    if not request.password or len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )

    # Create admin user
    user = User(
        username=request.username,
        password_hash=get_password_hash(request.password),
        role="admin",
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create access token
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )

    return {
        "success": True,
        "message": "Admin user created successfully",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role
        }
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    login_request: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    # Rate limiting - check before processing
    client_ip = get_client_ip(request)
    is_allowed, retry_after = await login_rate_limiter.is_allowed(client_ip)

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )

    # Find user
    result = await db.execute(select(User).where(User.username == login_request.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Clear rate limit on successful login
    await login_rate_limiter.clear(client_ip)

    # Update last login (use UTC for consistency)
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    # Create access token
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 86400,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role
        }
    }


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token or API key."""
    # Try JWT auth first
    if credentials:
        token = credentials.credentials
        payload = decode_access_token(token)

        if payload:
            username = payload.get("sub")
            if username:
                result = await db.execute(select(User).where(User.username == username))
                user = result.scalar_one_or_none()
                if user and user.is_active:
                    return user

    # Fall back to API key auth via X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        result = await db.execute(
            select(APIToken).where(
                APIToken.token == api_key,
                APIToken.is_active == True,
            )
        )
        api_token = result.scalar_one_or_none()

        if api_token:
            # Check expiration
            if api_token.expires_at and api_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key has expired"
                )

            # Load associated user
            result = await db.execute(select(User).where(User.id == api_token.user_id))
            user = result.scalar_one_or_none()

            if user and user.is_active:
                # Update last_used timestamp
                api_token.last_used = datetime.now(timezone.utc)
                await db.flush()
                # Store API key name for downstream use (e.g., set_by in temp limits)
                request.state.api_key_name = api_token.name
                return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "created_at": current_user.created_at,
        "last_login": current_user.last_login
    }


@router.post("/change-password")
async def change_password(
    password_request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change current user password."""
    if not verify_password(password_request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    current_user.password_hash = get_password_hash(password_request.new_password)
    await db.commit()

    return {"message": "Password changed successfully"}


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require current user to be an admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


# --- API Key Management ---

class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Descriptive name for the API key")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Days until expiration (null = never)")


class APIKeyResponse(BaseModel):
    id: int
    name: str
    token: str
    token_preview: str
    created_at: str
    expires_at: Optional[str]
    last_used: Optional[str]
    is_active: bool


class CreateAPIKeyResponse(BaseModel):
    id: int
    name: str
    token: str
    created_at: str
    expires_at: Optional[str]


@router.get("/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all API keys for the current user. Tokens are masked."""
    result = await db.execute(
        select(APIToken)
        .where(APIToken.user_id == current_user.id)
        .order_by(APIToken.created_at.desc())
    )
    tokens = result.scalars().all()

    return [
        APIKeyResponse(
            id=t.id,
            name=t.name or "Unnamed",
            token=t.token or "",
            token_preview=t.token[:8] + "..." if t.token else "",
            created_at=t.created_at.isoformat() + "Z" if t.created_at else "",
            expires_at=(t.expires_at.isoformat() + "Z") if t.expires_at else None,
            last_used=(t.last_used.isoformat() + "Z") if t.last_used else None,
            is_active=t.is_active,
        )
        for t in tokens
    ]


@router.post("/api-keys", response_model=CreateAPIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new API key. The full token is returned only once."""
    token = secrets.token_hex(32)  # 64-char hex string

    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)

    api_token = APIToken(
        user_id=current_user.id,
        token=token,
        name=request.name,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(api_token)
    await db.flush()
    await db.refresh(api_token)

    logger.info(f"API key '{request.name}' created by {current_user.username}")

    return CreateAPIKeyResponse(
        id=api_token.id,
        name=api_token.name or "Unnamed",
        token=token,
        created_at=api_token.created_at.isoformat() + "Z" if api_token.created_at else "",
        expires_at=(api_token.expires_at.isoformat() + "Z") if api_token.expires_at else None,
    )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Revoke an API key (soft-delete by setting is_active=False)."""
    result = await db.execute(
        select(APIToken).where(
            APIToken.id == key_id,
            APIToken.user_id == current_user.id,
        )
    )
    api_token = result.scalar_one_or_none()

    if not api_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    api_token.is_active = False
    await db.flush()

    logger.info(f"API key '{api_token.name}' (id={key_id}) revoked by {current_user.username}")

    return {"message": "API key revoked"}
