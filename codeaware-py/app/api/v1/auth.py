"""Auth API - /api/auth（团队化升级阶段 A）。

login 无需鉴权；register 仅 admin；me 需登录。
实验室不开放自助注册--管理员通过 register 或 create_admin 脚本建账号。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db, require_admin
from app.core.exceptions import BusinessException
from app.core.response import Result
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=Result[TokenResponse])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.username == req.username))
    if user is None or not user.is_active or not verify_password(req.password, user.password_hash):
        raise BusinessException("AUTH_INVALID_CREDENTIALS", status_code=401)
    token = create_access_token(user_id=user.id, role=user.role)
    return Result.ok(
        TokenResponse(
            access_token=token,
            user=UserOut(
                id=user.id, username=user.username, role=user.role, display_name=user.display_name
            ),
        )
    )


@router.post("/register", response_model=Result[UserOut])
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    exists = await db.scalar(select(User.id).where(User.username == req.username))
    if exists is not None:
        raise BusinessException("AUTH_USERNAME_TAKEN", status_code=409)
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        display_name=req.display_name,
    )
    db.add(user)
    await db.flush()
    return Result.ok(
        UserOut(
            id=user.id, username=user.username, role=user.role, display_name=user.display_name
        )
    )


@router.get("/me", response_model=Result[UserOut])
async def me(user: User = Depends(get_current_user)):
    return Result.ok(
        UserOut(
            id=user.id, username=user.username, role=user.role, display_name=user.display_name
        )
    )
